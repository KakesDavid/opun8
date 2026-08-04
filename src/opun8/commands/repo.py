"""
Repository deployment - Deploy GitHub repositories directly.

This module handles:
    - Cloning a GitHub repository to a temporary directory (for Vercel/Netlify)
    - Detecting the project type
    - Deploying to the selected platform (Vercel, Render, Netlify)
    - Cleaning up temporary files

For Render: the repo is still cloned locally first (so we can run project
detection and pick up a local .env file for convenience), but the actual
deployment itself is triggered from the GitHub URL rather than by uploading
local files.
For Vercel: we clone the repo and upload local files.
For Netlify: we clone the repo and upload local files.

Changelog:
✅ FIX: _clone_repository() returns resolved absolute path
✅ FIX: _clone_repository() now escapes Rich markup in git error messages
✅ FIX: _deploy_to_vercel() ensures path is resolved before deployment
✅ FIX: _deploy_to_netlify() ensures path is resolved before deployment
✅ FIX: Added debug logging to track file discovery
✅ FIX: Docstring no longer claims Render skips cloning entirely
✅ FIX: _load_env_vars() now checks multiple common env filenames and
        clearly warns that .env files are typically not committed
✅ FIX: _run_deployment() now handles "render" with a clear error message
✅ FIX: status is now set to "failed" when project detection fails
✅ FIX: repo_name is sanitized before being used to build filesystem paths
✅ FIX: _detect_project() now guards os.chdir() with a lock
"""

import logging
import os
import re
import shutil
import tempfile
import threading
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
from opun8.core.detector import detect_project, ProjectInfo
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

# Netlify imports
from opun8.providers.netlify.auth import (
    get_netlify_token,
    is_netlify_authenticated,
    login_to_netlify,
)
from opun8.providers.netlify.deploy import deploy_to_netlify

console = Console()
logger = logging.getLogger(__name__)

PANEL_WIDTH = 60

# Platforms that are fully implemented
LIVE_PLATFORMS = {"vercel", "render", "netlify"}

# Platforms that deploy from local files (as opposed to a bare GitHub URL)
LOCAL_FILE_PLATFORMS = {"vercel", "netlify"}

# Upcoming platforms (empty set)
UPCOMING_PLATFORMS: set[str] = set()

# Common env filenames to look for, in priority order (later files override
# earlier ones, matching the usual dotenv precedence convention).
ENV_FILE_CANDIDATES = (".env", ".env.local", ".env.production", ".env.production.local")

DeployStatus = Literal["success", "unsupported", "failed"]

# Guards os.chdir() in _detect_project so two concurrent calls in the same
# process can't race and detect the wrong directory's project type.
_detect_project_lock = threading.Lock()

# Anything outside this set gets stripped out of repo_name before it's used
# to build a filesystem path, to avoid path traversal / unexpected deletion.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_repo_name(repo_name: str) -> str:
    """
    Make repo_name safe to use as a single path component.

    Strips path separators, parent-directory references, and any other
    characters that aren't conservatively "filename-safe". This prevents a
    malicious or malformed repo_name (e.g. containing "../" or "/") from
    escaping the intended temp directory when building clone_path, and
    later being handed to shutil.rmtree during cleanup.
    """
    name = repo_name.strip().replace("\\", "/").split("/")[-1]
    name = _SAFE_NAME_RE.sub("_", name)
    name = name.lstrip(".") or "repo"
    return name


def _escape_rich_markup(text: str) -> str:
    """
    Escape square brackets so Rich doesn't interpret them as markup tags.

    ✅ FIX #1: Prevents MarkupError on clone failure messages containing
    brackets (e.g., "[email protected]", ref names, auth errors).
    """
    return str(text).replace("[", "(").replace("]", ")")


