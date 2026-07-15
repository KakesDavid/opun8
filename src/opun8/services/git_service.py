"""
Git service for Opun8.
Handles all Git operations: init, add, commit, push, clone, and branch management.

This version fixes three root-cause bugs found in production:

1. New repos were created with `auto_init=True`, which makes GitHub create
   its own initial commit (README). That commit history is *unrelated* to
   the local project's history, so the very first push always fails with
   "refusing to merge unrelated histories". New repos are now created empty.

2. `pull()` never passed `--allow-unrelated-histories`, so pulling from a
   pre-existing remote repo (which legitimately has its own history) failed
   the same way. It now retries with that flag, and distinguishes a real
   merge conflict from a clean auto-merge.

3. Interactive prompts were being shown *while* a Rich `Progress` live
   display was still running, which corrupts terminal output (duplicated /
   garbled menus). All prompts now happen with the progress display stopped.

Additional hardening: recursion depth guard against infinite retry loops,
network retry/backoff for GitHub API calls, defensive validation throughout
so a single failure mode can't crash the whole flow, and robust clone
functionality for repository deployment.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Optional, Tuple, Union, Literal

from rich.console import Console
from rich.prompt import Prompt
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

# Prevents runaway recursion if e.g. every candidate repo name collides.
MAX_PUSH_RETRIES = 5
CLONE_TIMEOUT = 120  # seconds


# ──────────────────────────────────────────────────────────────
# SAFE PROMPT (handles Ctrl+C / Ctrl+Z)
# ──────────────────────────────────────────────────────────────

def _safe_prompt(
    message: str,
    choices: Optional[list] = None,
    default: str = "1",
    show_choices: bool = False,
) -> Optional[str]:
    """
    Prompt the user with graceful handling of Ctrl+C and Ctrl+Z.
    Returns None if the user cancels.
    """
    try:
        if choices:
            return Prompt.ask(
                message,
                choices=choices,
                default=default,
                show_choices=show_choices,
            )
        return Prompt.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        return None


class GitService:
    """Handle Git operations for Opun8."""

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()
        self.git_path = self.project_path / ".git"

    # ──────────────────────────────────────────────────────────────
    # BASIC GIT OPERATIONS
    # ──────────────────────────────────────────────────────────────

    def is_git_repo(self) -> bool:
        return self.git_path.exists() and self.git_path.is_dir()

    def init_repo(self) -> bool:
        try:
            result = subprocess.run(
                ["git", "init"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            console.print(f"[red]Git init error: {e}[/red]")
            return False

    def add_all(self) -> bool:
        try:
            result = subprocess.run(
                ["git", "add", "."],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            console.print(f"[red]Git add error: {e}[/red]")
            return False

    def commit(self, message: str = "Initial commit by Opun8") -> bool:
        try:
            # Ensure a committer identity exists locally so fresh CI/CD
            # containers or brand-new machines don't fail with
            # "Please tell me who you are".
            self._ensure_git_identity()

            result = subprocess.run(
                ["git", "commit", "-m", message],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                return True
            if "nothing to commit" in result.stderr.lower():
                return True
            console.print(f"[red]Git commit error: {result.stderr.strip()}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Git commit error: {e}[/red]")
            return False

    def _ensure_git_identity(self) -> None:
        """Set a local fallback git identity if none is configured."""
        for key, value in (("user.name", "Opun8 Bot"), ("user.email", "opun8@users.noreply.github.com")):
            check = subprocess.run(
                ["git", "config", "--get", key],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if check.returncode != 0 or not check.stdout.strip():
                subprocess.run(
                    ["git", "config", key, value],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

    def add_remote(self, repo_url: str) -> bool:
        try:
            existing = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if existing.returncode == 0:
                result = subprocess.run(
                    ["git", "remote", "set-url", "origin", repo_url],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            else:
                result = subprocess.run(
                    ["git", "remote", "add", "origin", repo_url],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
            return result.returncode == 0
        except Exception as e:
            console.print(f"[red]Git remote error: {e}[/red]")
            return False

    def push(self, branch: str = "main", force: bool = False) -> Union[bool, Literal["not_found"]]:
        try:
            cmd = ["git", "push", "-u", "origin", branch]
            if force:
                cmd.append("--force")
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                return True
            stderr_lower = result.stderr.lower()
            if "repository not found" in stderr_lower:
                return "not_found"
            return False
        except Exception as e:
            console.print(f"[red]Git push error: {e}[/red]")
            return False

    def pull(self, branch: str = "main") -> Tuple[bool, bool]:
        """
        Pull latest changes from remote.

        Returns:
            (success, had_conflicts)
            - (True, False):  pulled/merged cleanly
            - (False, True):  pulled but hit real merge conflicts (needs
                               manual resolution — do NOT retry automatically)
            - (False, False): pull failed for another reason
        """
        try:
            result = subprocess.run(
                ["git", "pull", "origin", branch, "--no-rebase"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=60,
            )
            if result.returncode == 0:
                console.print("[green]✅ Pulled latest changes from remote.[/green]")
                return True, False

            combined = (result.stdout + result.stderr).lower()

            # Root-cause fix: retry once with --allow-unrelated-histories
            # when the remote has independent history (e.g. a repo that
            # was auto-initialized with a README on GitHub).
            if "refusing to merge unrelated histories" in combined:
                console.print("[dim]Remote has unrelated history — retrying merge...[/dim]")
                result2 = subprocess.run(
                    ["git", "pull", "origin", branch, "--no-rebase", "--allow-unrelated-histories"],
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result2.returncode == 0:
                    console.print("[green]✅ Merged unrelated histories successfully.[/green]")
                    return True, False

                combined2 = (result2.stdout + result2.stderr).lower()
                if "conflict" in combined2:
                    console.print("[yellow]⚠️  Merge conflicts detected — manual resolution required.[/yellow]")
                    return False, True

                console.print(f"[yellow]Pull failed: {result2.stderr.strip()}[/yellow]")
                return False, False

            if "conflict" in combined:
                console.print("[yellow]⚠️  Merge conflicts detected — manual resolution required.[/yellow]")
                return False, True

            console.print(f"[yellow]Pull failed: {result.stderr.strip()}[/yellow]")
            return False, False
        except Exception as e:
            console.print(f"[yellow]Pull error: {e}[/yellow]")
            return False, False

    # ──────────────────────────────────────────────────────────────
    # CLONE REPOSITORY
    # ──────────────────────────────────────────────────────────────

    def clone_repository(
        self,
        repo_url: str,
        target_path: str,
        token: Optional[str] = None,
        branch: Optional[str] = None,
        depth: Optional[int] = None,
    ) -> Tuple[bool, str]:
        """
        Clone a GitHub repository to a local directory.

        Args:
            repo_url: The GitHub repository URL (e.g., https://github.com/user/repo)
            target_path: The local path to clone into
            token: Optional GitHub token for private repositories
            branch: Optional branch to clone (defaults to default branch)
            depth: Optional shallow clone depth (e.g., 1 for latest only)

        Returns:
            (success, message) tuple

        Note on token handling: authenticating by embedding the token in
        the clone URL means it's briefly visible in this process's argument
        list (e.g. to `ps`) while the clone runs — the same residual
        exposure any tool has without a dedicated credential helper. What
        we *do* control is persistence: git writes whatever URL it's given
        into `origin` in the resulting `.git/config`, so immediately after
        a successful clone the remote is reset to the credential-free
        `repo_url`, ensuring the token doesn't linger on disk in the
        checked-out project.
        """
        target = Path(target_path)

        # Ensure parent directory exists
        target.parent.mkdir(parents=True, exist_ok=True)

        # Build the clone URL with token if provided
        clone_url = repo_url
        if token:
            # Convert https://github.com/user/repo to https://token@github.com/user/repo
            if repo_url.startswith("https://"):
                clone_url = repo_url.replace("https://", f"https://{token}@")
            elif repo_url.startswith("http://"):
                clone_url = repo_url.replace("http://", f"http://{token}@")

        try:
            # Remove existing directory if it exists
            if target.exists():
                shutil.rmtree(target)

            # Build the clone command
            cmd = ["git", "clone", clone_url, str(target)]
            if branch:
                cmd.extend(["-b", branch])
            if depth is not None and depth > 0:
                cmd.extend(["--depth", str(depth)])

            # Clone the repository
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=CLONE_TIMEOUT,
                check=False,
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()
                # Clean up sensitive token from error message if present
                if token and token in stderr:
                    stderr = stderr.replace(token, "[REDACTED]")
                return False, f"Git clone failed: {stderr}"

            # Strip the credential-bearing URL out of .git/config right away
            if token:
                subprocess.run(
                    ["git", "remote", "set-url", "origin", repo_url],
                    cwd=target,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

            return True, f"Successfully cloned to {target}"

        except subprocess.TimeoutExpired:
            return False, f"Clone timed out after {CLONE_TIMEOUT} seconds"
        except shutil.Error as e:
            return False, f"Failed to remove existing directory: {e}"
        except Exception as e:
            return False, f"Clone error: {str(e)}"

    # ──────────────────────────────────────────────────────────────
    # BRANCH MANAGEMENT
    # ──────────────────────────────────────────────────────────────

    def get_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip() and result.stdout.strip() != "HEAD":
                return result.stdout.strip()
            return "main"
        except Exception:
            return "main"

    def get_default_branch(self) -> str:
        try:
            result = subprocess.run(
                ["git", "remote", "show", "origin"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=15,
            )
            for line in result.stdout.split("\n"):
                if "HEAD branch" in line:
                    return line.split(":")[-1].strip()
            return "main"
        except Exception:
            return "main"

    def rename_branch(self, old_name: str, new_name: str) -> bool:
        if old_name == new_name:
            return True
        try:
            result = subprocess.run(
                ["git", "branch", "-m", old_name, new_name],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    def ask_branch_name(self) -> Optional[str]:
        console.print()
        console.print("[bold]Which branch would you like to push to?[/bold]")
        console.print("  [bold cyan]1[/] 📌  [white]main[/white]  [dim](recommended)[/dim]")
        console.print("  [bold cyan]2[/] 📌  [white]master[/white]  [dim](legacy)[/dim]")
        console.print()

        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2"],
            default="1",
        )
        if choice is None:
            return None
        return "master" if choice == "2" else "main"

    # ──────────────────────────────────────────────────────────────
    # STATUS AND CHANGES
    # ──────────────────────────────────────────────────────────────

    def status(self) -> str:
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.stdout
        except Exception:
            return ""

    def has_changes(self) -> bool:
        return bool(self.status())

    def has_commits(self) -> bool:
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            return result.returncode == 0
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────
    # GITHUB REPOSITORY MANAGEMENT
    # ──────────────────────────────────────────────────────────────

    def _github_request(self, method: str, url: str, headers: dict, timeout: int, **kwargs):
        """Small retry/backoff wrapper around requests for transient network errors."""
        import requests

        last_exc = None
        for attempt in range(3):
            try:
                return requests.request(method, url, headers=headers, timeout=timeout, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as e:
                last_exc = e
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
        raise last_exc

    def repo_exists_on_github(self, token: str, repo_name: str) -> bool:
        """
        Check if a repository exists on GitHub.
        repo_name must be in 'owner/repo' format.
        """
        try:
            response = self._github_request(
                "GET",
                f"https://api.github.com/repos/{repo_name}",
                headers={"Authorization": f"token {token}"},
                timeout=10,
            )
            return response.status_code == 200
        except Exception:
            return False

    def parse_repo_url(self, repo_url: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            repo_url = repo_url.strip().rstrip("/")
            if not repo_url:
                return None, None
            if repo_url.endswith(".git"):
                repo_url = repo_url[:-4]

            if repo_url.startswith("git@"):
                parts = repo_url.split(":")
                if len(parts) == 2:
                    path_parts = [p for p in parts[1].split("/") if p]
                    if len(path_parts) >= 2:
                        return path_parts[-2], path_parts[-1]
                return None, None

            if repo_url.startswith("http://") or repo_url.startswith("https://"):
                url = repo_url.replace("http://", "").replace("https://", "")
                parts = [p for p in url.split("/") if p]
                if len(parts) >= 3:
                    return parts[1], parts[2]
                return None, None

            parts = [p for p in repo_url.split("/") if p]
            if len(parts) >= 2:
                return parts[-2], parts[-1]
            return None, None
        except Exception:
            return None, None

    def create_github_repo(
        self,
        token: str,
        owner: str,
        repo_name: str,
        description: str = "",
        private: bool = False,
    ) -> Tuple[Union[bool, Literal["exists"]], str]:
        """
        Create a GitHub repository using the API.

        IMPORTANT: new repositories are created EMPTY (auto_init=False).
        Auto-initializing with a README creates a commit history on GitHub
        that is unrelated to the local project's history, which guarantees
        the first push will fail with "refusing to merge unrelated
        histories". Leaving the repo empty lets the first push populate it
        cleanly with no merge required at all.

        Returns:
            Tuple of (True|"exists"|False, message)
        """
        try:
            full_repo_name = f"{owner}/{repo_name}"

            if self.repo_exists_on_github(token, full_repo_name):
                return "exists", f"Repository '{full_repo_name}' already exists on GitHub."

            headers = {
                "Authorization": f"token {token}",
                "Accept": "application/vnd.github.v3+json",
            }
            data = {
                "name": repo_name,
                "description": description,
                "private": private,
                "auto_init": False,
            }

            # Determine whether `owner` is an organization or the token's
            # own user account, since these use different API endpoints.
            is_org = False
            try:
                org_response = self._github_request(
                    "GET",
                    f"https://api.github.com/orgs/{owner}",
                    headers=headers,
                    timeout=10,
                )
                if org_response.status_code == 200:
                    is_org = True
            except Exception:
                pass

            if is_org:
                response = self._github_request(
                    "POST",
                    f"https://api.github.com/orgs/{owner}/repos",
                    headers=headers,
                    timeout=30,
                    json=data,
                )
            else:
                response = self._github_request(
                    "POST",
                    "https://api.github.com/user/repos",
                    headers=headers,
                    timeout=30,
                    json=data,
                )

            if response.status_code == 201:
                return True, f"Repository '{full_repo_name}' created successfully."
            return False, f"Failed to create repository: {response.text}"
        except Exception as e:
            return False, f"Error creating repository: {e}"

    # ──────────────────────────────────────────────────────────────
    # COMPLETE PUSH WORKFLOW
    # ──────────────────────────────────────────────────────────────

    def push_to_github(
        self,
        repo_url: str,
        branch: Optional[str] = None,
        force: bool = False,
        token: Optional[str] = None,
        _retry_count: int = 0,
    ) -> Tuple[bool, str]:
        if _retry_count >= MAX_PUSH_RETRIES:
            return False, "Too many retries — stopping to avoid an infinite loop. Please try again with a different repository name."

        owner, repo_name = self.parse_repo_url(repo_url)
        if not owner or not repo_name:
            return False, f"Could not parse repository URL: {repo_url}"

        full_repo_name = f"{owner}/{repo_name}"

        repo_exists = False
        if token:
            repo_exists = self.repo_exists_on_github(token, full_repo_name)

        if branch is None:
            branch = self.ask_branch_name()
            if branch is None:
                return False, "Operation cancelled by user."

        # ────────────────────────────────────────────────
        # Handle a repo that already exists on GitHub
        # ────────────────────────────────────────────────
        if repo_exists:
            console.print()
            console.print(f"[yellow]⚠️  Repository '[cyan]{full_repo_name}[/cyan]' already exists on GitHub.[/yellow]")
            console.print("[dim]What would you like to do?[/dim]")
            console.print()
            console.print("  [bold cyan]1[/] 📤  [white]Push to existing repository[/white]")
            console.print("  [bold cyan]2[/] 📝  [white]Use a different name[/white]")
            console.print("  [bold cyan]3[/] ⏭️  [white]Skip GitHub[/white]")
            console.print("  [bold cyan]4[/] 🚪  [white]Cancel[/white]")
            console.print()

            choice = _safe_prompt(
                "[bold cyan]➜[/] Select an option",
                choices=["1", "2", "3", "4"],
                default="1",
            )

            if choice is None or choice == "4":
                return False, "Operation cancelled."
            if choice == "3":
                return False, "Skipping GitHub push."
            if choice == "2":
                new_name = _safe_prompt("[bold cyan]➜[/] Enter a new repository name")
                if not new_name:
                    return False, "Operation cancelled." if new_name is None else "Skipping GitHub push."
                new_name = new_name.replace(" ", "-")
                new_name = re.sub(r"[^a-zA-Z0-9\-_]", "", new_name)
                new_name = new_name.lower()
                if not new_name:
                    console.print("[red]That name isn't valid. Please try again.[/red]")
                    return self.push_to_github(repo_url, branch, force, token, _retry_count + 1)
                new_repo_url = f"https://github.com/{owner}/{new_name}"
                return self.push_to_github(new_repo_url, branch, force, token, _retry_count + 1)
            # choice == "1": fall through and push to the existing repo
        else:
            if token:
                result, message = self.create_github_repo(token, owner, repo_name)
                if result == "exists":
                    # Repo appeared between our check and now (race condition).
                    console.print(f"[yellow]Repository '{full_repo_name}' already exists — continuing.[/yellow]")
                    return self.push_to_github(repo_url, branch, force, token, _retry_count + 1)
                if not result:
                    return False, message

        # ────────────────────────────────────────────────
        # LOCAL GIT WORKFLOW
        # ────────────────────────────────────────────────
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=True,
        )
        progress.start()
        try:
            if not self.is_git_repo():
                task = progress.add_task("[cyan]Initializing Git...", total=None)
                if not self.init_repo():
                    return False, "Failed to initialize Git."
                progress.update(task, description="[green]Git initialized.")

            task = progress.add_task("[cyan]Adding files...", total=None)
            if not self.add_all():
                return False, "Failed to add files."
            progress.update(task, description="[green]Files added.")

            if self.has_changes() or not self.has_commits():
                task = progress.add_task("[cyan]Committing files...", total=None)
                if not self.commit():
                    return False, "Failed to commit."
                progress.update(task, description="[green]Files committed.")

            task = progress.add_task("[cyan]Adding remote...", total=None)
            if not self.add_remote(repo_url):
                return False, "Failed to add remote."
            progress.update(task, description="[green]Remote added.")

            local_branch = self.get_branch()
            if self.has_commits() and local_branch != branch:
                progress.stop()
                console.print(f"[dim]Renaming '{local_branch}' to '{branch}'...[/dim]")
                progress.start()
                if self.rename_branch(local_branch, branch):
                    local_branch = branch
                else:
                    branch = local_branch

            task = progress.add_task("[cyan]Pushing to GitHub...", total=None)
            push_result = self.push(branch, force)

            if push_result is True:
                progress.update(task, description="[green]Successfully pushed!")
                progress.stop()
                return True, f"Successfully pushed to GitHub ({branch} branch)."

            if push_result == "not_found":
                progress.stop()
                return False, "Repository not found. It may have been deleted or you may lack access."

            # push_result is False: rejected push. Stop the live display
            # BEFORE prompting — mixing Prompt.ask with an active Progress
            # Live render is what caused the garbled/duplicated menus.
            progress.stop()
        finally:
            if progress.live.is_started:
                progress.stop()

        console.print()
        console.print("[yellow]⚠️  Push was rejected — the remote has commits this repo doesn't have.[/yellow]")
        console.print("[dim]What would you like to do?[/dim]")
        console.print()
        console.print("  [bold cyan]1[/] 🔄  [white]Pull and merge[/white]  [dim](safe)[/dim]")
        console.print("  [bold cyan]2[/] 💪  [white]Force push[/white]  [dim](overwrites remote)[/dim]")
        console.print("  [bold cyan]3[/] ⏭️  [white]Skip GitHub[/white]")
        console.print("  [bold cyan]4[/] 🚪  [white]Cancel[/white]")
        console.print()

        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2", "3", "4"],
            default="1",
        )

        if choice is None or choice == "4":
            return False, "Operation cancelled."
        if choice == "3":
            return False, "Skipping GitHub push."

        if choice == "1":
            console.print("[dim]Pulling latest changes...[/dim]")
            pulled, had_conflicts = self.pull(branch)
            if had_conflicts:
                return (
                    False,
                    "Merge conflicts were detected. Please resolve them manually "
                    "(git status will show the conflicted files), commit, and re-run deploy.",
                )
            if not pulled:
                return False, "Pull failed and the push is still rejected. Try Force push or Skip GitHub instead."

            console.print("[dim]Attempting push again...[/dim]")
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                console=console, transient=True,
            ) as p2:
                t2 = p2.add_task("[cyan]Pushing to GitHub...", total=None)
                retry_result = self.push(branch, force)
                if retry_result is True:
                    p2.update(t2, description="[green]Successfully pushed after pull!")
                    return True, f"Successfully pushed to GitHub ({branch} branch) after merging."
            return False, "Pull succeeded but push is still rejected. Please check for local uncommitted changes."

        if choice == "2":
            console.print("[dim]Force pushing (this will overwrite remote history)...[/dim]")
            with Progress(
                SpinnerColumn(), TextColumn("[progress.description]{task.description}"),
                console=console, transient=True,
            ) as p3:
                t3 = p3.add_task("[cyan]Force pushing...", total=None)
                force_result = self.push(branch, force=True)
                if force_result is True:
                    p3.update(t3, description="[green]Successfully force-pushed!")
                    return True, f"Successfully force-pushed to GitHub ({branch} branch)."
            return False, "Force push failed."

        return False, "Unrecognized option."

    def create_and_push(
        self,
        repo_url: str,
        force: bool = False,
        token: Optional[str] = None,
    ) -> Tuple[bool, str]:
        return self.push_to_github(repo_url, force=force, token=token)