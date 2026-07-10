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
        """Add a remote origin, or update it if one already exists."""
        try:
            # Check if remote already exists
            existing = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10
            )

            if existing.returncode == 0:
                # Remote exists, update it
                result = subprocess.run(
                    ["git", "remote", "set-url", "origin", repo_url],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
            else:
                # Remote doesn't exist, add it
                result = subprocess.run(
                    ["git", "remote", "add", "origin", repo_url],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10
                )

            # Both branches above assign `result` — check it instead of
            # assuming success, otherwise a failed `remote add`/`set-url`
            # (bad URL, permissions, etc.) gets reported as a success and
            # the real error only surfaces later as a confusing push failure.
            if result.returncode == 0:
                return True
            else:
                console.print(f"[red]Git remote error: {result.stderr}[/red]")
                return False
        except Exception as e:
            console.print(f"[red]Git remote error: {e}[/red]")
            return False

    def push(self, branch: str = "main", force: bool = False) -> bool:
        """Push to remote repository.

        force=True should only be used as an explicit, user-confirmed
        choice — it overwrites whatever history is on the remote.
        """
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

    def push_to_github(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        force: bool = False,
    ) -> Tuple[bool, str]:
        """
        Complete Git workflow: init, add, commit, remote, push.

        Args:
            repo_url: Remote URL to push to.
            branch: Branch to push. Defaults to the repo's current
                branch (falls back to "main" for a brand new repo)
                instead of assuming every project uses "main".
            force: If True, force-push when a normal push is rejected.
                Defaults to False, so a rejected push (e.g. the remote
                has commits this repo doesn't) is reported as a
                failure instead of silently overwriting the remote's
                history.

        Returns: (success, message)
        """
        branch = branch or self.get_branch()

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

            # Step 3: Commit, but only if there's actually something staged.
            # Re-running this on a clean repo used to call `git commit`
            # anyway, which fails with "nothing to commit" and made the
            # whole workflow report failure even though there was nothing
            # wrong.
            if self.has_changes():
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
            success, push_message = self._push_with_optional_force(branch, force)
            if not success:
                return False, push_message
            progress.update(task, description="[green]Successfully pushed to GitHub!")

        return True, f"Successfully pushed to GitHub ({branch} branch)."

    def _push_with_optional_force(self, branch: str, force: bool) -> Tuple[bool, str]:
        """Push to `branch`. Only force-pushes if `force=True` was
        explicitly requested AND a normal push was rejected — never as
        the default path.
        """
        if self.push(branch):
            return True, "Pushed."

        if not force:
            return False, (
                "Push was rejected — the remote has commits this repo "
                "doesn't have locally. Pull and merge first, or re-run "
                "with force=True if you're sure you want to overwrite "
                "the remote's history."
            )

        if self.push(branch, force=True):
            return True, "Force-pushed."

        return False, "Push failed even with --force. Check the remote URL and your permissions."

    def create_and_push(self, repo_url: str, force: bool = False) -> Tuple[bool, str]:
        """
        Create an initial commit (if needed) and push to GitHub.

        This used to duplicate push_to_github() with its own git
        workflow that force-pushed unconditionally on every call,
        including the very first attempt — meaning any push through
        this method could silently overwrite a remote's existing
        history. It's now a thin wrapper around push_to_github(),
        which only force-pushes when force=True is passed explicitly
        and a normal push was actually rejected first.
        """
        return self.push_to_github(repo_url, force=force)