def deploy_repository(repo_url: str, repo_name: str, platform: str = "vercel") -> None:
    """
    Deploy a GitHub repository to the specified platform.

    Args:
        repo_url: The GitHub repository URL (e.g., https://github.com/user/repo).
        repo_name: The name of the repository.
        platform: The platform to deploy to (vercel, render, netlify).
    """
    safe_repo_name = _sanitize_repo_name(repo_name)

    project_path: Optional[Path] = None
    status: Optional[DeployStatus] = None
    project_info: Optional[ProjectInfo] = None

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

        # Step 1: Clone the repository.
        # We always clone locally, even for Render, so that we can run
        # project detection and optionally pick up a local .env file. Only
        # the *upload* step differs: Render deploys straight from the
        # GitHub URL, while Vercel/Netlify upload these local files.
        console.print("[bold]Step 1: Cloning repository[/bold]")
        console.print(f"[dim]Cloning from: {repo_url}[/dim]\n")

        project_path = _clone_repository(repo_url, safe_repo_name)
        if project_path is None:
            msg.error("Failed to clone repository.", suggestion="Check the URL and your internet connection.")
            status = "failed"
            return

        console.print(f"[green]✅ Cloned to: {project_path}[/green]\n")

        # Debug: Check if files exist after clone
        file_count = sum(1 for _ in project_path.rglob("*") if _.is_file())
        console.print(f"[dim]📁 Found {file_count} files in cloned repository[/dim]\n")

        # Step 2: Detect project type
        console.print("[bold]Step 2: Detecting project type[/bold]\n")
        project_info = _detect_project(project_path)
        if project_info is None:
            msg.error("Could not detect project type.", suggestion="Make sure the repository contains a valid project.")
            status = "failed"  # ✅ FIX #5: Set status so final banner appears
            return

        _show_project_summary(project_info)
        console.print()

        # Step 3: Deploy
        if platform == "render":
            # Render deploys directly from GitHub (no local file upload).
            # We still pass the cloned path along for detection and env vars.
            status = _run_render_deployment_from_github(
                repo_url, safe_repo_name, project_info, project_path
            )
        else:
            # Vercel and Netlify deploy from local files.
            status = _run_deployment(platform, project_info, project_path, safe_repo_name)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️ Operation cancelled.[/yellow]")
        raise typer.Exit(0)
    except Exception as exc:
        logger.exception("Unexpected error while deploying repository %s", repo_name)
        error_msg = _escape_rich_markup(exc)
        console.print(f"[red]Unexpected error: {error_msg}[/red]")
        status = "failed"
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
    project_info: ProjectInfo,
    project_path: Path,
    repo_name: str,
) -> DeployStatus:
    """
    Dispatch deployment to the requested LOCAL-FILE platform (vercel/netlify)
    and report the outcome.

    Note: this function intentionally does not handle "render" — that
    platform has its own upload-free flow in
    _run_render_deployment_from_github and is routed there directly by
    deploy_repository. If "render" (or anything else unexpected) ever
    reaches this function, that's a routing bug upstream, so we surface a
    clear error instead of silently reporting failure.

    ✅ FIX #4: "render" now produces a clear error message instead of silently failing.
    """
    console.print(f"[bold]Step 3: Deploying to {platform.capitalize()}[/bold]\n")

    if platform in UPCOMING_PLATFORMS:
        console.print(f"[yellow]⚠️ {platform.capitalize()} deployment is coming soon![/yellow]")
        return "unsupported"

    if platform not in LIVE_PLATFORMS:
        msg.error(f"Unknown platform: {platform}", suggestion="Choose one of: vercel, render, netlify.")
        return "failed"

    # ✅ FIX #4: Explicitly handle "render" with a clear error message
    if platform == "render":
        logger.error(
            "Platform 'render' reached _run_deployment() — this should not happen. "
            "It should be routed to _run_render_deployment_from_github() instead."
        )
        msg.error(
            "Internal routing error: Render was sent to the local-file deployment path.",
            suggestion="Please report this issue.",
        )
        return "failed"

    if platform == "vercel":
        success = _deploy_to_vercel(project_info, project_path, repo_name)
    else:  # platform == "netlify"
        success = _deploy_to_netlify(project_info, project_path, repo_name)

    return "success" if success else "failed"


