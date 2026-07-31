"""
Deploy command - Deploy your project to the cloud.

Orchestrates the full deployment flow:
    1. Detect the project
    2. Auto-build if needed
    3. Show platform-specific welcome and 4-option menu:
        a. Deploy Now
        b. Select Different Project
        c. Deploy GitHub Repo
        d. Exit
    4. Show cost estimate
    5. Deploy and report the result

Supported Platforms:
    - Vercel (Frontend, Next.js, React, etc.)
    - Netlify (Static sites, JAMstack)
    - Render (Full-stack, Python, Node.js)

Author: OPUN8 Team
Version: 0.1.6
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
from typing import Dict, Optional

import requests
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box
from rich.markup import escape

from opun8.auth import (
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
from opun8.ui.messages import (
    _sym,
    _emoji_or_empty,
    _escape_text,
    _safe_prompt,
    _safe_confirm,
    _safe_prompt_free,
    deploy_platform_start,
    deploy_platform_menu,
)

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

PLATFORM_DISPLAY_NAMES = {
    Platform.VERCEL: "Vercel",
    Platform.NETLIFY: "Netlify",
    Platform.RENDER: "Render",
}


@dataclass
class SuccessResult:
    """Result of a successful deployment."""
    url: str
    project_name: str
    platform: Platform
    project_id: Optional[str] = None


# =============================================================================
# DEBUG LOGGING
# =============================================================================

def _log_debug_exception(context: str, exc: Exception) -> None:
    """Log exception details to debug file."""
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
# PLAN DETECTION
# =============================================================================

def _get_vercel_plan() -> str:
    """Detect the user's Vercel plan from their account."""
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

        if plan == "enterprise":
            console.print("[dim]📊 Detected Vercel plan: [bold]Enterprise[/bold][/dim]")
            return "enterprise"

        if plan == "hobby":
            console.print("[dim]📊 Detected Vercel plan: [bold]Hobby[/bold] (free)[/dim]")
            return "hobby"

        is_hobby = user.get("isHobby", False)
        has_payment_method = user.get("hasPaymentMethod", False)

        if is_hobby or not has_payment_method:
            console.print("[dim]📊 Detected Vercel plan: [bold]Hobby[/bold] (free)[/dim]")
            return "hobby"

        console.print("[dim]📊 Detected Vercel plan: [bold]Pro[/bold][/dim]")
        return "pro"

    except Exception as e:
        console.print(f"[dim]⚠️ Could not detect Vercel plan: {escape(str(e))}[/dim]")
        return "hobby"


def _get_render_plan() -> str:
    """Detect the user's Render workspace tier."""
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
        console.print(f"[dim]⚠️ Could not detect Render tier: {escape(str(e))}[/dim]")
        return "individual"


def _get_netlify_plan() -> str:
    """Detect the user's Netlify plan from their account."""
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
        console.print(f"[dim]⚠️ Could not detect Netlify plan: {escape(str(e))}[/dim]")
        return "hobby"


# =============================================================================
# BUILD STEP
# =============================================================================

def _build_project(project_info: ProjectInfo) -> Optional[ProjectInfo]:
    """
    Run the build step for a (re)detected project and stamp the resulting
    output directory onto its metadata.

    Returns:
        The updated ProjectInfo, or None if the build failed (an error
        has already been printed to the console).
    """
    build_service = get_build_service()
    build_result = build_service.ensure_build()

    if not build_result["built"]:
        console.print()
        console.print(f"[red]{_sym('error')} Build failed. Please fix build errors and try again.[/red]")
        console.print(f"[dim]   Error: {escape(str(build_result.get('message', 'Unknown error')))}[/dim]")
        return None

    build_info = build_service.get_build_info()
    project_info.metadata["build_info"] = build_info
    project_info.metadata["output_dir"] = build_info.get("output_dir", ".")
    return project_info


# =============================================================================
# MAIN DEPLOY COMMAND
# =============================================================================

