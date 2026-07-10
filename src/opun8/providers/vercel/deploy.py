"""
Vercel deployment for Opun8.
"""

import os
import json
import zipfile
import tempfile
from pathlib import Path
from typing import Optional, Dict, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

import requests

from opun8.providers.vercel.auth import get_vercel_token

console = Console()


def deploy_to_vercel(
    project_path: Path,
    project_name: str,
    framework: str = None,
    env_vars: Dict[str, str] = None,
) -> Tuple[bool, str]:
    """
    Deploy a project to Vercel.
    Returns: (success, message/url)
    """
    
    token = get_vercel_token()
    if not token:
        return False, "Not authenticated with Vercel. Run: opun8 vercel"
    
    env_vars = env_vars or {}
    
    console.print()
    console.print("[bold cyan]▲ Deploying to Vercel...[/bold cyan]")
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        
        # Step 1: Prepare project
        task = progress.add_task("[cyan]Preparing project...", total=None)
        
        # Create a deployment package
        zip_path = create_deployment_package(project_path)
        if not zip_path:
            return False, "Failed to create deployment package."
        
        progress.update(task, description="[green]Project prepared.")
        
        # Step 2: Create deployment
        task = progress.add_task("[cyan]Creating deployment...", total=None)
        
        # Get project ID or create new project
        project_id = get_or_create_project(token, project_name, framework)
        if not project_id:
            return False, "Failed to create Vercel project."
        
        progress.update(task, description="[green]Project created.")
        
        # Step 3: Upload files
        task = progress.add_task("[cyan]Uploading files...", total=None)
        
        deployment_url = create_deployment(token, project_id, zip_path, env_vars)
        if not deployment_url:
            return False, "Failed to create deployment."
        
        progress.update(task, description="[green]Files uploaded.")
        
        # Step 4: Wait for deployment to complete
        task = progress.add_task("[cyan]Waiting for deployment...", total=None)
        
        final_url = wait_for_deployment(token, deployment_url)
        if not final_url:
            return False, "Deployment failed."
        
        progress.update(task, description="[green]Deployment complete!")
        
        # Clean up
        if zip_path and os.path.exists(zip_path):
            os.unlink(zip_path)
    
    return True, final_url


def create_deployment_package(project_path: Path) -> Optional[str]:
    """Create a zip file of the project for deployment."""
    try:
        # Create temporary zip file
        fd, zip_path = tempfile.mkstemp(suffix='.zip')
        os.close(fd)
        
        # Files to exclude
        exclude = {'.git', 'node_modules', '.venv', '__pycache__', '*.pyc', '.env'}
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in project_path.rglob('*'):
                if file_path.is_file():
                    # Check if file should be excluded
                    rel_path = file_path.relative_to(project_path)
                    should_exclude = False
                    for pattern in exclude:
                        if any(part == pattern or part.startswith(pattern) for part in rel_path.parts):
                            should_exclude = True
                            break
                    if not should_exclude:
                        zipf.write(file_path, rel_path)
        
        return zip_path
        
    except Exception as e:
        console.print(f"[red]Error creating deployment package: {e}[/red]")
        return None


def get_or_create_project(token: str, project_name: str, framework: str = None) -> Optional[str]:
    """Get existing project or create a new one."""
    
    # Try to find existing project
    response = requests.get(
        "https://api.vercel.com/v9/projects",
        headers={"Authorization": f"Bearer {token}"},
        timeout=30
    )
    
    if response.status_code == 200:
        projects = response.json().get("projects", [])
        for project in projects:
            if project.get("name") == project_name:
                return project.get("id")
    
    # Create new project
    payload = {
        "name": project_name,
        "framework": framework or "other",
    }
    
    response = requests.post(
        "https://api.vercel.com/v9/projects",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        },
        json=payload,
        timeout=30
    )
    
    if response.status_code == 200:
        return response.json().get("id")
    
    return None


def create_deployment(token: str, project_id: str, zip_path: str, env_vars: Dict[str, str]) -> Optional[str]:
    """Create a deployment."""
    
    with open(zip_path, 'rb') as f:
        files = {'file': f}
        data = {
            'projectId': project_id,
            'target': 'production',
        }
        
        response = requests.post(
            "https://api.vercel.com/v13/deployments",
            headers={"Authorization": f"Bearer {token}"},
            data=data,
            files=files,
            timeout=120
        )
        
        if response.status_code == 200:
            return response.json().get("url")
        else:
            console.print(f"[red]Deployment failed: {response.text}[/red]")
            return None


def wait_for_deployment(token: str, deployment_url: str, timeout: int = 120) -> Optional[str]:
    """Wait for deployment to complete."""
    import time
    
    # Extract deployment ID from URL
    deployment_id = deployment_url.split('/')[-1] if '/' in deployment_url else deployment_url
    
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        response = requests.get(
            f"https://api.vercel.com/v13/deployments/{deployment_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            status = data.get("status", "PENDING")
            
            if status == "READY":
                return data.get("url")
            elif status == "ERROR":
                return None
        
        time.sleep(5)
    
    return None