def _run_render_deployment_from_github(
    repo_url: str,
    repo_name: str,
    project_info: ProjectInfo,
    project_path: Path,
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

        # Load environment variables from the cloned repo (best effort)
        # ✅ FIX #3: Clear warning about .env files being excluded from git
        env_vars = _load_env_vars(project_path)
        if env_vars:
            console.print(f"[dim]📄 Loaded {len(env_vars)} environment variables for Render.[/dim]")
        else:
            console.print(
                "[dim]ℹ️ No local .env file found (or it's excluded via .gitignore, "
                "as is typical). You can set env vars in the Render dashboard.[/dim]"
            )

        console.print()
        console.print("[bold]Step 3: Deploying to Render from GitHub[/bold]")
        console.print("[dim]☁️ This may take a few minutes.[/dim]\n")

        success, url, service_id = deploy_to_render(
            token=token,
            project_name=repo_name,
            project_path=project_path,
            framework=project_info.framework,
            owner_id=owner_id,
            repo_url=repo_url,
            region="oregon",
            output_dir=project_info.output_dir or ".",
            env_vars=env_vars,
        )

        if success:
            if not url:
                url = f"https://{repo_name}.onrender.com"
                _debug_log(f"URL was None, using constructed URL: {url}")

            _record_deployment_history(
                project_name=repo_name,
                url=url,
                project_id=service_id,
                team_id=owner_id,
                env_vars=list(env_vars.keys()) if env_vars else [],
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
            error_msg = _escape_rich_markup(str(url) if url else "Unknown error")
            console.print(f"[red]❌ Deployment failed: {error_msg}[/red]")
            return "failed"

    except Exception as exc:
        logger.exception("Error deploying %s to Render from GitHub", repo_name)
        error_msg = _escape_rich_markup(exc)
        console.print(f"[red]❌ Render deployment error: {error_msg}[/red]")
        return "failed"


def _clone_repository(repo_url: str, repo_name: str) -> Optional[Path]:
    """
    Clone a GitHub repository to a temporary directory.

    ✅ FIX: Returns resolved absolute path.
    ✅ FIX #1: Escapes Rich markup characters in git's error message before
            printing, since that message is not under our control and may
            legitimately contain "[" / "]" (e.g. in URLs, refs, or auth
            errors), which Rich would otherwise try to interpret as markup.

    Args:
        repo_name: Expected to already be sanitized (see _sanitize_repo_name)
            by the caller, since it's used directly as a path component.

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
            # ✅ FIX #1: Escape Rich markup in git error message
            safe_message = _escape_rich_markup(message)
            console.print(f"[red]❌ Clone failed: {safe_message}[/red]")
            return None

        cloned_ok = True
        # ✅ FIX: Return resolved absolute path
        return clone_path.resolve()

    except Exception as exc:
        logger.exception("Error cloning repository %s", repo_url)
        error_msg = _escape_rich_markup(exc)
        console.print(f"[red]❌ Clone error: {error_msg}[/red]")
        return None
    finally:
        if not cloned_ok:
            shutil.rmtree(temp_dir, ignore_errors=True)


def _detect_project(project_path: Path) -> Optional[ProjectInfo]:
    """
    Detect the project type in the cloned repository.

    ✅ FIX #7: os.chdir() mutates process-global state. A lock serializes
    access so that two concurrent calls to this function (e.g. from a
    future batch/async deploy flow) can't race and end up detecting the
    wrong directory's project type. This has no effect on today's
    single-threaded CLI usage but makes the function safe to reuse.
    """
    with _detect_project_lock:
        original_cwd = os.getcwd()

        try:
            os.chdir(project_path)
            with msg.scanning_spinner():
                result = detect_project(".")
        except Exception as exc:
            logger.exception("Error detecting project type at %s", project_path)
            error_msg = _escape_rich_markup(exc)
            console.print(f"[red]❌ Detection error: {error_msg}[/red]")
            return None
        finally:
            os.chdir(original_cwd)

    if result.framework == "unknown" and not result.is_static:
        return None

    return result


def _show_project_summary(project_info: ProjectInfo) -> None:
    """Print a summary of the detected project."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold white")
    table.add_column(style="white")

    fields = (
        ("Framework", project_info.framework or "Unknown"),
        ("Package Manager", project_info.package_manager or "Unknown"),
        ("Build Command", project_info.build_command or "Not found"),
        ("Output Directory", project_info.output_dir or "."),
    )
    for label, value in fields:
        table.add_row(label, str(value))

    console.print(table)


# ──────────────────────────────────────────────────────────────
# VERCEL DEPLOYMENT
# ──────────────────────────────────────────────────────────────

def _deploy_to_vercel(project_info: ProjectInfo, project_path: Path, repo_name: str) -> bool:
    """
    Deploy the project to Vercel and record the result in deployment history.

    ✅ FIX: Ensures path is resolved before deployment.
    ✅ FIX: Adds debug logging to track file discovery.
    """
    try:
        # ✅ FIX: Ensure path is resolved
        project_path = project_path.resolve()

        # Debug: Log files found
        files = list(project_path.rglob("*"))
        file_count = sum(1 for f in files if f.is_file())
        console.print(f"[dim]📁 Vercel: Found {file_count} files in {project_path}[/dim]")

        # Debug: Check for package.json
        package_json = project_path / "package.json"
        if package_json.exists():
            console.print("[dim]📦 package.json found[/dim]")
        else:
            console.print("[dim]⚠️ No package.json found[/dim]")

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
            framework=project_info.framework,
            env_vars=env_vars,
            team_id=team_id,
        )

        if not success:
            error_msg = _escape_rich_markup(str(url) if url else "Unknown error")
            console.print(f"[red]❌ Deployment failed: {error_msg}[/red]")
            return False

        # Handle None URL
        if not url:
            url = f"https://{repo_name}.vercel.app"
            _debug_log(f"URL was None, using constructed URL: {url}")

        _record_deployment_history(
            project_name=repo_name,
            url=url,
            project_id=project_id,
            team_id=team_id,
            env_vars=list(env_vars.keys()),
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
        error_msg = _escape_rich_markup(exc)
        console.print(f"[red]❌ Vercel deployment error: {error_msg}[/red]")
        return False


# ──────────────────────────────────────────────────────────────
# NETLIFY DEPLOYMENT
# ──────────────────────────────────────────────────────────────

def _deploy_to_netlify(project_info: ProjectInfo, project_path: Path, repo_name: str) -> bool:
    """
    Deploy the project to Netlify and record the result in deployment history.

    ✅ FIX: Ensures path is resolved before deployment.
    """
    try:
        # ✅ FIX: Ensure path is resolved
        project_path = project_path.resolve()

        if not is_netlify_authenticated():
            console.print("[yellow]You're not connected to Netlify yet.[/yellow]")
            login_to_netlify()
            if not is_netlify_authenticated():
                msg.error(
                    "Netlify authentication failed.",
                    suggestion="Run `opun8 netlify` to connect manually.",
                )
                return False

        token = get_netlify_token()
        if not token:
            msg.error("No Netlify token found.", suggestion="Run `opun8 netlify` to connect.")
            return False

        env_vars = _load_env_vars(project_path)

        console.print("[dim]☁️ Deploying to Netlify...[/dim]")
        console.print("[dim]This may take a moment.[/dim]\n")

        success, url, site_id = deploy_to_netlify(
            token=token,
            site_name=repo_name,
            project_path=project_path,
            env_vars=env_vars,
        )

        if not success:
            error_msg = _escape_rich_markup(str(url) if url else "Unknown error")
            console.print(f"[red]❌ Deployment failed: {error_msg}[/red]")
            return False

        # Handle None URL
        if not url:
            url = f"https://{repo_name}.netlify.app"
            _debug_log(f"URL was None, using constructed URL: {url}")

        _record_deployment_history(
            project_name=repo_name,
            url=url,
            project_id=site_id,
            team_id=None,
            env_vars=list(env_vars.keys()),
            platform="netlify",
        )

        live_url = url if url.startswith("http") else f"https://{url}"

        console.print()
        console.print(Panel(
            f"[bold green]✅ Deployment successful![/bold green]\n\n"
            f"[bold]🌐 {live_url}[/bold]\n\n"
            f"[dim]Your repository '{repo_name}' is now live on Netlify.[/dim]",
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
        logger.exception("Error deploying %s to Netlify", repo_name)
        error_msg = _escape_rich_markup(exc)
        console.print(f"[red]❌ Netlify deployment error: {error_msg}[/red]")
        return False


# ──────────────────────────────────────────────────────────────
# ENVIRONMENT VARIABLES
# ──────────────────────────────────────────────────────────────

def _load_env_vars(project_path: Path) -> Dict[str, str]:
    """
    Load environment variables from local env files, if any exist.

    ✅ FIX #3: Checks a small set of common env filenames (.env, .env.local,
    .env.production, .env.production.local) instead of only ".env", since
    real projects commonly split config across these. Later files in
    ENV_FILE_CANDIDATES override earlier ones, matching typical dotenv
    precedence.

    Important limitation (by design, not a bug): .env files are almost
    always excluded via .gitignore, which means a freshly cloned repo
    frequently won't have ANY of these files, even if the project needs
    env vars to run. When that happens we say so explicitly rather than
    silently reporting "0 env vars loaded" with no explanation, so users
    aren't misled into thinking their secrets made it over automatically.
    You may still need to configure env vars manually in the target
    platform's dashboard.
    """
    env_vars: Dict[str, str] = {}
    found_any_file = False

    for filename in ENV_FILE_CANDIDATES:
        env_file = project_path / filename
        if not env_file.exists():
            continue

        found_any_file = True
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                file_vars = 0
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip().strip('"').strip("'")
                    file_vars += 1
            if file_vars:
                console.print(f"[dim]📄 Loaded {file_vars} variable(s) from {filename}.[/dim]")
        except Exception as exc:
            error_msg = _escape_rich_markup(exc)
            console.print(f"[yellow]⚠️ Could not read {filename}: {error_msg}[/yellow]")

    if not found_any_file:
        console.print(
            "[dim]ℹ️ No .env file found in the cloned repo. This is expected if it's "
            "listed in .gitignore (the common case) — configure env vars in the "
            "target platform's dashboard if your app needs them.[/dim]"
        )

    return env_vars


# ──────────────────────────────────────────────────────────────
# DEPLOYMENT HISTORY
# ──────────────────────────────────────────────────────────────

def _record_deployment_history(
    project_name: str,
    url: str,
    project_id: Optional[str],
    team_id: Optional[str],
    env_vars: list[str],
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
            env_vars=env_vars,
        )
        badge_info = deployment_record.get("badge_unlocked")
        if badge_info:
            show_badge_notification(badge_info)
        return deployment_record
    except Exception as exc:
        logger.exception("Error recording deployment history for %s", project_name)
        error_msg = _escape_rich_markup(exc)
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
        error_msg = _escape_rich_markup(exc)
        console.print(f"[yellow]⚠️ Could not clean up: {error_msg}[/yellow]")


def _debug_log(message: str) -> None:
    """Log a debug message to the console."""
    console.print(f"[dim]🐛 {_escape_rich_markup(message)}[/dim]")