def deploy(
    platform_arg: Optional[str] = None,
    detected_project: Optional[ProjectInfo] = None,
) -> None:
    """
    Deploy your project to the cloud.

    If a platform is specified (netlify, vercel, render), skips the platform
    selection menu and goes directly to the 4-option deploy menu.
    """
    try:
        # Step 1: Detect or use provided project
        if detected_project:
            project_info = detected_project
            console.print()
            console.print(f"[bold green]{_sym('success')} Using previously detected project![/bold green]")
            console.print()
            _show_project_summary(project_info)
        else:
            project_info = _detect_project()
            if project_info is None:
                return

        # Step 2: Build if needed
        project_info = _build_project(project_info)
        if project_info is None:
            return

        # Step 3: Determine platform
        platform = None

        if platform_arg:
            # Platform specified via command line
            platform_lower = platform_arg.lower()
            if platform_lower == "vercel":
                platform = Platform.VERCEL
            elif platform_lower == "netlify":
                platform = Platform.NETLIFY
            elif platform_lower == "render":
                platform = Platform.RENDER
            else:
                msg.error(
                    f"Unknown platform: {platform_arg}",
                    suggestion="Supported platforms: vercel, netlify, render",
                )
                raise typer.Exit(1)

            # Show platform-specific welcome and 4-option menu
            _show_platform_deploy_menu(project_info, platform)

        else:
            # No platform specified — show platform selection first
            platform = _ask_platform()
            if platform is None:
                return

            # Then show 4-option menu
            _show_platform_deploy_menu(project_info, platform)

    except KeyboardInterrupt:
        console.print(f"\n[yellow]{_sym('warning')} Deployment cancelled.[/yellow]")
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
# PLATFORM DEPLOY MENU (4 Options)
# =============================================================================

def _show_platform_deploy_menu(project_info: ProjectInfo, platform: Platform) -> None:
    """
    Show the 4-option deploy menu for a specific platform.

    ✅ FIX: Now uses ui.messages.deploy_platform_start() and deploy_platform_menu()
    
    Options:
        1. Deploy Now
        2. Select Different Project
        3. Deploy GitHub Repo
        4. Exit
    """
    while True:
        # Show platform-specific welcome (from ui.messages)
        deploy_platform_start(platform.value)
        
        # Show project summary
        _show_project_summary(project_info)

        # Show 4 options and get user choice (from ui.messages)
        choice = deploy_platform_menu()
        
        # _safe_prompt raises Exit on cancel, so choice should never be None
        # but keep check for safety
        if choice is None:
            msg.goodbye()
            raise typer.Exit()

        if choice == "1":
            # Deploy Now
            _deploy_to_platform(project_info, platform)
            # After deployment attempt, return to menu
            continue

        elif choice == "2":
            # Select Different Project
            if _browse_and_change_folder():
                new_project = _detect_project()
                if new_project:
                    new_project = _build_project(new_project)
                    if new_project:
                        project_info = new_project
                        continue
                else:
                    console.print("[yellow]No project detected in the selected folder.[/yellow]")
                    continue
            else:
                console.print("[dim]Folder selection cancelled.[/dim]")
                continue

        elif choice == "3":
            # Deploy GitHub Repo
            _deploy_github_repo(platform)
            continue

        else:
            # Exit
            msg.goodbye()
            raise typer.Exit()


def _browse_and_change_folder() -> bool:
    """
    Open the native OS folder picker and change to the selected folder.

    Returns:
        True if folder was selected and directory changed, False if cancelled.
    """
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('browse')} Let's find your project, partner![/bold cyan]\n"
        f"[dim]The folder picker dialog will open — just select your project folder.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))
    console.print()

    from opun8.services.navigation import browse_to_folder
    selected = browse_to_folder()

    if not selected:
        console.print(f"[dim]{_sym('smile')} All good — folder selection cancelled.[/dim]")
        return False

    os.chdir(selected)
    console.print()
    console.print(
        f"[green]{_sym('success')} Hopped into [cyan]{escape(str(selected))}[/cyan] "
        f"— let's see what we've got![/green]"
    )
    console.print()
    return True


def _ensure_github_auth() -> Optional[str]:
    """
    Ensure the user is authenticated with GitHub and return the token.
    
    Returns:
        GitHub token if authenticated, None otherwise.
    """
    if not is_authenticated():
        console.print(f"[yellow]{_sym('warning')} You're not connected to GitHub yet.[/yellow]")
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

    return token


