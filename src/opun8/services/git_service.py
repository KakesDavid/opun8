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
        """Add a remote origin."""
        try:
            # Check if remote already exists
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                # Remote exists, update it
                subprocess.run(
                    ["git", "remote", "set-url", "origin", repo_url],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                # Remote doesn't exist, add it
                subprocess.run(
                    ["git", "remote", "add", "origin", repo_url],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            return True
        except Exception as e:
            console.print(f"[red]Git remote error: {e}[/red]")
            return False

    def push(self, branch: str = "main") -> bool:
        """Push to remote repository."""
        try:
            result = subprocess.run(
                ["git", "push", "-u", "origin", branch],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return True
            else:
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

    def push_to_github(self, repo_url: str, branch: str = "main") -> Tuple[bool, str]:
        """
        Complete Git workflow: init, add, commit, remote, push.
        Returns: (success, message)
        """
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        ) as progress:
            
            # Step 1: Initialize Git if needed
            if not self.is_git_repo():
                task = progress.add_task("[cyan]Initializing Git repository...", total=None)
                if not self.init_repo():
                    return False, "Failed to initialize Git repository."
                progress.update(task, description="[green]Git repository initialized.")
            
            # Step 2: Add files
            task = progress.add_task("[cyan]Adding files...", total=None)
            if not self.add_all():
                return False, "Failed to add files to Git."
            progress.update(task, description="[green]Files added.")
            
            # Step 3: Commit files
            task = progress.add_task("[cyan]Committing files...", total=None)
            if not self.commit():
                return False, "Failed to commit files."
            progress.update(task, description="[green]Files committed.")
            
            # Step 4: Add remote
            task = progress.add_task("[cyan]Adding remote...", total=None)
            if not self.add_remote(repo_url):
                return False, "Failed to add remote."
            progress.update(task, description="[green]Remote added.")
            
            # Step 5: Push
            task = progress.add_task("[cyan]Pushing to GitHub...", total=None)
            if not self.push(branch):
                return False, "Failed to push to GitHub."
            progress.update(task, description="[green]Successfully pushed to GitHub!")
        
        return True, "Successfully pushed to GitHub!"

    def create_and_push(self, repo_url: str) -> Tuple[bool, str]:
        """
        Create initial commit and push to GitHub.
        Handles cases where repo is empty or has existing content.
        """
        try:
            # Check if we need to create an initial commit
            if not self.is_git_repo():
                self.init_repo()
                self.add_all()
                self.commit()
            
            # Add remote
            self.add_remote(repo_url)
            
            # Push
            branch = self.get_branch()
            result = subprocess.run(
                ["git", "push", "-u", "origin", f"{branch}:{branch}", "--force"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode == 0:
                return True, f"Successfully pushed to GitHub ({branch} branch)"
            else:
                # Try with force if regular push fails
                if "failed to push some refs" in result.stderr:
                    result = subprocess.run(
                        ["git", "push", "-u", "origin", f"{branch}:{branch}", "--force"],
                        cwd=self.project_path,
                        capture_output=True,
                        text=True,
                        timeout=60
                    )
                    if result.returncode == 0:
                        return True, f"Successfully pushed to GitHub ({branch} branch)"
                
                return False, f"Push failed: {result.stderr}"
                
        except Exception as e:
            return False, f"Git error: {e}"