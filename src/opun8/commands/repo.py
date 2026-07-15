"""
Repository deployment - Deploy GitHub repositories directly.

This module handles:
    - Cloning a GitHub repository to a temporary directory (for Vercel)
    - Detecting the project type
    - Deploying to the selected platform (Vercel, Render)
    - Cleaning up temporary files

For Render: we deploy directly from the GitHub URL without cloning.
For Vercel: we clone the repo and upload local files.
"""

import logging
import os
import shutil
import tempfile
import webbrowser
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from opun8.auth import get_github_token
from opun8.commands.badges import show_badge_notification
from opun8.core.detector import ProjectDetector
from opun8.services.deployment_history import add_deployment
from opun8.services.git_service import GitService
from opun8.ui import messages as msg

# Vercel imports
from opun8.providers.vercel.auth import (
    get_vercel_scope,
    get_vercel_token,
    is_vercel_authenticated,
    login_to_vercel,
)
from opun8.providers.vercel.deploy import deploy_to_vercel

# Render imports
from opun8.providers.render.auth import (
    get_render_token,
    get_render_owner_id,
    is_render_authenticated,
    login_to_render,
    prompt_owner_selection,
)
from opun8.providers.render.deploy import deploy_to_render

console = Console()
logger = logging.getLogger(__name__)

PANEL_WIDTH = 60

# Platforms that are fully implemented
LIVE_PLATFORMS = {"vercel", "render"}
UPCOMING_PLATFORMS = {"netlify"}

DeployStatus = Literal["success", "unsupported", "failed"]


def deploy_repository(repo_url: str, repo_name: str, platform: str = "vercel") -> None:
    """
    Deploy a GitHub repository to the specified platform.

    Args:
        repo_url: The GitHub repository URL (e.g., https://github.com/user/repo).
        repo_name: The name of the repository.
        platform: The platform to deploy to (vercel, render, netlify).
    """
    project_path: Optional[Path] = None
    status: Optional[DeployStatus] = None

    try:
        console.print()
        console.print(Panel(
            f"[bold cyan]🚀 Deploying Repository[/bold cyan]\n"
            f"[dim]Repository: {repo_name}[/dim]\n"
            f"[dim]Platform: {platform.capitalize()}[/dim]",
            border_style="cyan",
            padding=(1, 2),
            width=PANEL_WIDTH,
        ))
        console.print()

        # For Render: skip cloning, deploy directly from GitHub
        if platform == "render":
            console.print("[bold]Step 1: Detecting project type from GitHub[/bold]\n")
            
            # We need to clone temporarily just to detect the project type
            console.print("[dim]Cloning temporarily for detection...[/dim]")
            project_path = _clone_repository(repo_url, repo_name)
            if project_path is None:
                msg.error("Failed to clone repository for detection.", suggestion="Check the URL and your internet connection.")
                return

            console.print(f"[green]✅ Cloned to: {project_path}[/green]\n")

            console.print("[bold]Step 2: Detecting project type[/bold]\n")
            project_info = _detect_project(project_path)
            if project_info is None:
                msg.error("Could not detect project type.", suggestion="Make sure the repository contains a valid project.")
                return

            _show_project_summary(project_info)
            console.print()

            # Deploy directly from GitHub (no local files)
            status = _run_render_deployment_from_github(repo_url, repo_name, project_info)

        else:
            # For Vercel and others: clone and deploy from local files
            console.print("[bold]Step 1: Cloning repository[/bold]")
            console.print(f"[dim]Cloning from: {repo_url}[/dim]\n")

            project_path = _clone_repository(repo_url, repo_name)
            if project_path is None:
                msg.error("Failed to clone repository.", suggestion="Check the URL and your internet connection.")
                return

            console.print(f"[green]✅ Cloned to: {project_path}[/green]\n")

            console.print("[bold]Step 2: Detecting project type[/bold]\n")
            project_info = _detect_project(project_path)
            if project_info is None:
                msg.error("Could not detect project type.", suggestion="Make sure the repository contains a valid project.")
                return

            _show_project_summary(project_info)
            console.print()

            status = _run_deployment(platform, project_info, project_path, repo_name)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Operation cancelled.[/yellow]")
        raise typer.Exit(0)
    except Exception as exc:
        logger.exception("Unexpected error while deploying repository %s", repo_name)
        error_msg = str(exc).replace("[", "(").replace("]", ")")
        console.print(f"[red]Unexpected error: {error_msg}[/red]")
        raise typer.Exit(1)
    finally:
        if project_path is not None:
            console.print()
            console.print("[bold]Step 4: Cleaning up[/bold]")
            _cleanup_temp_dir(project_path)

        if status == "success":
            console.print("[bold green]✅ Deployment complete![/bold green]")
        elif status == "unsupported":
            console.print(f"[yellow]⚠️ {platform.capitalize()} support is on the way — nothing was deployed yet.[/yellow]")
        elif status == "failed":
            console.print("[red]❌ Deployment failed.[/red]")