def _deploy_github_repo(platform: Platform) -> None:
    """
    Clone and deploy a GitHub repository.
    
    ✅ FIX: Uses _safe_prompt_free() for free-text input.
    """
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('clone')} Deploy GitHub Repo[/bold cyan]\n"
        f"[dim]{_emoji_or_empty('handshake')} Let's get a repo from GitHub and deploy it![/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))
    console.print()

    # Step 1: Ensure GitHub auth
    github_token = _ensure_github_auth()
    if github_token is None:
        console.print("[yellow]GitHub authentication required for this feature.[/yellow]")
        return

    # Step 2: Ask for GitHub repo URL
    # ✅ FIX: Use _safe_prompt_free() for free-text input
    repo_url = _safe_prompt_free(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Enter GitHub repository URL (e.g., https://github.com/user/repo)",
        default="",
    )

    if not repo_url or not repo_url.strip():
        console.print("[yellow]No repository URL provided. Returning to menu.[/yellow]")
        return

    repo_url = repo_url.strip()

    # Step 3: Ask for clone destination
    default_dest = Path.cwd() / "cloned_repo"
    # ✅ FIX: Use _safe_prompt_free() for free-text input
    dest_path = _safe_prompt_free(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Clone destination path",
        default=str(default_dest),
    )

    if not dest_path or not dest_path.strip():
        console.print("[yellow]No destination provided. Returning to menu.[/yellow]")
        return

    dest_path = dest_path.strip()

    dest = Path(dest_path).expanduser()

    # Warn before overwriting existing folder
    if dest.exists():
        console.print()
        console.print(
            f"[yellow]{_sym('warning')} '{escape(str(dest))}' already exists "
            f"and will be erased before cloning.[/yellow]"
        )
        confirm = _safe_confirm(
            f"{_emoji_or_empty('arrow')} Continue and overwrite it?",
            default=False,
        )
        if confirm is None or not confirm:
            console.print("[dim]Cancelled.[/dim]")
            return

    # Step 4: Clone the repo with GitHub token
    console.print()
    console.print(f"[dim]{_emoji_or_empty('clone')} Cloning repository...[/dim]")

    git_service = GitService()
    success, message = git_service.clone_repository(
        repo_url=repo_url,
        target_path=str(dest),
        token=github_token,
        depth=1,
    )

    if not success:
        console.print(f"[red]{_sym('error')} Failed to clone: {escape(message)}[/red]")
        return

    console.print(f"[green]{_sym('success')} {escape(message)}[/green]")

    # Step 5: Change to the cloned directory
    cloned_path = dest.resolve()
    if cloned_path.exists() and cloned_path.is_dir():
        os.chdir(cloned_path)
        console.print(f"[dim]{_emoji_or_empty('folder')} Changed to: {escape(str(cloned_path))}[/dim]")
        console.print()

        # Step 6: Detect the cloned project
        project_info = _detect_project()
        if project_info is None:
            console.print("[yellow]No project detected in the cloned repository.[/yellow]")
            return

        # Step 7: Build the cloned project
        project_info = _build_project(project_info)
        if project_info is None:
            return

        # Step 8: Deploy, passing the repo URL through
        _deploy_to_platform(project_info, platform, repo_url=repo_url)
    else:
        console.print(f"[red]{_sym('error')} Could not find cloned directory: {escape(str(cloned_path))}[/red]")


def _deploy_to_platform(
    project_info: ProjectInfo,
    platform: Platform,
    repo_url: Optional[str] = None,
) -> bool:
    """
    Show the cost estimate and deploy the project to the specified platform
    if the user confirms.

    Returns:
        True if a deployment attempt was made; False if the user backed out.
    """
    # Show cost estimate
    estimator = get_cost_estimator(project_info)

    if platform == Platform.VERCEL:
        plan = _get_vercel_plan()
        estimate = estimator.estimate_vercel(plan=plan)
    elif platform == Platform.NETLIFY:
        plan = _get_netlify_plan()
        estimate = estimator.estimate_netlify(plan=plan)
    elif platform == Platform.RENDER:
        plan = _get_render_plan()
        estimate = estimator.estimate_render(workspace_plan=plan)
    else:
        msg.error(f"Unknown platform: {platform.value}")
        return False

    if estimate:
        if not display_cost_estimate(estimate):
            console.print(f"[dim]{_emoji_or_empty('back')} Deployment cancelled.[/dim]")
            return False
        display_savings_tip(estimate)
    else:
        console.print(f"[yellow]{_sym('warning')} Could not generate cost estimate.[/yellow]")
        if not _safe_confirm(f"{_emoji_or_empty('rocket')} Continue with deployment?", default=True):
            console.print(f"[dim]{_emoji_or_empty('back')} Deployment cancelled.[/dim]")
            return False

    # Execute deployment
    # ✅ FIX: repo_url only passed to Render (Vercel/Netlify don't use it)
    if platform == Platform.VERCEL:
        _handle_vercel_deploy(project_info)
    elif platform == Platform.NETLIFY:
        _handle_netlify_deploy(project_info)
    elif platform == Platform.RENDER:
        _handle_render_deploy(project_info, repo_url)

    return True


# =============================================================================
# PROJECT DETECTION
# =============================================================================

def _detect_project() -> Optional[ProjectInfo]:
    """Detect the project type in the current directory."""
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
        console.print(f"[dim]{_emoji_or_empty('bulb')} Run [cyan]opun8 detect[/cyan] to see what I'm looking for.[/dim]")
        return None

    return result


def _show_project_summary(project_info: ProjectInfo) -> None:
    """Display a summary of the detected project."""
    console.print()
    console.print(f"[bold green]{_sym('success')} Project detected![/bold green]")
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
        table.add_row(label, escape(str(value)))

    console.print(table)
    console.print()


# =============================================================================
# PLATFORM SELECTION
# =============================================================================

def _ask_platform() -> Optional[Platform]:
    """Ask the user which platform to deploy to."""
    console.print()
    console.print(f"[bold]{_emoji_or_empty('question')} Which platform would you like to deploy to?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_emoji_or_empty('triangle')} [white]Vercel[/white]  [dim](Recommended for frontend)[/dim]")
    console.print(f"  [bold cyan]2[/] {_emoji_or_empty('box')} [white]Netlify[/white]  [dim](Great for static sites)[/dim]")
    console.print(f"  [bold cyan]3[/] {_emoji_or_empty('cloud')} [white]Render[/white]  [dim](Great for full-stack and Python)[/dim]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=list(PLATFORM_CHOICES.keys()),
        default="1",
    )

    # _safe_prompt raises Exit on cancel, so choice should never be None
    if choice is None:
        return None

    return PLATFORM_CHOICES.get(choice)


# =============================================================================
# VERCEL DEPLOYMENT
# =============================================================================

def _handle_vercel_deploy(project_info: ProjectInfo) -> None:
    """Deploy the project to Vercel."""
    try:
        console.print()
        console.print(f"[bold cyan]{_emoji_or_empty('triangle')} Vercel Deployment[/bold cyan]")
        console.print(f"[dim]{_emoji_or_empty('heart')} I'll deploy your project to Vercel, partner![/dim]")
        console.print()

        output_dir = project_info.metadata.get("output_dir", ".")
        console.print(f"[dim]{_emoji_or_empty('folder')} Output directory: [cyan]{escape(str(output_dir))}[/cyan][/dim]")
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
        console.print(f"[bold cyan]{_emoji_or_empty('rocket')} Deploying to Vercel...[/bold cyan]")
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
                platform=Platform.VERCEL,
            ))
        else:
            msg.error(
                url or "Deployment failed.",
                suggestion="Check your project for build errors and try again.",
            )

    except KeyboardInterrupt:
        console.print(f"\n[yellow]{_sym('warning')} Vercel deployment cancelled.[/yellow]")
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
    """Ensure the user is authenticated with Vercel."""
    if is_vercel_authenticated():
        return True

    console.print(f"[yellow]{_sym('warning')} You're not connected to Vercel yet.[/yellow]")
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

