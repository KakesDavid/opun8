"""
History command - View, manage, and redeploy past deployments.

This module provides:
    - View all deployment history with details
    - Select and redeploy previous deployments
    - Delete deployments from history (with platform cleanup option)
    - Rename deployments (update the project name in history)
    - Track badge progress

Navigation model: the history list and the deployment-detail screen are each
a bounded `while True` loop. Sub-actions (redeploy/rename/delete) return
plain values to their caller instead of calling `_show_history_screen()` or
`_show_deployment_details()` again — so moving between screens never grows
the call stack, no matter how long the interactive session runs.
"""

from __future__ import annotations

import typer
import webbrowser
import re
import requests
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from opun8.services.deployment_history import (
    get_deployment_history,
    get_deployment,
    delete_deployment,
    update_deployment,
    get_deployment_count,
    get_badge_info,
    add_deployment,
    get_platform_icon,
)
from opun8.commands.badges import show_badge_notification
from opun8.ui import messages as msg
from opun8.auth import get_vercel_token
from opun8.providers.vercel.auth import get_vercel_scope
from opun8.providers.vercel.deploy import (
    deploy_to_vercel,
    rename_vercel_project,
    _sanitize_project_name,
)

# Render imports
from opun8.providers.render.auth import (
    get_render_token,
    is_render_authenticated,
    login_to_render,
    get_render_owner_id,
)
from opun8.providers.render.deploy import deploy_to_render

console = Console()

PANEL_WIDTH = 60
HISTORY_TABLE_DISPLAY_LIMIT = 30

# Platform icons mapping
PLATFORM_ICONS = {
    "vercel": "▲",
    "netlify": "📦",
    "render": "☁️",
}


# ──────────────────────────────────────────────────────────────
# HELPER: Safe prompt that handles Ctrl+C / Ctrl+Z (EOF)
# ──────────────────────────────────────────────────────────────

def _safe_prompt(
    message: str,
    choices: Optional[list] = None,
    default: Optional[str] = None,
    show_choices: bool = False,
) -> Optional[str]:
    """Prompt with graceful handling of Ctrl+C and Ctrl+Z/Ctrl+D. Returns
    None if the user cancels."""
    try:
        kwargs: Dict[str, Any] = {"show_choices": show_choices}
        if choices:
            kwargs["choices"] = choices
        if default is not None:
            kwargs["default"] = default
        return Prompt.ask(message, **kwargs)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        return None


def _safe_confirm(message: str, default: bool = True) -> Optional[bool]:
    """Confirm with graceful handling of Ctrl+C and Ctrl+Z/Ctrl+D. Returns
    None if the user cancels."""
    try:
        return Confirm.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        return None


def history() -> None:
    """
    View and manage deployment history.
    """
    try:
        _show_history_screen()
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Operation cancelled.[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print_exception()
        msg.error(
            f"Unexpected error: {e}",
            suggestion="Try again or run `opun8 help` for assistance.",
        )
        raise typer.Exit(1)


# ──────────────────────────────────────────────────────────────
# TOP-LEVEL HISTORY LIST SCREEN
# ──────────────────────────────────────────────────────────────

def _show_history_screen() -> None:
    """Main history list. Loops until the user chooses to go back."""
    while True:
        deployments = get_deployment_history()

        console.print()
        console.print(Panel(
            "[bold cyan]📜 Deployment History[/bold cyan]\n"
            "[dim]View, manage, and redeploy your past deployments.[/dim]",
            border_style="cyan",
            padding=(1, 2),
            width=PANEL_WIDTH,
        ))

        if not deployments:
            console.print()
            console.print("[yellow]No deployments found yet.[/yellow]")
            console.print("[dim]Run [cyan]opun8 deploy[/cyan] to create your first deployment.[/dim]")
            console.print()
            return

        count = get_deployment_count()
        badge = get_badge_info(count)
        console.print(f"[dim]🏅 Badge: {badge['emoji']} {badge['name']} ({count} deployments)[/dim]")
        console.print()

        _display_history_table(deployments)

        console.print()
        console.print("[dim]Enter a number to view deployment details, or [b] to go back.[/dim]")
        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            default="b",
            show_choices=False,
        )
        if choice is None:
            return

        if choice.lower() == "b":
            return

        try:
            idx = int(choice) - 1
        except ValueError:
            console.print("[red]Invalid input. Please enter a number.[/red]")
            continue

        if not (0 <= idx < len(deployments)):
            console.print("[red]Invalid selection.[/red]")
            continue

        # Runs its own loop and returns here when the user backs out,
        # whatever happened in between (rename, redeploy, delete).
        _show_deployment_details(deployments[idx])