def _run_deployment(
    platform: str,
    project_info: Dict[str, Any],
    project_path: Path,
    repo_name: str,
) -> DeployStatus:
    """Dispatch deployment to the requested platform and report the outcome."""
    console.print(f"[bold]Step 3: Deploying to {platform.capitalize()}[/bold]\n")

    if platform in UPCOMING_PLATFORMS:
        console.print(f"[yellow]⚠️ {platform.capitalize()} deployment is coming soon![/yellow]")
        return "unsupported"

    if platform not in LIVE_PLATFORMS:
        msg.error(f"Unknown platform: {platform}", suggestion="Choose one of: vercel, render, netlify.")
        return "failed"

    if platform == "vercel":
        success = _deploy_to_vercel(project_info, project_path, repo_name)
    else:
        success = False

    return "success" if success else "failed"


def _run_render_deployment_from_github(
    repo_url: str,
    repo_name: str,
    project_info: Dict[str, Any],
) -> DeployStatus:
    """Deploy a GitHub repository directly to Render (no local files)."""
    try:
        if not is_render_authenticated():
            console.print("[yellow]You're not connected to Render yet.[/yellow]")
            login_to_render()
            if not is_render_authenticated():
                msg.error(
                    "Render authentication failed.",
                    suggestion="Run `opun8 render` to connect manually.",
                )
                return "failed"

        token = get_render_token()
        if not token:
            msg.error("No Render token found.", suggestion="Run `opun8 render` to connect.")
            return "failed"

        owner_id = get_render_owner_id()
        if not owner_id:
            owner_id = prompt_owner_selection(token)
            if owner_id is None:
                console.print("[yellow]No workspace selected. Using personal account.[/yellow]")

        console.print()
        console.print("[bold]Step 3: Deploying to Render from GitHub[/bold]")
        console.print("[dim]☁️ This may take a few minutes.[/dim]\n")

        success, url, service_id = deploy_to_render(
            token=token,
            project_name=repo_name,
            project_path=Path.cwd(),
            framework=project_info.get("framework"),
            owner_id=owner_id,
            repo_url=repo_url,
            region="oregon",
        )

        if success:
            if not url:
                url = f"https://{repo_name}.onrender.com"
                _debug_log(f"URL was None, using constructed URL: {url}")
            
            deployment_record = _record_deployment_history(
                project_name=repo_name,
                url=url,
                project_id=service_id,
                team_id=owner_id,
                env_vars={},
                platform="render",
            )

            live_url = url if url.startswith("http") else f"https://{url}"

            console.print()
            console.print(Panel(
                f"[bold green]✅ Deployment successful![/bold green]\n\n"
                f"[bold]🌐 {live_url}[/bold]\n\n"
                f"[dim]Your repository '{repo_name}' is now live on Render.[/dim]",
                border_style="green",
                padding=(1, 2),
                width=PANEL_WIDTH,
            ))
            console.print()

            try:
                if Confirm.ask("[bold]Open the website?[/bold]", default=True):
                    webbrowser.open(live_url)
            except (EOFError, KeyboardInterrupt):
                console.print("\n[yellow]⚠️ Skipped opening website.[/yellow]")

            return "success"
        else:
            error_msg = str(url) if url else "Unknown error"
            error_msg = error_msg.replace("[", "(").replace("]", ")")
            console.print(f"[red]❌ Deployment failed: {error_msg}[/red]")
            return "failed"

    except Exception as exc:
        logger.exception("Error deploying %s to Render from GitHub", repo_name)
        error_msg = str(exc).replace("[", "(").replace("]", ")")
        console.print(f"[red]❌ Render deployment error: {error_msg}[/red]")
        return "failed"