def _handle_netlify_deploy(project_info: ProjectInfo) -> None:
    """Deploy the project to Netlify."""
    try:
        console.print()
        console.print(f"[bold cyan]{_emoji_or_empty('box')} Netlify Deployment[/bold cyan]")
        console.print(f"[dim]{_emoji_or_empty('heart')} I'll deploy your project to Netlify, partner![/dim]")
        console.print()

        output_dir = project_info.metadata.get("output_dir", ".")
        console.print(f"[dim]{_emoji_or_empty('folder')} Output directory: [cyan]{escape(str(output_dir))}[/cyan][/dim]")
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
        console.print(f"[bold cyan]{_emoji_or_empty('rocket')} Deploying to Netlify...[/bold cyan]")
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
                platform=Platform.NETLIFY,
            ))
        else:
            msg.error(
                url or "Deployment failed.",
                suggestion="Check your project for build errors and try again.",
            )

    except KeyboardInterrupt:
        console.print(f"\n[yellow]{_sym('warning')} Netlify deployment cancelled.[/yellow]")
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
    """Ensure the user is authenticated with Netlify."""
    if is_netlify_authenticated():
        return True

    console.print(f"[yellow]{_sym('warning')} You're not connected to Netlify yet.[/yellow]")
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

def _handle_render_deploy(project_info: ProjectInfo, repo_url: Optional[str] = None) -> None:
    """Deploy the project to Render."""
    try:
        console.print()
        console.print(f"[bold cyan]{_emoji_or_empty('cloud')} Render Deployment[/bold cyan]")
        console.print(f"[dim]{_emoji_or_empty('heart')} I'll deploy your project to Render, partner![/dim]")
        console.print()

        output_dir = project_info.metadata.get("output_dir", ".")
        console.print(f"[dim]{_emoji_or_empty('folder')} Output directory: [cyan]{escape(str(output_dir))}[/cyan][/dim]")
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
        console.print(f"[bold cyan]{_emoji_or_empty('rocket')} Deploying to Render...[/bold cyan]")
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
                platform=Platform.RENDER,
            ))
        else:
            msg.error(
                url or "Deployment failed.",
                suggestion="Check your project for build errors and try again.",
            )

    except KeyboardInterrupt:
        console.print(f"\n[yellow]{_sym('warning')} Render deployment cancelled.[/yellow]")
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
    """Ensure the user is authenticated with Render."""
    if is_render_authenticated():
        return True

    console.print(f"[yellow]{_sym('warning')} You're not connected to Render yet.[/yellow]")
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
    """Save a successful deployment to local history."""
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
            f"[yellow]{_sym('warning')} Deployment succeeded, but couldn't be saved to history: {escape(str(exc))}[/yellow]"
        )
        return

    try:
        show_badge_notification(deployment_record.get("badge_unlocked"))
    except Exception as exc:
        console.print(f"[yellow]{_sym('warning')} Couldn't check badge progress: {escape(str(exc))}[/yellow]")


