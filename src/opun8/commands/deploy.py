"""
Deploy command - Deploy your project to the cloud.

Orchestrates the full deployment flow:
    1. Detect the project
    2. Auto-build if needed
    3. Show menu: Deploy with GitHub / Deploy without GitHub / Select different project
    4. Show cost estimate
    5. Deploy and report the result

Supported Platforms:
    - Vercel (Frontend, Next.js, React, etc.)
    - Netlify (Static sites, JAMstack)
    - Render (Full-stack, Python, Node.js)

Author: OPUN8 Team
Version: 0.1.5
"""

from __future__ import annotations

import datetime
import os
import re
import traceback
import webbrowser
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests
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
from opun8.commands.badges import show_badge_notification
from opun8.core.detector import ProjectInfo, detect_project
from opun8.services.build_service import get_build_service
from opun8.services.cost_estimator import get_cost_estimator
from opun8.services.deployment_history import add_deployment
from opun8.services.git_service import GitService
from opun8.ui import messages as msg
from opun8.ui.cost_display import display_cost_estimate, display_savings_tip

# =============================================================================
# PROVIDER IMPORTS
# =============================================================================

# Vercel
from opun8.providers.vercel.auth import (
    get_vercel_scope,
    get_vercel_token,
    is_vercel_authenticated,
    login_to_vercel,
)
from opun8.providers.vercel.deploy import deploy_to_vercel, rename_vercel_project

# Render
from opun8.providers.render.auth import (
    get_render_owner_id,
    get_render_token,
    is_render_authenticated,
    login_to_render,
    prompt_owner_selection,
)
from opun8.providers.render.deploy import deploy_to_render

# Netlify
from opun8.providers.netlify.auth import (
    get_netlify_token,
    is_netlify_authenticated,
    login_to_netlify,
)
from opun8.providers.netlify.deploy import deploy_to_netlify

# =============================================================================
# CLIPBOARD SUPPORT
# =============================================================================

try:
    import pyperclip
    HAS_CLIPBOARD = True
except ImportError:
    HAS_CLIPBOARD = False

# =============================================================================
# CONSTANTS
# =============================================================================

console = Console()
PANEL_WIDTH = 60
DEBUG_LOG_FILE = Path.home() / ".opun8" / "debug.log"


# =============================================================================
# PLATFORM DEFINITIONS
# =============================================================================

class Platform(str, Enum):
    """Supported deployment platforms."""
    VERCEL = "vercel"
    NETLIFY = "netlify"
    RENDER = "render"


PLATFORM_CHOICES: Dict[str, Platform] = {
    "1": Platform.VERCEL,
    "2": Platform.NETLIFY,
    "3": Platform.RENDER,
}

IMPLEMENTED_PLATFORMS = {Platform.VERCEL, Platform.NETLIFY, Platform.RENDER}


@dataclass
class SuccessResult:
    """Result of a successful deployment."""
    url: str
    project_name: str
    project_id: Optional[str] = None


# =============================================================================
# DEBUG LOGGING
# =============================================================================

def _log_debug_exception(context: str, exc: Exception) -> None:
    """
    Log exception details to debug file.

    Args:
        context: Description of where the error occurred
        exc: The exception to log
    """
    try:
        DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {context}\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            f.write("\n")
    except Exception:
        pass

    if os.environ.get("OPUN8_DEBUG"):
        console.print_exception()


# =============================================================================
# SAFE PROMPT HELPERS
# =============================================================================