def _display_history_table(deployments: List[Dict[str, Any]]) -> None:
    """Display the deployment history in a table."""
    table = Table(
        border_style="cyan",
        title_style="bold cyan",
        show_lines=True,
    )

    if len(deployments) > HISTORY_TABLE_DISPLAY_LIMIT:
        display_items = deployments[:HISTORY_TABLE_DISPLAY_LIMIT]
        table.title = f"Deployments (showing {HISTORY_TABLE_DISPLAY_LIMIT} of {len(deployments)})"
    else:
        display_items = deployments
        table.title = f"Deployments ({len(deployments)})"

    table.add_column("#", style="bold white", width=4)
    table.add_column("Project", style="bold white", width=20)
    table.add_column("Platform", style="dim", width=8)
    table.add_column("URL", style="cyan", width=25)
    table.add_column("Date", style="dim", width=15)

    for idx, deployment in enumerate(display_items, 1):
        project_name = deployment.get("project_name", "Unknown")[:20]
        platform = (deployment.get("platform") or "unknown").capitalize()
        url = deployment.get("url", "N/A")[:25]
        date_str = _format_relative_date(deployment.get("timestamp"))
        platform_icon = PLATFORM_ICONS.get(deployment.get("platform") or "", "●")

        table.add_row(str(idx), project_name, platform_icon + platform, url, date_str)

    console.print(table)


def _format_relative_date(timestamp: Optional[str]) -> str:
    if not timestamp:
        return "Unknown"
    try:
        dt = datetime.fromisoformat(timestamp)
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        time_diff = datetime.now() - dt
    except Exception:
        return "Unknown"

    total_seconds = time_diff.total_seconds()
    if total_seconds < 0:
        return "Just now"

    if total_seconds < 60:
        return "Just now"
    if total_seconds < 3600:
        minutes = int(total_seconds / 60)
        return f"{minutes}m ago"
    if time_diff.days < 1:
        hours = int(total_seconds / 3600)
        return f"{hours}h ago"
    if time_diff.days < 7:
        return f"{time_diff.days}d ago"
    return dt.strftime("%b %d")


# ──────────────────────────────────────────────────────────────
# DEPLOYMENT DETAIL SCREEN
# ──────────────────────────────────────────────────────────────

def _show_deployment_details(deployment: Dict[str, Any]) -> None:
    """
    Detail screen for a single deployment. Loops in place so rename/failed
    actions can redisplay fresh data without re-entering the history list;
    returns to the caller (the history loop) once the user backs out or the
    deployment is deleted.
    """
    current = deployment

    while True:
        deployment_id = current.get("id")
        if deployment_id:
            refreshed = get_deployment(deployment_id)
            if refreshed:
                current = refreshed

        _render_deployment_panel(current)

        folder_label = "Change project folder" if current.get("project_path") else "Set project folder"

        console.print("[bold]What would you like to do?[/bold]")
        console.print()
        console.print("  [bold cyan]1[/] 🚀  [white]Redeploy[/white]")
        console.print("  [bold cyan]2[/] ✏️  [white]Rename in history[/white]")
        console.print(f"  [bold cyan]3[/] 📁  [white]{folder_label}[/white]")
        console.print("  [bold cyan]4[/] 🗑️  [white]Delete from history[/white]  [dim](optionally from platform)[/dim]")
        console.print("  [bold cyan]5[/] 🔙  [white]Go back[/white]")
        console.print()

        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2", "3", "4", "5"],
            default="1",
            show_choices=False,
        )

        if choice is None or choice == "5":
            return
        elif choice == "1":
            _redeploy(current)
            return
        elif choice == "2":
            renamed = _rename_in_history(current)
            if renamed:
                current = renamed
        elif choice == "3":
            updated = _set_project_folder(current)
            if updated:
                current = updated
        elif choice == "4":
            if _delete_deployment(current):
                return


