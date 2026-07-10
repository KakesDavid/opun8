"""
Git service for Opun8.
Handles all Git operations: init, add, commit, push.
"""

import os
import subprocess
from pathlib import Path
from typing import Optional, Tuple
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()


class GitService:
    """Handle Git operations for Opun8."""

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()
        self.git_path = self.project_path / ".git"

    def is_git_repo(self) -> bool:
        """Check if the current directory is a Git repository."""
        return self.git_path.exists() and self.git_path.is_dir()

    def init_repo(self) -> bool:
        """Initialize a Git repository in the project path."""
        try:
            result = subprocess.run(
                ["git", "init"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return True
            else:
                console.print(f"[red]Git init failed: {result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Git init error: {e}[/red]")
            return False

    def add_all(self) -> bool:
        """Add all files to Git staging."""
        try:
            result = subprocess.run(
                ["git", "add", "."],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return True
            else:
                console.print(f"[red]Git add failed: {result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Git add error: {e}[/red]")
            return False

    def commit(self, message: str = "Initial commit by Opun8") -> bool:
        """Commit staged files."""
        try:
            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                return True
            else:
                console.print(f"[red]Git commit failed: {result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Git commit error: {e}[/red]")
            return False

    def add_remote(self, repo_url: str) -> bool:
        """Add a remote origin, or update it if one already exists."""
        try:
            existing = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )

            if existing.returncode == 0:
                result = subprocess.run(
                    ["git", "remote", "set-url", "origin", repo_url],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                result = subprocess.run(
                    ["git", "remote", "add", "origin", repo_url],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

            if result.returncode == 0:
                return True
            else:
                console.print(f"[red]Git remote error: {result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Git remote error: {e}[/red]")
            return False

    def push(self, branch: str = "main", force: bool = False) -> bool:
        """Push to remote repository."""
        try:
            cmd = ["git", "push", "-u", "origin", branch]
            if force:
                cmd.append("--force")
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return True
            else:
                # Check if it's a "repository not found" error
                if "repository not found" in result.stderr.lower():
                    return "not_found"
                console.print(f"[red]Git push failed: {result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Git push error: {e}[/red]")
            return False

    def get_branch(self) -> str:
        """Get the current branch name."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                return result.stdout.strip()
            return "main"
        except Exception:
            return "main"

    def status(self) -> str:
        """Get Git status."""
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout
        except Exception:
            return ""

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        return bool(self.status())

    def repo_exists_on_github(self, token: str, repo_name: str) -> bool:
        """Check if a repository already exists on GitHub."""
        try:
            import requests
            
            # Try to get the repo
            response = requests.get(
                f"https://api.github.com/repos/{repo_name}",
                headers={
                    "Authorization": f"token {token}",
                    "Accept": "application/vnd.github.v3+json"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                return True
            elif response.status_code == 404:
                return False
            else:
                # Any other error, assume it doesn't exist
                return False
        except Exception:
            return False

    def create_github_repo(self, token: str, repo_name: str, description: str = "", private: bool = False) -> Tuple[bool, str]:
        """
        Create a GitHub repository using the API.
        Returns: (success, message)
        """
        try:
            import requests
            
            # First check if repo already exists
            if self.repo_exists_on_github(token, repo_name):
                return "exists", f"Repository '{repo_name}' already exists on GitHub."
            
            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json"
            }
            data = {
                "name": repo_name,
                "description": description,
                "private": private,
                "auto_init": True
            }
            
            response = requests.post(
                "https://api.github.com/user/repos",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 201:
                return True, "Repository created successfully."
            else:
                return False, f"Failed to create repository: {response.text}"
        except Exception as e:
            return False, f"Error creating repository: {e}"

    def push_to_github(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        force: bool = False,
        token: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Complete Git workflow: init, add, commit, remote, push.
        Returns: (success, message)
        """
        # Extract repo name from URL
        repo_name = repo_url.rstrip('/').split('/')[-1]
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        
        # Create repo on GitHub if it doesn't exist
        if token:
            result, message = self.create_github_repo(token, repo_name)
            
            if result == "exists":
                # Repository already exists — ask user what to do
                console.print()
                console.print(f"[yellow]⚠️  Repository '{repo_name}' already exists on GitHub.[/yellow]")
                console.print("[dim]What would you like to do?[/dim]")
                console.print()
                console.print("  [bold cyan]1[/] 📝  [white]Use a different name[/white]")
                console.print("  [bold cyan]2[/] 🔄  [white]Skip GitHub[/white]  [dim](continue without pushing)[/dim]")
                console.print("  [bold cyan]3[/] 🚪  [white]Cancel deployment[/white]")
                console.print()
                
                choice = Prompt.ask(
                    "[bold cyan]➜[/] Select an option",
                    choices=["1", "2", "3"],
                    default="1",
                    show_choices=False,
                )
                
                if choice == "3":
                    return False, "Deployment cancelled by user."
                elif choice == "2":
                    return False, "Skipping GitHub push."
                elif choice == "1":
                    # Ask for new repo name
                    console.print()
                    new_name = Prompt.ask("[bold cyan]➜[/] Enter a new repository name")
                    if new_name:
                        # Update repo_url with new name
                        new_repo_url = f"https://github.com/{repo_url.split('/')[-2]}/{new_name}"
                        # Try again with new name
                        return self.push_to_github(new_repo_url, branch, force, token)
                    else:
                        console.print("[red]No name provided. Skipping GitHub.[/red]")
                        return False, "Skipping GitHub push."
            elif not result:
                return False, message
        
        branch = branch or self.get_branch()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:

            if not self.is_git_repo():
                task = progress.add_task("[cyan]Initializing Git repository...", total=None)
                if not self.init_repo():
                    return False, "Failed to initialize Git repository."
                progress.update(task, description="[green]Git repository initialized.")

            task = progress.add_task("[cyan]Adding files...", total=None)
            if not self.add_all():
                return False, "Failed to add files to Git."
            progress.update(task, description="[green]Files added.")

            if self.has_changes():
                task = progress.add_task("[cyan]Committing files...", total=None)
                if not self.commit():
                    return False, "Failed to commit files."
                progress.update(task, description="[green]Files committed.")

            task = progress.add_task("[cyan]Adding remote...", total=None)
            if not self.add_remote(repo_url):
                return False, "Failed to add remote."
            progress.update(task, description="[green]Remote added.")

            task = progress.add_task("[cyan]Pushing to GitHub...", total=None)
            push_result = self.push(branch)
            
            if push_result == "not_found":
                return False, "Repository not found on GitHub. Please create it first or check the name."
            elif not push_result:
                return False, "Failed to push to GitHub."
            elif push_result is True:
                progress.update(task, description="[green]Successfully pushed to GitHub!")

        return True, f"Successfully pushed to GitHub ({branch} branch)."

    def create_and_push(self, repo_url: str, force: bool = False) -> Tuple[bool, str]:
        return self.push_to_github(repo_url, force=force)