def _safe_prompt(
    message: str,
    choices: Optional[list] = None,
    default: str = "1",
    show_choices: bool = False,
) -> Optional[str]:
    """
    Prompt user with graceful handling of Ctrl+C and Ctrl+Z.

    Args:
        message: The prompt message
        choices: Optional list of valid choices
        default: Default choice
        show_choices: Whether to show choices in prompt

    Returns:
        User's choice, or None if cancelled
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


def _safe_confirm(message: str, default: bool = True) -> Optional[bool]:
    """
    Confirm with user, handling Ctrl+C and Ctrl+Z.

    Args:
        message: The confirmation message
        default: Default response

    Returns:
        User's choice, or None if cancelled
    """
    try:
        from rich.prompt import Confirm
        return Confirm.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        return None


# =============================================================================
# PLAN DETECTION
# =============================================================================

def _get_vercel_plan() -> str:
    """
    Detect the user's Vercel plan from their account.

    Returns:
        "hobby", "pro", or "enterprise"
    """
    try:
        token = get_vercel_token()
        if not token:
            console.print("[dim]ℹ️ Not connected to Vercel. Assuming Hobby plan.[/dim]")
            return "hobby"

        response = requests.get(
            "https://api.vercel.com/v2/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )

        if response.status_code != 200:
            console.print("[dim]⚠️ Could not fetch Vercel plan. Assuming Hobby.[/dim]")
            return "hobby"

        data = response.json()
        user = data.get("user", {})
        billing = user.get("billing", {})
        plan = billing.get("plan", "").lower()

        # Explicit plan checks first
        if plan == "enterprise":
            console.print("[dim]📊 Detected Vercel plan: [bold]Enterprise[/bold][/dim]")
            return "enterprise"

        if plan == "hobby":
            console.print("[dim]📊 Detected Vercel plan: [bold]Hobby[/bold] (free)[/dim]")
            return "hobby"

        # Fallback heuristics
        is_hobby = user.get("isHobby", False)
        has_payment_method = user.get("hasPaymentMethod", False)

        if is_hobby or not has_payment_method:
            console.print("[dim]📊 Detected Vercel plan: [bold]Hobby[/bold] (free)[/dim]")
            return "hobby"

        console.print("[dim]📊 Detected Vercel plan: [bold]Pro[/bold][/dim]")
        return "pro"

    except Exception as e:
        console.print(f"[dim]⚠️ Could not detect Vercel plan: {e}[/dim]")
        return "hobby"


def _get_render_plan() -> str:
    """
    Detect the user's Render workspace tier.

    Returns:
        "individual", "team", "organization", or "enterprise"
    """
    try:
        token = get_render_token()
        if not token:
            console.print("[dim]ℹ️ Not connected to Render. Assuming Individual (free).[/dim]")
            return "individual"

        owner_id = get_render_owner_id()
        if not owner_id:
            return "individual"

        response = requests.get(
            f"https://api.render.com/v1/owners/{owner_id}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )

        if response.status_code != 200:
            console.print("[dim]⚠️ Could not fetch Render tier. Assuming Individual.[/dim]")
            return "individual"

        data = response.json()
        tier = data.get("type", "individual").lower()

        plan_mapping = {
            "individual": "individual",
            "team": "team",
            "organization": "organization",
            "enterprise": "enterprise",
        }

        plan = plan_mapping.get(tier, "individual")

        plan_display = {
            "individual": "Individual (free)",
            "team": "Team (Pro)",
            "organization": "Organization (Scale)",
            "enterprise": "Enterprise",
        }

        console.print(f"[dim]📊 Detected Render tier: [bold]{plan_display.get(plan, plan.capitalize())}[/bold][/dim]")
        return plan

    except Exception as e:
        console.print(f"[dim]⚠️ Could not detect Render tier: {e}[/dim]")
        return "individual"


def _get_netlify_plan() -> str:
    """
    Detect the user's Netlify plan from their account.

    Returns:
        "hobby", "personal", "pro", or "enterprise"
    """
    try:
        token = get_netlify_token()
        if not token:
            console.print("[dim]ℹ️ Not connected to Netlify. Assuming Hobby (free) plan.[/dim]")
            return "hobby"

        response = requests.get(
            "https://api.netlify.com/api/v1/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )

        if response.status_code != 200:
            console.print("[dim]⚠️ Could not fetch Netlify plan. Assuming Hobby.[/dim]")
            return "hobby"

        data = response.json()
        plan = data.get("plan", {}).get("name", "").lower()

        if not plan:
            subscription = data.get("subscription", {})
            plan = subscription.get("plan", {}).get("name", "").lower()

        plan_mapping = {
            "free": "hobby",
            "hobby": "hobby",
            "starter": "personal",
            "personal": "personal",
            "pro": "pro",
            "professional": "pro",
            "business": "pro",
            "enterprise": "enterprise",
        }

        mapped_plan = plan_mapping.get(plan, "hobby")

        plan_display = {
            "hobby": "Hobby (free)",
            "personal": "Personal ($9/month)",
            "pro": "Pro ($20/month)",
            "enterprise": "Enterprise (custom)",
        }

        console.print(f"[dim]📊 Detected Netlify plan: [bold]{plan_display.get(mapped_plan, mapped_plan.capitalize())}[/bold][/dim]")
        return mapped_plan

    except Exception as e:
        console.print(f"[dim]⚠️ Could not detect Netlify plan: {e}[/dim]")
        return "hobby"


# =============================================================================
# MAIN DEPLOY COMMAND
# =============================================================================

def deploy(
    platform_arg: Optional[str] = None,
    skip_github: bool = False,
    detected_project: Optional[ProjectInfo] = None,
) -> None:
    """
    Run the interactive deployment flow.

    Args:
        platform_arg: Optional platform to deploy to (vercel, netlify, render)
        skip_github: Whether to skip GitHub integration
        detected_project: Pre-detected project info (for reuse)
    """
    try:
        _print_welcome_banner()

        # Detect or use provided project
        if detected_project:
            project_info = detected_project
            console.print()
            console.print("[bold green]✅ Using previously detected project![/bold green]")
            console.print()
            _show_project_summary(project_info)
        else:
            project_info = _detect_project()
            if project_info is None:
                return

        # Build the project if needed
        build_service = get_build_service()
        build_result = build_service.ensure_build()

        if not build_result["built"]:
            console.print()
            console.print("[red]❌ Build failed. Please fix build errors and try again.[/red]")
            console.print(f"[dim]   Error: {build_result.get('message', 'Unknown error')}[/dim]")
            return

        build_info = build_service.get_build_info()
        project_info.metadata["build_info"] = build_info
        project_info.metadata["output_dir"] = build_info.get("output_dir", ".")

        # Proceed with deployment
        if skip_github:
            _deploy_without_github(project_info, platform_arg)
        else:
            _show_deploy_menu(project_info, platform_arg)

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Deployment cancelled.[/yellow]")
        console.print("[dim]Run `opun8 deploy` again when you're ready.[/dim]")
        raise typer.Exit(0)

    except typer.Exit:
        raise

    except Exception as exc:
        _log_debug_exception("deploy() unexpected error", exc)
        msg.error(
            f"Unexpected error: {exc}",
            suggestion="Check the error above and try again.",
        )
        raise typer.Exit(1)


# =============================================================================
# DEPLOY MENU
# =============================================================================

def _show_deploy_menu(project_info: ProjectInfo, platform_arg: Optional[str] = None) -> None:
    """
    Display the interactive deployment menu.
    """
    while True:
        console.print()
        console.print("[bold]🎉 Nice! Your project is ready. What would you like to do?[/bold]")
        console.print()
        console.print("  [bold cyan]1[/] 🚀  [white]Deploy this project (with GitHub)[/white]")
        console.print("  [bold cyan]2[/] ⏭️  [white]Deploy without GitHub[/white]")
        console.print("  [bold cyan]3[/] 📂  [white]Select a different project[/white]")
        console.print("  [bold cyan]4[/] 🚪  [white]Exit[/white]")
        console.print()

        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2", "3", "4"],
            default="1",
        )

        if choice is None:
            return

        if choice == "1":
            _deploy_with_github(project_info, platform_arg)
            return

        if choice == "2":
            _deploy_without_github(project_info, platform_arg)
            return

        if choice == "3":
            # Interactive folder browser using navigation service
            from opun8.services.navigation import browse_to_folder
            selected_path = browse_to_folder()
            if selected_path:
                os.chdir(selected_path)
                # Re-run deploy with detected project
                from opun8.commands.deploy import deploy as deploy_cmd
                deploy_cmd(platform_arg=platform_arg)
            return

        # Choice 4: Exit
        msg.goodbye()
        raise typer.Exit()


def _deploy_with_github(project_info: ProjectInfo, platform_arg: Optional[str] = None) -> None:
    """
    Deploy with GitHub push.
    """
    repo_url, cancelled = _handle_github_push(project_info)

    if repo_url is None:
        if cancelled:
            console.print("[dim]⏹️  GitHub push cancelled. Continuing without GitHub.[/dim]")
        else:
            console.print("[yellow]⚠️  GitHub push failed. Continuing without GitHub.[/yellow]")

    _continue_deploy(project_info, repo_url, platform_arg)


def _deploy_without_github(project_info: ProjectInfo, platform_arg: Optional[str] = None) -> None:
    """
    Deploy without GitHub push.
    """
    console.print("[dim]⏭️  Skipping GitHub push.[/dim]")
    _continue_deploy(project_info, None, platform_arg)


def _continue_deploy(
    project_info: ProjectInfo,
    repo_url: Optional[str],
    platform_arg: Optional[str] = None,
) -> None:
    """
    Continue with deployment after GitHub decision.
    """
    platform = _ask_platform(default_platform=platform_arg)
    if platform is None:
        return

    if platform not in IMPLEMENTED_PLATFORMS:
        msg.info(f"{platform.value.capitalize()} support is coming soon!")
        return

    # Show cost estimate
    estimator = get_cost_estimator(project_info)

    if platform == Platform.VERCEL:
        plan = _get_vercel_plan()
        estimate = estimator.estimate_vercel(plan=plan)
    elif platform == Platform.RENDER:
        plan = _get_render_plan()
        estimate = estimator.estimate_render(workspace_plan=plan)
    elif platform == Platform.NETLIFY:
        plan = _get_netlify_plan()
        estimate = estimator.estimate_netlify(plan=plan)
    else:
        msg.error(f"Unknown platform: {platform.value}")
        return

    # Confirm deployment
    if estimate:
        if not display_cost_estimate(estimate):
            console.print("[dim]Deployment cancelled.[/dim]")
            return
        display_savings_tip(estimate)
    else:
        console.print("[yellow]⚠️ Could not generate cost estimate.[/yellow]")
        if not _safe_confirm("[bold]Continue with deployment?[/bold]", default=True):
            console.print("[dim]Deployment cancelled.[/dim]")
            return

    # Execute deployment
    if platform == Platform.VERCEL:
        _handle_vercel_deploy(project_info, repo_url)
    elif platform == Platform.NETLIFY:
        _handle_netlify_deploy(project_info, repo_url)
    elif platform == Platform.RENDER:
        _handle_render_deploy(project_info, repo_url)


# =============================================================================
# UI HELPERS
# =============================================================================

def _print_welcome_banner() -> None:
    """Print the welcome banner."""
    console.print()
    console.print(Panel(
        "[bold cyan]🚀 Opun8 Deploy[/bold cyan]\n"
        "[dim]I'll guide you through deploying your project.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))


# =============================================================================
# PROJECT DETECTION
# =============================================================================

def _detect_project() -> Optional[ProjectInfo]:
    """
    Detect the project type in the current directory.

    Returns:
        ProjectInfo if detected, None otherwise
    """
    try:
        msg.detection_start()
        with msg.scanning_spinner():
            result = detect_project(".")
    except PermissionError:
        msg.error(
            "Permission denied reading this folder.",
            suggestion="Make sure you have read access to this directory.",
        )
        return None
    except Exception as exc:
        _log_debug_exception("_detect_project() unexpected error", exc)
        msg.error(
            f"Unexpected error while detecting project: {exc}",
            suggestion="Run `opun8 detect` to see more details.",
        )
        return None

    if result.framework == "unknown" and not result.is_static:
        msg.no_project_detected()
        console.print("[dim]💡 Run [cyan]opun8 detect[/cyan] to see what I'm looking for.[/dim]")
        return None

    return result


def _show_project_summary(project_info: ProjectInfo) -> None:
    """
    Display a summary of the detected project.
    """
    console.print()
    console.print("[bold green]✅ Project detected![/bold green]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold white")
    table.add_column(style="white")

    fields = (
        ("Name", project_info.metadata.get("name", Path.cwd().name)),
        ("Framework", project_info.framework or "Unknown"),
        ("Package Manager", project_info.package_manager or "Unknown"),
        ("Build Command", project_info.build_command or "Not found"),
        ("Output Directory", project_info.output_dir or "."),
        ("Needs Build", "✅ Yes" if project_info.needs_build else "❌ No"),
    )

    for label, value in fields:
        table.add_row(label, str(value))

    console.print(table)
    console.print()


# =============================================================================
# GITHUB INTEGRATION
# =============================================================================

def _sanitize_repo_name(name: str) -> str:
    """
    Sanitize a repository name for GitHub compatibility.

    Args:
        name: Raw repository name

    Returns:
        Sanitized name (lowercase, hyphens, no special chars)
    """
    name = name.replace(" ", "-")
    name = re.sub(r'[^a-zA-Z0-9\-_]', '', name)
    return name.lower()


def _handle_github_push(project_info: ProjectInfo) -> Tuple[Optional[str], bool]:
    """
    Authenticate with GitHub, create a repo, and push the project.

    Returns:
        (repo_url, cancelled)
        - repo_url: URL of the repository, or None if failed/cancelled
        - cancelled: True if user cancelled, False if actual failure
    """
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
            return None, False

        token = get_github_token()
        if not token:
            msg.error(
                "No GitHub token found.",
                suggestion="Run `opun8 github` to connect.",
            )
            return None, False

        username = get_authenticated_user()
        if not username:
            msg.error(
                "Could not get GitHub username.",
                suggestion="Run `opun8 github` to reconnect.",
            )
            return None, False

        default_name = project_info.metadata.get("name", Path.cwd().name)
        console.print()
        console.print(f"[bold]Repository name:[/bold] [cyan]{default_name}[/cyan]")
        console.print("[dim]Spaces will be replaced with hyphens for GitHub compatibility.[/dim]")

        raw_name = _safe_prompt("[bold cyan]➜[/] Repository name", default=default_name)
        if raw_name is None:
            return None, True

        repo_name = _sanitize_repo_name(raw_name)

        if repo_name != raw_name:
            console.print(f"[dim]ℹ️  Using sanitized name: [cyan]{repo_name}[/cyan][/dim]")

        console.print()
        console.print("[dim]📤 Creating repository and pushing code...[/dim]")

        repo_url = f"https://github.com/{username}/{repo_name}"
        git_service = GitService()
        success, message = git_service.push_to_github(repo_url, token=token)

        if success:
            msg.success(message)
            return repo_url, False

        if "nothing to commit" in message.lower():
            console.print("[dim]✅ No changes to commit — repository is already up to date.[/dim]")
            return repo_url, False

        msg.error(message)
        return None, False

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  GitHub push cancelled.[/yellow]")
        return None, True

    except Exception as exc:
        _log_debug_exception("_handle_github_push() unexpected error", exc)
        msg.error(
            f"GitHub push failed: {exc}",
            suggestion="Check your internet connection and try again.",
        )
        return None, False


# =============================================================================
# PLATFORM SELECTION
# =============================================================================

def _ask_platform(default_platform: Optional[str] = None) -> Optional[Platform]:
    """
    Ask the user which platform to deploy to.

    Args:
        default_platform: Optional platform to default to

    Returns:
        Selected Platform, or None if cancelled
    """
    console.print()
    console.print("[bold]Which platform would you like to deploy to?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] ▲  [white]Vercel[/white]  [dim](Recommended for frontend)[/dim]")
    console.print("  [bold cyan]2[/] 📦  [white]Netlify[/white]  [dim](Great for static sites)[/dim]")
    console.print("  [bold cyan]3[/] ☁️  [white]Render[/white]  [dim](Great for full-stack and Python)[/dim]")
    console.print()

    default_choice = "1"
    if default_platform:
        platform_lower = default_platform.lower()
        if platform_lower == "netlify":
            default_choice = "2"
        elif platform_lower == "render":
            default_choice = "3"

    choice = _safe_prompt(
        "[bold cyan]➜[/] Select an option",
        choices=list(PLATFORM_CHOICES.keys()),
        default=default_choice,
    )

    if choice is None:
        return None

    return PLATFORM_CHOICES.get(choice)


# =============================================================================
# VERCEL DEPLOYMENT
# =============================================================================

def _handle_vercel_deploy(project_info: ProjectInfo, repo_url: Optional[str]) -> None:
    """
    Deploy the project to Vercel.
    """
    try:
        console.print()
        console.print("[bold cyan]▲ Vercel Deployment[/bold cyan]")
        console.print("[dim]I'll deploy your project to Vercel.[/dim]")
        console.print()

        output_dir = project_info.metadata.get("output_dir", ".")
        console.print(f"[dim]📁 Output directory: [cyan]{output_dir}[/dim]")
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
        project_name = project_info.metadata.get("name", project_path.name)

        console.print()
        console.print("[bold cyan]☁️  Deploying to Vercel...[/bold cyan]")
        console.print("[dim]This may take a moment.[/dim]")
        console.print()

        success, url, project_id = deploy_to_vercel(
            token=token,
            project_name=project_name,
            project_path=project_path,
            framework=project_info.framework,
            team_id=team_id,
        )

        if success:
            _record_deployment_history(
                project_name=project_name,
                url=url,
                project_id=project_id,
                team_id=team_id,
                platform="vercel",
                env_vars=[],
            )

            _show_success(SuccessResult(
                url=url,
                project_name=project_name,
                project_id=project_id,
            ))
        else:
            msg.error(
                url or "Deployment failed.",
                suggestion="Check your project for build errors and try again.",
            )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Vercel deployment cancelled.[/yellow]")
        return

    except TimeoutError:
        msg.error(
            "Deployment timed out.",
            suggestion="Your project may be large or complex. Try again later.",
        )

    except typer.Exit:
        raise

    except Exception as exc:
        _log_debug_exception("_handle_vercel_deploy() unexpected error", exc)
        msg.error(
            f"Deployment failed: {exc}",
            suggestion="Check your internet connection and try again.",
        )


def _ensure_vercel_auth() -> bool:
    """
    Ensure the user is authenticated with Vercel.

    Returns:
        True if authenticated, False otherwise
    """
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


# =============================================================================
# NETLIFY DEPLOYMENT
# =============================================================================

def _handle_netlify_deploy(project_info: ProjectInfo, repo_url: Optional[str]) -> None:
    """
    Deploy the project to Netlify.
    """
    try:
        console.print()
        console.print("[bold cyan]📦 Netlify Deployment[/bold cyan]")
        console.print("[dim]I'll deploy your project to Netlify.[/dim]")
        console.print()

        output_dir = project_info.metadata.get("output_dir", ".")
        console.print(f"[dim]📁 Output directory: [cyan]{output_dir}[/dim]")
        console.print()

        if repo_url:
            console.print(f"[dim]ℹ️  GitHub repo: {repo_url}[/dim]")
            console.print("[dim]   Netlify will deploy from your local files directly.[/dim]")
            console.print()

        if not _ensure_netlify_auth():
            return

        token = get_netlify_token()
        if not token:
            msg.error(
                "No Netlify token found.",
                suggestion="Run `opun8 netlify` to connect.",
            )
            return

        project_path = Path.cwd()
        site_name = project_info.metadata.get("name", project_path.name)

        console.print()
        console.print("[bold cyan]☁️  Deploying to Netlify...[/bold cyan]")
        console.print("[dim]This may take a moment.[/dim]")
        console.print()

        success, url, site_id = deploy_to_netlify(
            token=token,
            site_name=site_name,
            project_path=project_path,
        )

        if success:
            _record_deployment_history(
                project_name=site_name,
                url=url,
                project_id=site_id,
                team_id=None,
                platform="netlify",
                env_vars=[],
            )

            _show_success(SuccessResult(
                url=url,
                project_name=site_name,
                project_id=site_id,
            ))
        else:
            msg.error(
                url or "Deployment failed.",
                suggestion="Check your project for build errors and try again.",
            )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Netlify deployment cancelled.[/yellow]")
        return

    except TimeoutError:
        msg.error(
            "Deployment timed out.",
            suggestion="Your project may be large or complex. Try again later.",
        )

    except typer.Exit:
        raise

    except Exception as exc:
        _log_debug_exception("_handle_netlify_deploy() unexpected error", exc)
        msg.error(
            f"Deployment failed: {exc}",
            suggestion="Check your internet connection and try again.",
        )


def _ensure_netlify_auth() -> bool:
    """
    Ensure the user is authenticated with Netlify.

    Returns:
        True if authenticated, False otherwise
    """
    if is_netlify_authenticated():
        return True

    console.print("[yellow]You're not connected to Netlify yet.[/yellow]")
    login_to_netlify()

    if is_netlify_authenticated():
        return True

    msg.error(
        "Netlify authentication failed.",
        suggestion="Run `opun8 netlify` to connect manually.",
    )
    return False


# =============================================================================
# RENDER DEPLOYMENT
# =============================================================================

def _handle_render_deploy(project_info: ProjectInfo, repo_url: Optional[str]) -> None:
    """
    Deploy the project to Render.
    """
    try:
        console.print()
        console.print("[bold cyan]☁️ Render Deployment[/bold cyan]")
        console.print("[dim]I'll deploy your project to Render.[/dim]")
        console.print()

        output_dir = project_info.metadata.get("output_dir", ".")
        console.print(f"[dim]📁 Output directory: [cyan]{output_dir}[/dim]")
        console.print()

        if repo_url:
            console.print(f"[dim]ℹ️  GitHub repo: {repo_url}[/dim]")
            console.print("[dim]   Render will deploy directly from GitHub.[/dim]")
            console.print()

        if not _ensure_render_auth():
            return

        token = get_render_token()
        if not token:
            msg.error(
                "No Render token found.",
                suggestion="Run `opun8 render` to connect.",
            )
            return

        owner_id = get_render_owner_id()
        if not owner_id:
            owner_id = prompt_owner_selection(token)
            if owner_id is None:
                console.print("[yellow]No workspace selected. Using personal account.[/yellow]")

        project_path = Path.cwd()
        project_name = project_info.metadata.get("name", project_path.name)

        console.print()
        console.print("[bold cyan]☁️  Deploying to Render...[/bold cyan]")
        console.print("[dim]This may take a few minutes.[/dim]")
        console.print()

        success, url, service_id = deploy_to_render(
            token=token,
            project_name=project_name,
            project_path=project_path,
            framework=project_info.framework,
            owner_id=owner_id,
            repo_url=repo_url,
            region="oregon",
            output_dir=output_dir,
        )

        if success:
            _record_deployment_history(
                project_name=project_name,
                url=url,
                project_id=service_id,
                team_id=owner_id,
                platform="render",
                env_vars=[],
            )

            _show_success(SuccessResult(
                url=url,
                project_name=project_name,
                project_id=service_id,
            ))
        else:
            msg.error(
                url or "Deployment failed.",
                suggestion="Check your project for build errors and try again.",
            )

    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Render deployment cancelled.[/yellow]")
        return

    except TimeoutError:
        msg.error(
            "Deployment timed out.",
            suggestion="Your project may be large or complex. Try again later.",
        )

    except typer.Exit:
        raise

    except Exception as exc:
        _log_debug_exception("_handle_render_deploy() unexpected error", exc)
        msg.error(
            f"Deployment failed: {exc}",
            suggestion="Check your internet connection and try again.",
        )


def _ensure_render_auth() -> bool:
    """
    Ensure the user is authenticated with Render.

    Returns:
        True if authenticated, False otherwise
    """
    if is_render_authenticated():
        return True

    console.print("[yellow]You're not connected to Render yet.[/yellow]")
    login_to_render()

    if is_render_authenticated():
        return True

    msg.error(
        "Render authentication failed.",
        suggestion="Run `opun8 render` to connect manually.",
    )
    return False


# =============================================================================
# DEPLOYMENT HISTORY
# =============================================================================

def _record_deployment_history(
    project_name: str,
    url: str,
    project_id: Optional[str],
    team_id: Optional[str],
    platform: str,
    env_vars: list[str],
) -> None:
    """
    Save a successful deployment to local history.
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
    except Exception as exc:
        console.print(
            f"[yellow]⚠️  Deployment succeeded, but couldn't be saved to history: {exc}[/yellow]"
        )
        return

    try:
        show_badge_notification(deployment_record.get("badge_unlocked"))
    except Exception as exc:
        console.print(f"[yellow]⚠️  Couldn't check badge progress: {exc}[/yellow]")