def _render_deployment_panel(deployment: Dict[str, Any]) -> None:
    """Render the info panel + badge status for one deployment."""
    console.print()

    project_name = deployment.get("project_name", "Unknown")
    platform = (deployment.get("platform") or "unknown").capitalize()
    url = deployment.get("url", "N/A")
    deployment_id = deployment.get("id", "N/A")
    env_vars = deployment.get("env_vars", [])
    status = deployment.get("status", "unknown")
    platform_icon = PLATFORM_ICONS.get(deployment.get("platform") or "", "●")

    timestamp = deployment.get("timestamp")
    date_display = "Unknown"
    if timestamp:
        try:
            date_display = datetime.fromisoformat(timestamp).strftime("%B %d, %Y at %I:%M %p")
        except Exception:
            date_display = timestamp

    project_path = deployment.get("project_path") or "Not tracked"

    console.print(Panel(
        f"[bold cyan]{platform_icon} {project_name}[/bold cyan]\n\n"
        f"[bold]Platform:[/bold] {platform}\n"
        f"[bold]URL:[/bold] [cyan]{url}[/cyan]\n"
        f"[bold]Deployment ID:[/bold] [dim]{deployment_id}[/dim]\n"
        f"[bold]Project folder:[/bold] [dim]{project_path}[/dim]\n"
        f"[bold]Date:[/bold] {date_display}\n"
        f"[bold]Status:[/bold] {status}\n"
        f"[bold]Environment Variables:[/bold] {', '.join(env_vars) if env_vars else 'None'}",
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))

    count = get_deployment_count()
    badge = get_badge_info(count)
    console.print()
    console.print(f"[dim]🏅 Badge: {badge['emoji']} {badge['name']} ({count} total deployments)[/dim]")
    if badge["next"]:
        remaining = badge["next"] - count
        console.print(
            f"[dim]   {remaining} more deployment(s) until "
            f"[cyan]{badge['emoji']} {badge['name']}[/cyan] upgrade.[/dim]"
        )
    console.print()


# ──────────────────────────────────────────────────────────────
# ENV FILE PARSING
# ──────────────────────────────────────────────────────────────

def _load_env_vars(project_path: Path) -> Dict[str, str]:
    """Load environment variables from a .env file, skipping bad lines."""
    env_vars: Dict[str, str] = {}
    env_file = project_path / ".env"

    if not env_file.exists():
        return env_vars

    try:
        with open(env_file, "r", encoding="utf-8") as f:
            for line_num, raw_line in enumerate(f, 1):
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                try:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if (value.startswith('"') and value.endswith('"')) or (
                        value.startswith("'") and value.endswith("'")
                    ):
                        value = value[1:-1]
                    env_vars[key] = value
                except Exception:
                    console.print(f"[yellow]⚠️  Skipped malformed line {line_num}: {raw_line.strip()}[/yellow]")
        if env_vars:
            console.print(f"[dim]📄 Loaded {len(env_vars)} environment variables.[/dim]")
    except Exception as e:
        console.print(f"[yellow]⚠️  Could not read .env file: {e}[/yellow]")

    return env_vars


# ──────────────────────────────────────────────────────────────
# REDEPLOY
# ──────────────────────────────────────────────────────────────

def _redeploy(deployment: Dict[str, Any]) -> None:
    """Redeploy a previous deployment to the correct platform."""
    console.print()
    console.print("[bold cyan]🚀 Redeploy[/bold cyan]")
    console.print(f"[dim]Redeploying: {deployment.get('project_name', 'Unknown')}[/dim]")
    console.print()

    project_path = _choose_redeploy_project_path(deployment)
    if project_path is None:
        console.print("[dim]Redeploy cancelled.[/dim]")
        return

    console.print()
    console.print(f"[dim]Project folder: [cyan]{project_path}[/cyan][/dim]")
    console.print("[dim]This will create a new deployment with the same settings.[/dim]")
    console.print()

    if not _safe_confirm("[bold]Continue with redeploy?[/bold]", default=True):
        return

    platform = deployment.get("platform") or "vercel"

    if platform == "vercel":
        _redeploy_vercel(deployment, project_path)
    elif platform == "render":
        _redeploy_render(deployment, project_path)
    elif platform == "netlify":
        console.print("[yellow]📦 Netlify redeploy coming soon![/yellow]")
        console.print("[dim]Please redeploy manually from the Netlify dashboard.[/dim]")
    else:
        console.print(f"[red]Unknown platform: {platform}[/red]")
        console.print("[dim]Please redeploy manually from the platform dashboard.[/dim]")


