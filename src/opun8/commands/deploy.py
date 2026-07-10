"""
Deploy command - Deploy your project to the cloud.

Orchestrates the full deployment flow:
    1. Detect the project
    2. Optionally push it to GitHub (with auto-fix for common issues)
    3. Select a target platform
    4. Deploy and report the result
"""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from opun8.auth import (
    get_authenticated_user,
    get_github_token,
    is_authenticated,
    login_to_github,
)
from opun8.core.detector import ProjectDetector
from opun8.providers.vercel.auth import (
    get_vercel_scope,
    get_vercel_token,
    is_vercel_authenticated,
    login_to_vercel,
)
from opun8.providers.vercel.deploy import deploy_to_vercel
from opun8.services.git_service import GitService
from opun8.ui import messages as msg

try:
    import pyperclip
    HAS_CLIPBOARD = True
except ImportError:
    HAS_CLIPBOARD = False


console = Console()

PANEL_WIDTH = 60


class Platform(str, Enum):
    VERCEL = "vercel"
    NETLIFY = "netlify"
    RENDER = "render"


PLATFORM_CHOICES: Dict[str, Platform] = {
    "1": Platform.VERCEL,
    "2": Platform.NETLIFY,
    "3": Platform.RENDER,
}

IMPLEMENTED_PLATFORMS = {Platform.VERCEL}


@dataclass
class SuccessResult:
    """Result of a successful deployment, ready for display."""
    url: str
    project_name: str


# ──────────────────────────────────────────────────────────────
# HELPER: Safe prompt that handles Ctrl+C / Ctrl+Z
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
        else:
            return Prompt.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        return None


def _safe_confirm(message: str, default: bool = True) -> Optional[bool]:
    """
    Confirm with the user with graceful handling of Ctrl+C and Ctrl+Z.
    Returns None if the user cancels.
    """
    try:
        from rich.prompt import Confirm
        return Confirm.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        return None


# ──────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────

def deploy() -> None:
    """Run the interactive deploy flow."""
    try:
        _print_welcome_banner()

        project_info = _detect_project()
        if project_info is None:
            return

        _show_project_summary(project_info)

        repo_url = _maybe_push_to_github(project_info)

        platform = _ask_platform()
        if platform is None:
            return

        if platform not in IMPLEMENTED_PLATFORMS:
            msg.info(f"{platform.value.capitalize()} support is coming soon!")
            return

        _handle_vercel_deploy(project_info, repo_url)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Deployment cancelled.[/yellow]")
        console.print("[dim]Run `opun8 deploy` again when you're ready.[/dim]")
        raise typer.Exit(0)
    except Exception as exc:
        console.print_exception()
        msg.error(
            f"Unexpected error: {exc}",
            suggestion="Check the error above and try again.",
        )
        raise typer.Exit(1)