# =============================================================================
# SUCCESS SCREEN & POST-DEPLOY ACTIONS
# =============================================================================

def _show_success(result: SuccessResult) -> None:
    """
    Display the success screen and offer post-deploy actions.
    """
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
    console.print("  [bold cyan]3[/] ✏️  [white]Rename URL[/white]  [dim](make it shorter)[/dim]")
    console.print("  [bold cyan]4[/] 🏁  [white]Exit[/white]")
    console.print()

    choice = _safe_prompt(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2", "3", "4"],
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
    elif choice == "3":
        _rename_url_flow(result)
    else:
        msg.goodbye()
        raise typer.Exit()


def _rename_url_flow(result: SuccessResult) -> None:
    """
    Guide the user through renaming their deployment URL via Vercel API.
    """
    console.print()
    console.print("[bold cyan]✏️ Rename Your Deployment[/bold cyan]")
    console.print("[dim]Choose a shorter, cleaner name for your project.[/dim]")
    console.print()
    console.print(f"[dim]Current URL: [cyan]{result.url}[/cyan][/dim]")
    console.print()

    if not result.project_id:
        console.print("[red]❌ Cannot rename: No project ID available.[/red]")
        console.print("[dim]Please rename manually in the platform dashboard.[/dim]")
        return

    current_name = result.url.split('.')[0] if '.' in result.url else result.url
    max_attempts = 3
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        console.print(f"[dim]Attempt {attempt} of {max_attempts}[/dim]")
        console.print("[dim]Suggestions:[/dim]")
        console.print("[dim]  • Use your project name (e.g., my-portfolio)[/dim]")
        console.print("[dim]  • Keep it short (2-30 characters)[/dim]")
        console.print("[dim]  • Use letters, numbers, and hyphens only[/dim]")
        console.print("[dim]  • No spaces or special characters[/dim]")
        console.print()

        new_name = _safe_prompt(
            "[bold cyan]➜[/] Enter a new name",
            default=current_name.replace("-", "")
        )

        if new_name is None:
            console.print("[dim]Skipping rename.[/dim]")
            return

        new_name = re.sub(r'[^a-zA-Z0-9-]', '', new_name)
        new_name = new_name.lower().strip('-')

        if len(new_name) < 2:
            console.print("[red]❌ Name must be at least 2 characters.[/red]")
            continue

        if len(new_name) > 30:
            console.print("[red]❌ Name must be less than 30 characters.[/red]")
            continue

        if new_name == current_name:
            console.print("[yellow]⚠️  Same as current name. Skipping rename.[/yellow]")
            return

        token = get_vercel_token()
        if not token:
            console.print("[red]❌ Not connected to Vercel. Please run `opun8 vercel` first.[/red]")
            return

        team_id = (get_vercel_scope() or {}).get("team_id")

        console.print()
        console.print(f"[dim]Attempting rename to [cyan]{new_name}[/cyan]...[/dim]")

        confirm = _safe_confirm(
            f"[bold]Rename to [cyan]{new_name}[/cyan]?[/bold]",
            default=True
        )

        if confirm is None or not confirm:
            console.print("[dim]Skipping rename.[/dim]")
            return

        console.print("[dim]Renaming deployment...[/dim]")
        success, message = rename_vercel_project(token, result.project_id, new_name, team_id)

        if success:
            console.print()
            console.print(f"[bold green]✅ Renamed successfully![/bold green]")
            console.print(f"[bold]🌐 https://{message}[/bold]")
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

            if choice == "1":
                webbrowser.open(f"https://{message}")
                console.print(f"[dim]🌐 Opened https://{message}[/dim]")
            elif choice == "2":
                _copy_to_clipboard(f"https://{message}")
            else:
                msg.goodbye()
                raise typer.Exit()
            return

        console.print(f"[red]❌ {message}[/red]")
        if attempt < max_attempts:
            console.print("[dim]Please try a different name.[/dim]")
            continue

        console.print("[red]❌ Too many attempts. Skipping rename.[/red]")
        return

    console.print("[yellow]⚠️  Could not rename. Your current URL is still active.[/yellow]")
    console.print(f"[dim]🌐 {_normalize_url(result.url)}[/dim]")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _normalize_url(url: str) -> str:
    """
    Ensure a URL has a scheme.

    Args:
        url: The URL to normalize

    Returns:
        URL with https:// prefix if missing
    """
    if url and not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url or ""


def _copy_to_clipboard(url: str) -> None:
    """
    Copy a URL to the system clipboard.
    """
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