# =============================================================================
# SUCCESS SCREEN & POST-DEPLOY ACTIONS
# =============================================================================

def _show_success(result: SuccessResult) -> None:
    """Display the success screen with partner tone."""
    full_url = _normalize_url(result.url)

    console.print()
    console.print(Panel(
        f"[bold green]{_sym('party')} WE DID IT, PARTNER! {_sym('party')}[/bold green]\n\n"
        f"[bold]{_emoji_or_empty('globe')} {escape(full_url)}[/bold]\n\n"
        f"[dim]Your project '{escape(result.project_name)}' is now live![/dim]",
        border_style="green",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))
    console.print()

    # Only show rename option for Vercel deployments
    can_rename = result.platform == Platform.VERCEL and bool(result.project_id)

    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_emoji_or_empty('globe')} [white]Open website[/white]")
    console.print(f"  [bold cyan]2[/] {_emoji_or_empty('clipboard')} [white]Copy URL[/white]")
    if can_rename:
        console.print(f"  [bold cyan]3[/] {_emoji_or_empty('pencil')} [white]Rename URL[/white]  [dim](make it shorter)[/dim]")
        console.print(f"  [bold cyan]4[/] {_emoji_or_empty('door')} [white]Exit[/white]")
        choices = ["1", "2", "3", "4"]
    else:
        console.print(f"  [bold cyan]3[/] {_emoji_or_empty('door')} [white]Exit[/white]")
        choices = ["1", "2", "3"]
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=choices,
        default="1",
    )

    if choice is None:
        msg.goodbye()
        raise typer.Exit()

    if choice == "1":
        webbrowser.open(full_url)
        console.print(f"[dim]{_emoji_or_empty('globe')} Opened {escape(full_url)}[/dim]")
    elif choice == "2":
        _copy_to_clipboard(full_url)
    elif choice == "3" and can_rename:
        _rename_url_flow(result)
    else:
        msg.goodbye()
        raise typer.Exit()