def _choose_redeploy_project_path(deployment: Dict[str, Any]) -> Optional[Path]:
    """
    Ask which local project folder this redeploy should use.
    """
    tracked_raw = deployment.get("project_path")
    tracked_path = Path(tracked_raw).expanduser() if tracked_raw else None
    tracked_valid = bool(tracked_path and tracked_path.is_dir())

    console.print("[bold]Which project folder should this redeploy use?[/bold]")
    console.print()

    if tracked_valid:
        console.print(f"  [bold cyan]1[/] 📁  [white]Use tracked project[/white]  [dim]({tracked_path})[/dim]")
        console.print("  [bold cyan]2[/] 📂  [white]Select a different project[/white]")
        console.print("  [bold cyan]3[/] 🔙  [white]Cancel[/white]")
        console.print()
        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2", "3"],
            default="1",
            show_choices=False,
        )
        if choice is None or choice == "3":
            return None
        if choice == "1":
            return tracked_path
        return _prompt_for_project_path()

    if tracked_raw:
        console.print(f"[yellow]⚠️  The originally tracked project folder no longer exists:[/yellow]")
        console.print(f"[dim]   {tracked_raw}[/dim]")
        console.print()
    else:
        console.print("[dim]This deployment was recorded before Opun8 tracked project folders.[/dim]")
        console.print()

    console.print("  [bold cyan]1[/] 📂  [white]Select a project folder[/white]")
    console.print("  [bold cyan]2[/] 🔙  [white]Cancel[/white]")
    console.print()
    choice = _safe_prompt(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2"],
        default="1",
        show_choices=False,
    )
    if choice is None or choice == "2":
        return None
    return _prompt_for_project_path()


def _prompt_for_project_path() -> Optional[Path]:
    """Prompt the user to select a project folder using the native folder dialog."""
    console.print()
    console.print("[dim]A file browser will open for you to select the folder.[/dim]")
    console.print()

    selected = msg.prompt_select_folder("Select project folder for this deployment")

    if selected is None:
        console.print("[dim]Folder selection cancelled.[/dim]")
        return None

    if not selected.exists():
        console.print(f"[red]❌ Path does not exist: {selected}[/red]")
        return None

    if not selected.is_dir():
        console.print(f"[red]❌ Not a directory: {selected}[/red]")
        return None

    return selected


# ──────────────────────────────────────────────────────────────
# SET / CHANGE PROJECT FOLDER
# ──────────────────────────────────────────────────────────────