def _clone_repository(repo_url: str, repo_name: str) -> Optional[Path]:
    """
    Clone a GitHub repository to a temporary directory.

    Returns:
        The path to the cloned repository, or None if cloning failed.
    """
    temp_dir = Path(tempfile.mkdtemp(prefix="opun8_"))
    clone_path = temp_dir / repo_name
    cloned_ok = False

    try:
        token = get_github_token()

        git_service = GitService()
        success, message = git_service.clone_repository(
            repo_url=repo_url,
            target_path=str(clone_path),
            token=token,
        )

        if not success:
            console.print(f"[red]❌ Clone failed: {message}[/red]")
            return None

        cloned_ok = True
        return clone_path

    except Exception as exc:
        logger.exception("Error cloning repository %s", repo_url)
        error_msg = str(exc).replace("[", "(").replace("]", ")")
        console.print(f"[red]❌ Clone error: {error_msg}[/red]")
        return None
    finally:
        if not cloned_ok:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _detect_project(project_path: Path) -> Optional[Dict[str, Any]]:
    """Detect the project type in the cloned repository."""
    original_cwd = os.getcwd()

    try:
        os.chdir(project_path)
        detector = ProjectDetector()
        with msg.scanning_spinner():
            result = detector.detect()
    except Exception as exc:
        logger.exception("Error detecting project type at %s", project_path)
        error_msg = str(exc).replace("[", "(").replace("]", ")")
        console.print(f"[red]❌ Detection error: {error_msg}[/red]")
        return None
    finally:
        os.chdir(original_cwd)

    if not result.get("is_detected"):
        return None

    return result