def _rename_url_flow(result: SuccessResult) -> None:
    """Guide the user through renaming their deployment URL via Vercel API."""
    console.print()
    console.print(f"[bold cyan]{_emoji_or_empty('pencil')} Rename Your Deployment[/bold cyan]")
    console.print("[dim]Choose a shorter, cleaner name for your project.[/dim]")
    console.print()
    console.print(f"[dim]Current URL: [cyan]{escape(result.url)}[/cyan][/dim]")
    console.print()

    if not result.project_id:
        console.print(f"[red]{_sym('error')} Cannot rename: No project ID available.[/red]")
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

        sanitized_name = current_name.replace("-", "")
        # ✅ FIX: Use _safe_prompt_free() for free-text input
        new_name = _safe_prompt_free(
            f"[bold cyan]{_emoji_or_empty('arrow')}[/] Enter a new name",
            default=sanitized_name,
        )

        if not new_name or not new_name.strip():
            console.print("[dim]Skipping rename.[/dim]")
            return

        new_name = new_name.strip()
        new_name = re.sub(r'[^a-zA-Z0-9-]', '', new_name)
        new_name = new_name.lower().strip('-')

        if len(new_name) < 2:
            console.print(f"[red]{_sym('error')} Name must be at least 2 characters.[/red]")
            continue

        if len(new_name) > 30:
            console.print(f"[red]{_sym('error')} Name must be less than 30 characters.[/red]")
            continue

        if new_name == sanitized_name:
            console.print(f"[yellow]{_sym('warning')} Same as current name. Skipping rename.[/yellow]")
            return

        token = get_vercel_token()
        if not token:
            console.print(f"[red]{_sym('error')} Not connected to Vercel. Please run `opun8 vercel` first.[/red]")
            return

        team_id = (get_vercel_scope() or {}).get("team_id")

        console.print()
        console.print(f"[dim]Attempting rename to [cyan]{escape(new_name)}[/cyan]...[/dim]")

        confirm = _safe_confirm(
            f"[bold]Rename to [cyan]{escape(new_name)}[/cyan]?[/bold]",
            default=True
        )

        if confirm is None or not confirm:
            console.print("[dim]Skipping rename.[/dim]")
            return

        console.print("[dim]Renaming deployment...[/dim]")
        success, message = rename_vercel_project(token, result.project_id, new_name, team_id)

        if success:
            console.print()
            console.print(f"[bold green]{_sym('success')} Renamed successfully![/bold green]")
            console.print(f"[bold]{_emoji_or_empty('globe')} https://{escape(message)}[/bold]")
            console.print()
            console.print("[bold]What would you like to do?[/bold]")
            console.print()
            console.print(f"  [bold cyan]1[/] {_emoji_or_empty('globe')} [white]Open website[/white]")
            console.print(f"  [bold cyan]2[/] {_emoji_or_empty('clipboard')} [white]Copy URL[/white]")
            console.print(f"  [bold cyan]3[/] {_emoji_or_empty('door')} [white]Exit[/white]")
            console.print()

            choice = _safe_prompt(
                f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
                choices=["1", "2", "3"],
                default="1",
            )

            if choice == "1":
                webbrowser.open(f"https://{message}")
                console.print(f"[dim]{_emoji_or_empty('globe')} Opened https://{escape(message)}[/dim]")
            elif choice == "2":
                _copy_to_clipboard(f"https://{message}")
            else:
                msg.goodbye()
                raise typer.Exit()
            return

        console.print(f"[red]{_sym('error')} {escape(message)}[/red]")
        if attempt < max_attempts:
            console.print("[dim]Please try a different name.[/dim]")
            continue

        console.print(f"[red]{_sym('error')} Too many attempts. Skipping rename.[/red]")
        return

    console.print(f"[yellow]{_sym('warning')} Could not rename. Your current URL is still active.[/yellow]")
    console.print(f"[dim]{_emoji_or_empty('globe')} {escape(_normalize_url(result.url))}[/dim]")


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def _normalize_url(url: str) -> str:
    """Ensure a URL has a scheme."""
    if url and not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url or ""


def _copy_to_clipboard(url: str) -> None:
    """Copy a URL to the system clipboard."""
    if not HAS_CLIPBOARD:
        console.print(f"[dim]{_emoji_or_empty('clipboard')} {escape(url)}[/dim]")
        console.print("[yellow]⚠️ Install `pyperclip` for clipboard support: pip install pyperclip[/yellow]")
        return

    try:
        pyperclip.copy(url)
        console.print(f"[green]{_sym('success')} Copied: {escape(url)}[/green]")
    except Exception:
        console.print(f"[dim]{_emoji_or_empty('clipboard')} {escape(url)}[/dim]")
        console.print("[yellow]⚠️ Could not copy to clipboard. URL printed above.[/yellow]")