def _set_project_folder(deployment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Manually set (or change) the local project folder recorded for a deployment."""
    console.print()
    console.print("[bold cyan]📁 Project Folder[/bold cyan]")
    current = deployment.get("project_path")
    console.print(f"[dim]Current: [cyan]{current or 'Not tracked'}[/cyan][/dim]")
    console.print()

    console.print("[dim]A file browser will open for you to select the folder.[/dim]")
    console.print()

    path = msg.prompt_select_folder("Select project folder for this deployment")

    if path is None:
        console.print("[dim]Cancelled.[/dim]")
        return None

    if current and str(path) == current:
        console.print("[yellow]No change made.[/yellow]")
        return None

    deployment_id = deployment.get("id")
    if not deployment_id:
        console.print("[red]Deployment ID not found.[/red]")
        return None

    updated = update_deployment(deployment_id, {"project_path": str(path)})
    if not updated:
        console.print("[red]Failed to update.[/red]")
        return None

    console.print(f"[green]✅ Project folder set to [cyan]{path}[/cyan][/green]")
    return updated


# ──────────────────────────────────────────────────────────────
# REDEPLOY: VERCEL
# ──────────────────────────────────────────────────────────────

def _redeploy_vercel(deployment: Dict[str, Any], project_path: Path) -> None:
    """Redeploy to Vercel using the existing project ID if available."""
    token = get_vercel_token()

    if not token:
        msg.error("Not connected to Vercel.", suggestion="Run `opun8 vercel` to connect.")
        return

    project_name = deployment.get("project_name") or project_path.name
    team_id = (get_vercel_scope() or {}).get("team_id")
    existing_project_id = deployment.get("project_id")

    console.print()
    console.print("[dim]Would you like to update environment variables?[/dim]")
    update_env = bool(_safe_confirm("[bold cyan]➜[/] Update env vars?", default=False))

    env_vars = _load_env_vars(project_path) if update_env else {}

    console.print()
    console.print("[dim]Deploying to Vercel...[/dim]")

    success, url, project_id = deploy_to_vercel(
        token=token,
        project_name=project_name,
        project_path=project_path,
        framework=None,
        env_vars=env_vars,
        team_id=team_id,
        existing_project_id=existing_project_id,
    )

    if not success:
        return

    result = add_deployment(
        project_name=project_name,
        url=url,
        platform="vercel",
        project_id=project_id,
        team_id=team_id,
        env_vars=list(env_vars.keys()) if env_vars else [],
        project_path=str(project_path),
    )

    console.print()
    console.print("[bold green]✅ Redeploy successful![/bold green]")
    console.print(f"[dim]🌐 https://{url}[/dim]")

    show_badge_notification(result.get("badge_unlocked"))

    console.print()
    if _safe_confirm("[bold]Open the new deployment?[/bold]", default=True):
        webbrowser.open(f"https://{url}")


# ──────────────────────────────────────────────────────────────
# REDEPLOY: RENDER
# ──────────────────────────────────────────────────────────────

def _redeploy_render(deployment: Dict[str, Any], project_path: Path) -> None:
    """Redeploy to Render using the existing service ID if available."""
    token = get_render_token()

    if not token:
        msg.error("Not connected to Render.", suggestion="Run `opun8 render` to connect.")
        return

    project_name = deployment.get("project_name") or project_path.name
    owner_id = get_render_owner_id()
    existing_service_id = deployment.get("project_id")

    console.print()
    console.print("[dim]Would you like to update environment variables?[/dim]")
    update_env = bool(_safe_confirm("[bold cyan]➜[/] Update env vars?", default=False))

    env_vars = _load_env_vars(project_path) if update_env else {}

    console.print()
    console.print("[dim]Deploying to Render...[/dim]")
    console.print("[dim]This may take a few minutes.[/dim]")

    success, url, service_id = deploy_to_render(
        token=token,
        project_name=project_name,
        project_path=project_path,
        framework=None,
        env_vars=env_vars,
        owner_id=owner_id,
        repo_url=None,
        region="oregon",
    )

    if not success:
        return

    # Update the existing deployment record with the new URL
    deployment_id = deployment.get("id")
    if deployment_id:
        update_deployment(deployment_id, {
            "url": url,
            "project_id": service_id,
            "timestamp": datetime.now().isoformat(),
            "status": "success",
        })

    result = add_deployment(
        project_name=project_name,
        url=url,
        platform="render",
        project_id=service_id,
        team_id=owner_id,
        env_vars=list(env_vars.keys()) if env_vars else [],
        project_path=str(project_path),
    )

    console.print()
    console.print("[bold green]✅ Redeploy successful![/bold green]")
    console.print(f"[dim]🌐 https://{url}[/dim]")

    show_badge_notification(result.get("badge_unlocked"))

    console.print()
    if _safe_confirm("[bold]Open the new deployment?[/bold]", default=True):
        webbrowser.open(f"https://{url}")


# ──────────────────────────────────────────────────────────────
# RENAME
# ──────────────────────────────────────────────────────────────

def _rename_in_history(deployment: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Rename a deployment.
    """
    console.print()
    console.print("[bold cyan]✏️ Rename Deployment[/bold cyan]")
    console.print(f"[dim]Current name: [cyan]{deployment.get('project_name', 'Unknown')}[/cyan][/dim]")
    console.print(f"[dim]Current URL:  [cyan]{deployment.get('url', 'N/A')}[/cyan][/dim]")
    console.print()

    raw_name = _safe_prompt("[bold cyan]➜[/] New project name")
    if not raw_name or not raw_name.strip():
        console.print("[yellow]Name cannot be empty.[/yellow]")
        return None

    platform = deployment.get("platform") or "vercel"

    if platform == "vercel":
        new_name = _sanitize_project_name(raw_name)
        if not new_name:
            console.print("[red]Invalid name. Use letters, numbers, dots, hyphens, or underscores.[/red]")
            return None
        if new_name != raw_name.strip():
            console.print(f"[dim]ℹ️  Vercel project names are lowercase letters/numbers/dots/hyphens only — using [cyan]{new_name}[/cyan][/dim]")
    else:
        new_name = re.sub(r'[^a-zA-Z0-9\s\-_]', '', raw_name).strip()
        if not new_name:
            console.print("[red]Invalid name. Only letters, numbers, spaces, hyphens, and underscores are allowed.[/red]")
            return None

    if deployment.get("project_name") == new_name:
        console.print("[yellow]No change made.[/yellow]")
        return None

    if not _safe_confirm(f"[bold]Rename to [cyan]{new_name}[/cyan]?[/bold]", default=True):
        return None

    deployment_id = deployment.get("id")
    if not deployment_id:
        console.print("[red]Deployment ID not found.[/red]")
        return None

    updates: Dict[str, Any] = {"project_name": new_name}

    if platform == "vercel":
        project_id = deployment.get("project_id")
        if not project_id:
            console.print(
                "[yellow]⚠️  No Vercel project ID on record for this deployment — "
                "can't rename it on Vercel, only in local history.[/yellow]"
            )
        else:
            token = get_vercel_token()
            if not token:
                msg.error("Not connected to Vercel.", suggestion="Run `opun8 vercel` to connect.")
                return None

            team_id = (get_vercel_scope() or {}).get("team_id")
            console.print("[dim]Renaming on Vercel...[/dim]")
            success, result = rename_vercel_project(token, project_id, new_name, team_id)
            if not success:
                console.print(f"[red]❌ {result}[/red]")
                console.print("[dim]Local history was left unchanged so it doesn't disagree with the live project.[/dim]")
                return None

            console.print("[green]✅ Renamed on Vercel.[/green]")
            updates["url"] = result

    updated = update_deployment(deployment_id, updates)
    if not updated:
        console.print("[red]Failed to rename.[/red]")
        return None

    console.print(f"[green]✅ Renamed to [cyan]{new_name}[/cyan][/green]")
    if "url" in updates:
        console.print(f"[green]🌐 New URL: [cyan]{updates['url']}[/cyan][/green]")
    return updated


# ──────────────────────────────────────────────────────────────
# DELETE
# ──────────────────────────────────────────────────────────────

def _delete_deployment(deployment: Dict[str, Any]) -> bool:
    """
    Delete a deployment from history and optionally from its platform.
    """
    console.print()
    console.print("[bold cyan]🗑️ Delete Deployment[/bold cyan]")
    console.print(f"[dim]Deleting: [cyan]{deployment.get('project_name', 'Unknown')}[/cyan][/dim]")
    console.print()

    console.print("[bold]Would you like to delete this deployment from the platform as well?[/bold]")
    console.print("[dim]This will remove it from Vercel/Netlify/Render.[/dim]")
    console.print()
    console.print("  [bold cyan]1[/] 🗑️  [white]Delete from history only[/white]")
    console.print("  [bold cyan]2[/] 🗑️  [white]Delete from history and platform[/white]")
    console.print("  [bold cyan]3[/] 🔙  [white]Cancel[/white]")
    console.print()

    choice = _safe_prompt(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2", "3"],
        default="1",
        show_choices=False,
    )

    if choice is None or choice == "3":
        return False

    delete_from_platform = choice == "2"
    if delete_from_platform:
        platform_display = (deployment.get("platform") or "vercel").capitalize()
        console.print(f"[yellow]⚠️  This will attempt to delete from {platform_display}.[/yellow]")
        console.print("[dim]Note: Some platforms require manual deletion via their dashboard.[/dim]")

    if not _safe_confirm("[bold]Are you sure you want to delete this deployment?[/bold]", default=True):
        return False

    deployment_id = deployment.get("id")
    if not deployment_id:
        console.print("[red]Failed to remove from history: this entry has no deployment ID.[/red]")
        return False

    if delete_from_platform:
        platform_deleted = _delete_from_platform(deployment)
        if not platform_deleted:
            proceed_anyway = _safe_confirm(
                "[bold]Platform deletion did not succeed. Remove this entry from local "
                "history anyway?[/bold] [dim](the project will still exist on the platform)[/dim]",
                default=False,
            )
            if not proceed_anyway:
                console.print("[dim]Keeping this entry in history so you can try again.[/dim]")
                return False

    if not delete_deployment(deployment_id):
        console.print("[red]Failed to remove from history: deployment not found (it may have already been deleted).[/red]")
        return False

    console.print("[green]✅ Deployment removed from history.[/green]")
    if not delete_from_platform:
        console.print("[dim]✅ Removed from history only.[/dim]")

    return True


def _delete_from_platform(deployment: Dict[str, Any]) -> bool:
    """
    Best-effort deletion of the underlying platform project.
    """
    platform = deployment.get("platform") or "vercel"

    if platform == "vercel":
        return _delete_from_vercel(deployment)
    elif platform == "render":
        return _delete_from_render(deployment)
    else:
        console.print("[yellow]⚠️  Automatic platform deletion not available for this platform.[/yellow]")
        console.print("[dim]Please delete manually from the platform dashboard.[/dim]")
        return False


def _delete_from_vercel(deployment: Dict[str, Any]) -> bool:
    """Delete a project from Vercel."""
    token = get_vercel_token()
    if not token:
        console.print("[yellow]⚠️  Not connected to Vercel — can't delete the project there.[/yellow]")
        console.print("[dim]Run `opun8 vercel` to connect, then try again.[/dim]")
        return False

    project_id = deployment.get("project_id")
    if not project_id:
        console.print("[yellow]⚠️  No Vercel project ID on record for this deployment — can't delete it automatically.[/yellow]")
        console.print("[dim]Please delete it manually from the Vercel dashboard.[/dim]")
        return False

    try:
        team_id = (get_vercel_scope() or {}).get("team_id")
        params = {"teamId": team_id} if team_id else {}

        response = requests.delete(
            f"https://api.vercel.com/v9/projects/{project_id}",
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=30,
        )

        if response.status_code == 200:
            console.print("[green]✅ Deployment deleted from Vercel.[/green]")
            return True
        elif response.status_code == 404:
            console.print("[yellow]⚠️  Project not found on Vercel (already deleted).[/yellow]")
            return True
        elif response.status_code in (401, 403):
            console.print(
                f"[red]⚠️  Vercel rejected the delete request ({response.status_code}) — "
                "your token may not have access to this project/team.[/red]"
            )
            return False
        else:
            console.print(f"[yellow]⚠️  Could not delete from Vercel: {response.text[:150]}[/yellow]")
            return False
    except requests.RequestException as e:
        console.print(f"[yellow]⚠️  Platform deletion error: {e}[/yellow]")
        return False


def _delete_from_render(deployment: Dict[str, Any]) -> bool:
    """Delete a service from Render."""
    token = get_render_token()
    if not token:
        console.print("[yellow]⚠️  Not connected to Render — can't delete the service there.[/yellow]")
        console.print("[dim]Run `opun8 render` to connect, then try again.[/dim]")
        return False

    service_id = deployment.get("project_id")
    if not service_id:
        console.print("[yellow]⚠️  No Render service ID on record for this deployment — can't delete it automatically.[/yellow]")
        console.print("[dim]Please delete it manually from the Render dashboard.[/dim]")
        return False

    from opun8.providers.render.deploy import delete_render_service

    return delete_render_service(token, service_id)