def _show_project_summary(project_info: Dict[str, Any]) -> None:
    """Print a summary of the detected project."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold white")
    table.add_column(style="white")

    fields = (
        ("Type", "type", "Unknown"),
        ("Framework", "framework", "Unknown"),
        ("Package Manager", "package_manager", "Unknown"),
        ("Build Command", "build_command", "Not found"),
    )
    for label, key, default in fields:
        table.add_row(label, project_info.get(key, default))

    console.print(table)


# ──────────────────────────────────────────────────────────────
# VERCEL DEPLOYMENT
# ──────────────────────────────────────────────────────────────

def _deploy_to_vercel(project_info: Dict[str, Any], project_path: Path, repo_name: str) -> bool:
    """Deploy the project to Vercel and record the result in deployment history."""
    try:
        if not is_vercel_authenticated():
            console.print("[yellow]You're not connected to Vercel yet.[/yellow]")
            login_to_vercel()
            if not is_vercel_authenticated():
                msg.error(
                    "Vercel authentication failed.",
                    suggestion="Run `opun8 vercel` to connect manually.",
                )
                return False

        token = get_vercel_token()
        if not token:
            msg.error("No Vercel token found.", suggestion="Run `opun8 vercel` to connect.")
            return False

        team_id = (get_vercel_scope() or {}).get("team_id")
        env_vars = _load_env_vars(project_path)

        console.print("[dim]☁️ Deploying to Vercel...[/dim]")
        console.print("[dim]This may take a moment.[/dim]\n")

        success, url, project_id = deploy_to_vercel(
            token=token,
            project_name=repo_name,
            project_path=project_path,
            framework=project_info.get("framework"),
            env_vars=env_vars,
            team_id=team_id,
        )

        if not success:
            error_msg = str(url) if url else "Unknown error"
            error_msg = error_msg.replace("[", "(").replace("]", ")")
            console.print(f"[red]❌ Deployment failed: {error_msg}[/red]")
            return False

        deployment_record = _record_deployment_history(
            project_name=repo_name,
            url=url,
            project_id=project_id,
            team_id=team_id,
            env_vars=env_vars,
            platform="vercel",
        )

        live_url = url if url.startswith("http") else f"https://{url}"

        console.print()
        console.print(Panel(
            f"[bold green]✅ Deployment successful![/bold green]\n\n"
            f"[bold]🌐 {live_url}[/bold]\n\n"
            f"[dim]Your repository '{repo_name}' is now live on Vercel.[/dim]",
            border_style="green",
            padding=(1, 2),
            width=PANEL_WIDTH,
        ))
        console.print()

        try:
            if Confirm.ask("[bold]Open the website?[/bold]", default=True):
                webbrowser.open(live_url)
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]⚠️ Skipped opening website.[/yellow]")

        return True

    except Exception as exc:
        logger.exception("Error deploying %s to Vercel", repo_name)
        error_msg = str(exc).replace("[", "(").replace("]", ")")
        console.print(f"[red]❌ Vercel deployment error: {error_msg}[/red]")
        return False


# ──────────────────────────────────────────────────────────────
# ENVIRONMENT VARIABLES
# ──────────────────────────────────────────────────────────────

def _load_env_vars(project_path: Path) -> Dict[str, str]:
    """Load environment variables from a .env file if one exists."""
    env_file = project_path / ".env"
    env_vars: Dict[str, str] = {}

    if not env_file.exists():
        return env_vars

    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env_vars[key.strip()] = value.strip().strip('"').strip("'")

        if env_vars:
            console.print(f"[dim]📄 Loaded {len(env_vars)} environment variables.[/dim]")
    except Exception as exc:
        error_msg = str(exc).replace("[", "(").replace("]", ")")
        console.print(f"[yellow]⚠️ Could not read .env file: {error_msg}[/yellow]")

    return env_vars


# ──────────────────────────────────────────────────────────────
# DEPLOYMENT HISTORY
# ──────────────────────────────────────────────────────────────

def _record_deployment_history(
    project_name: str,
    url: str,
    project_id: Optional[str],
    team_id: Optional[str],
    env_vars: Dict[str, str],
    platform: str,
) -> Optional[Dict[str, Any]]:
    """
    Save deployment to history and show badge notification if unlocked.
    
    Returns:
        The deployment record, or None if saving failed.
    """
    try:
        deployment_record = add_deployment(
            project_name=project_name,
            url=url,
            platform=platform,
            project_id=project_id,
            team_id=team_id,
            env_vars=list(env_vars.keys()) if env_vars else [],
        )
        badge_info = deployment_record.get("badge_unlocked")
        if badge_info:
            show_badge_notification(badge_info)
        return deployment_record
    except Exception as exc:
        logger.exception("Error recording deployment history for %s", project_name)
        error_msg = str(exc).replace("[", "(").replace("]", ")")
        console.print(f"[yellow]⚠️ Couldn't save to history: {error_msg}[/yellow]")
        return None


# ──────────────────────────────────────────────────────────────
# CLEANUP
# ──────────────────────────────────────────────────────────────

def _cleanup_temp_dir(project_path: Path) -> None:
    """Remove the temporary directory a repository was cloned into."""
    try:
        temp_dir = project_path.parent
        if temp_dir.exists() and temp_dir.name.startswith("opun8_"):
            shutil.rmtree(temp_dir, ignore_errors=True)
            console.print("[dim]🧹 Cleaned up temporary files.[/dim]")
    except Exception as exc:
        logger.exception("Error cleaning up temp directory for %s", project_path)
        error_msg = str(exc).replace("[", "(").replace("]", ")")
        console.print(f"[yellow]⚠️ Could not clean up: {error_msg}[/yellow]")