def _print_welcome_banner() -> None:
    console.print()
    console.print(Panel(
        "[bold cyan]🚀 Opun8 Deploy[/bold cyan]\n"
        "[dim]I'll guide you through deploying your project.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))


# ──────────────────────────────────────────────────────────────
# PROJECT DETECTION
# ──────────────────────────────────────────────────────────────

def _detect_project() -> Optional[Dict[str, Any]]:
    """Detect the project type in the current directory."""
    try:
        msg.detection_start()
        detector = ProjectDetector()
        with msg.scanning_spinner():
            result = detector.detect()
    except PermissionError:
        msg.error(
            "Permission denied reading this folder.",
            suggestion="Make sure you have read access to this directory.",
        )
        return None
    except Exception as exc:
        console.print_exception()
        msg.error(
            f"Unexpected error while detecting project: {exc}",
            suggestion="Run `opun8 detect` to see more details.",
        )
        return None

    if result.get("error"):
        msg.error(
            f"Found a package.json but couldn't read it: {result['error']}",
            suggestion="Check that package.json is valid JSON.",
        )
        return None

    if not result.get("is_detected"):
        msg.no_project_detected()
        console.print("[dim]💡 Run [cyan]opun8 detect[/cyan] to see what I'm looking for.[/dim]")
        return None

    return result


def _show_project_summary(project_info: Dict[str, Any]) -> None:
    """Print a summary table of the detected project."""
    console.print()
    console.print("[bold green]✅ Project detected![/bold green]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold white")
    table.add_column(style="white")

    fields = (
        ("Name", "name", "Unknown"),
        ("Type", "type", "Unknown"),
        ("Framework", "framework", "Unknown"),
        ("Package Manager", "package_manager", "Unknown"),
        ("Build Command", "build_command", "Not found"),
    )
    for label, key, default in fields:
        table.add_row(label, project_info.get(key, default))

    console.print(table)
    console.print()


# ──────────────────────────────────────────────────────────────
# GITHUB
# ──────────────────────────────────────────────────────────────

def _maybe_push_to_github(project_info: Dict[str, Any]) -> Optional[str]:
    """Ask whether to push to GitHub and do so if requested."""
    confirm = _safe_confirm(
        "Do you want to push this project to GitHub?\n"
        "[dim]This is recommended for version control and auto-deploy.[/dim]",
        default=True
    )
    
    if confirm is None:
        console.print("[dim]Skipping GitHub push.[/dim]")
        return None
    
    if not confirm:
        console.print("[dim]⏭️  Skipping GitHub push.[/dim]")
        return None

    repo_url = _handle_github_push(project_info)
    if repo_url is None:
        console.print("[yellow]⚠️  GitHub push failed. Continuing without GitHub.[/yellow]")
    return repo_url


def _sanitize_repo_name(name: str) -> str:
    """Sanitize repository name for GitHub compatibility."""
    import re
    name = name.replace(" ", "-")
    name = re.sub(r'[^a-zA-Z0-9\-_]', '', name)
    name = name.lower()
    return name


def _handle_github_push(project_info: Dict[str, Any]) -> Optional[str]:
    """Authenticate with GitHub, create a repo, and push the project."""
    try:
        console.print()
        console.print("[bold cyan]🔐 GitHub Authentication[/bold cyan]")
        console.print("[dim]I need access to create a repository and push your code.[/dim]")
        console.print()

        if not is_authenticated():
            console.print("[yellow]You're not connected to GitHub yet.[/yellow]")
            login_to_github()

        if not is_authenticated():
            msg.error(
                "GitHub authentication failed.",
                suggestion="Run `opun8 github` to connect manually.",
            )
            return None

        token = get_github_token()
        if not token:
            msg.error(
                "No GitHub token found.",
                suggestion="Run `opun8 github` to connect.",
            )
            return None

        username = get_authenticated_user()
        if not username:
            msg.error(
                "Could not get GitHub username.",
                suggestion="Run `opun8 github` to reconnect.",
            )
            return None

        default_name = project_info.get("name", Path.cwd().name)
        console.print()
        console.print(f"[bold]Repository name:[/bold] [cyan]{default_name}[/cyan]")
        console.print("[dim]Spaces will be replaced with hyphens for GitHub compatibility.[/dim]")
        
        raw_name = _safe_prompt("[bold cyan]➜[/] Repository name", default=default_name)
        if raw_name is None:
            return None
        
        repo_name = _sanitize_repo_name(raw_name)

        if repo_name != raw_name:
            console.print(f"[dim]ℹ️  Using sanitized name: [cyan]{repo_name}[/cyan][/dim]")

        console.print()
        console.print("[dim]📤 Creating repository and pushing code...[/dim]")

        repo_url = f"https://github.com/{username}/{repo_name}"
        
        # Retry logic for push
        max_retries = 2
        for attempt in range(max_retries + 1):
            if attempt > 0:
                console.print(f"[dim]Retry attempt {attempt} of {max_retries}...[/dim]")
            
            git_service = GitService()
            success, message = git_service.push_to_github(repo_url, token=token)
            
            if success:
                msg.success(message)
                return repo_url
            
            if "nothing to commit" in message.lower():
                console.print("[dim]✅ No changes to commit — repository is already up to date.[/dim]")
                return repo_url
            
            if "skipping github" in message.lower():
                return None
            
            if "repository not found" in message.lower():
                console.print("[red]Repository not found. Please check the name and try again.[/red]")
                return None
            
            if "already exists" in message.lower() or "rejected" in message.lower():
                console.print()
                console.print("[yellow]⚠️  Push was rejected — the repository may already have content.[/yellow]")
                console.print()
                console.print("[bold]What would you like to do?[/bold]")
                console.print()
                console.print("  [bold cyan]1[/] 🔄  [white]Try force push[/white]  [dim](overwrites remote)[/dim]")
                console.print("  [bold cyan]2[/] ⏭️  [white]Skip GitHub[/white]  [dim](continue without pushing)[/dim]")
                console.print("  [bold cyan]3[/] 📝  [white]Use a different name[/white]")
                console.print()
                
                choice = _safe_prompt(
                    "[bold cyan]➜[/] Select an option",
                    choices=["1", "2", "3"],
                    default="1",
                )
                
                if choice is None:
                    return None
                
                if choice == "2":
                    console.print("[dim]Skipping GitHub push.[/dim]")
                    return None
                
                if choice == "3":
                    new_name = _safe_prompt("[bold cyan]➜[/] Enter a new repository name")
                    if new_name:
                        new_name = _sanitize_repo_name(new_name)
                        repo_url = f"https://github.com/{username}/{new_name}"
                        console.print(f"[dim]Using new name: [cyan]{new_name}[/cyan][/dim]")
                        continue
                    else:
                        console.print("[dim]Skipping GitHub push.[/dim]")
                        return None
                
                if choice == "1":
                    console.print("[dim]Force pushing to GitHub...[/dim]")
                    success, message = git_service.push_to_github(repo_url, force=True, token=token)
                    if success:
                        msg.success(message + " (force push)")
                        return repo_url
                    else:
                        msg.error(message)
                        continue
            
            if attempt == max_retries:
                msg.error(
                    message,
                    suggestion="Check your internet connection, repository permissions, and try again.",
                )
                return None
            
            retry = _safe_prompt(
                "[bold cyan]➜[/] Retry?",
                choices=["y", "n"],
                default="y",
            )
            if retry is None or retry.lower() != "y":
                return None

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  GitHub push cancelled.[/yellow]")
        return None
    except Exception as exc:
        console.print_exception()
        msg.error(
            f"GitHub push failed: {exc}",
            suggestion="Check your internet connection and try again.",
        )
        return None


# ──────────────────────────────────────────────────────────────
# PLATFORM SELECTION
# ──────────────────────────────────────────────────────────────

def _ask_platform() -> Optional[Platform]:
    """Ask the user which platform to deploy to."""
    console.print()
    console.print("[bold]Which platform would you like to deploy to?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] ▲  [white]Vercel[/white]  [dim](Recommended for frontend)[/dim]")
    console.print("  [bold cyan]2[/] 📦  [white]Netlify[/white]  [dim](Coming soon)[/dim]")
    console.print("  [bold cyan]3[/] ☁️  [white]Render[/white]  [dim](Coming soon)[/dim]")
    console.print()

    choice = _safe_prompt(
        "[bold cyan]➜[/] Select an option",
        choices=list(PLATFORM_CHOICES.keys()),
        default="1",
    )
    
    if choice is None:
        return None
    
    return PLATFORM_CHOICES.get(choice)


# ──────────────────────────────────────────────────────────────
# VERCEL DEPLOYMENT
# ──────────────────────────────────────────────────────────────

def _handle_vercel_deploy(project_info: Dict[str, Any], repo_url: Optional[str]) -> None:
    """Authenticate with Vercel and deploy the project."""
    try:
        console.print()
        console.print("[bold cyan]▲ Vercel Deployment[/bold cyan]")
        console.print("[dim]I'll deploy your project to Vercel.[/dim]")
        console.print()

        if repo_url:
            console.print(f"[dim]ℹ️  GitHub repo: {repo_url}[/dim]")
            console.print("[dim]   (GitHub-linked deploys are coming soon — uploading directly for now)[/dim]")
            console.print()

        if not _ensure_vercel_auth():
            return

        token = get_vercel_token()
        if not token:
            msg.error(
                "No Vercel token found.",
                suggestion="Run `opun8 vercel` to connect.",
            )
            return

        team_id = (get_vercel_scope() or {}).get("team_id")
        project_path = Path.cwd()
        env_vars = _load_env_vars(project_path)

        console.print()
        console.print("[bold cyan]☁️  Deploying to Vercel...[/bold cyan]")
        console.print("[dim]This may take a moment.[/dim]")
        console.print()

        success, result = deploy_to_vercel(
            token=token,
            project_name=project_info.get("name", project_path.name),
            project_path=project_path,
            framework=project_info.get("framework"),
            env_vars=env_vars,
            team_id=team_id,
        )

        if success:
            _show_success(SuccessResult(url=result, project_name=project_info.get("name", project_path.name)))
        else:
            msg.error(
                result or "Deployment failed.",
                suggestion="Check your project for build errors and try again.",
            )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Vercel deployment cancelled.[/yellow]")
    except TimeoutError:
        msg.error(
            "Deployment timed out.",
            suggestion="Your project may be large or complex. Try again later.",
        )
    except Exception as exc:
        console.print_exception()
        msg.error(
            f"Deployment failed: {exc}",
            suggestion="Check your internet connection and try again.",
        )


def _ensure_vercel_auth() -> bool:
    if is_vercel_authenticated():
        return True

    console.print("[yellow]You're not connected to Vercel yet.[/yellow]")
    login_to_vercel()

    if is_vercel_authenticated():
        return True

    msg.error(
        "Vercel authentication failed.",
        suggestion="Run `opun8 vercel` to connect manually.",
    )
    return False


def _load_env_vars(project_path: Path) -> Dict[str, str]:
    """Load key/value pairs from a `.env` file, if present."""
    env_file = project_path / ".env"
    if not env_file.exists():
        return {}

    env_vars: Dict[str, str] = {}
    try:
        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip().strip('"').strip("'")
    except OSError as exc:
        console.print(f"[yellow]⚠️  Could not read .env file: {exc}[/yellow]")
        return {}

    if env_vars:
        keys = ", ".join(env_vars.keys())
        console.print(f"[dim]📄 Loaded {len(env_vars)} environment variable(s): {keys}[/dim]")

    return env_vars


# ──────────────────────────────────────────────────────────────
# SUCCESS / POST-DEPLOY ACTIONS
# ──────────────────────────────────────────────────────────────

def _show_success(result: SuccessResult) -> None:
    """Display the success screen and offer post-deploy actions."""
    full_url = _normalize_url(result.url)

    console.print()
    console.print(Panel(
        f"[bold green]🎉 Deployment successful![/bold green]\n\n"
        f"[bold]🌐 {full_url}[/bold]\n\n"
        f"[dim]Your project '{result.project_name}' is now live.[/dim]",
        border_style="green",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))
    console.print()

    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] 🌍  [white]Open website[/white]")
    console.print("  [bold cyan]2[/] 📋  [white]Copy URL[/white]")
    console.print("  [bold cyan]3[/] 🏁  [white]Exit[/white]")
    console.print()

    choice = _safe_prompt(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2", "3"],
        default="1",
    )
    
    if choice is None:
        msg.goodbye()
        raise typer.Exit()

    if choice == "1":
        webbrowser.open(full_url)
        console.print(f"[dim]🌐 Opened {full_url}[/dim]")
    elif choice == "2":
        _copy_to_clipboard(full_url)
    else:
        msg.goodbye()
        raise typer.Exit()


def _normalize_url(url: str) -> str:
    return url if url.startswith(("http://", "https://")) else f"https://{url}"


def _copy_to_clipboard(url: str) -> None:
    if not HAS_CLIPBOARD:
        console.print(f"[dim]📋 {url}[/dim]")
        console.print("[yellow]⚠️  Install `pyperclip` for clipboard support: pip install pyperclip[/yellow]")
        return

    try:
        pyperclip.copy(url)
        console.print(f"[green]✅ Copied: {url}[/green]")
    except Exception:
        console.print(f"[dim]📋 {url}[/dim]")
        console.print("[yellow]⚠️  Could not copy to clipboard. URL printed above.[/yellow]")