"""
Detect command - Detect your project type and stack.

This module:
    - Scans the current directory for project files
    - Detects framework (React, Next.js, Vue, Angular, etc.)
    - Identifies package manager (npm, yarn, pnpm)
    - Shows build configuration
    - Allows navigation to different folders

✅ FIX: After selecting a new folder, detection naturally re-runs via the main loop
✅ FIX: No recursive function calls — clean stack
✅ FIX: Native OS folder picker integration
✅ FIX: Proper handling of Ctrl+C and Ctrl+D
✅ FIX: No more screen-clearing — every action's output stays on screen,
         new output is appended below a rule separator instead of wiping
         the terminal and jumping back to the top on every redraw.
✅ FIX: Panels no longer expand to the full (sometimes huge) console width
         — capped so they stay visually consistent with the tables next
         to them, matching what navigation.py already did correctly.
"""

from __future__ import annotations

import os
import typer
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markup import escape
from rich import box

from opun8.core.detector import detect_project, ProjectInfo
from opun8.ui import messages as msg

console = Console()

# Panel() defaults to expand=True (fills console width), while Table()
# sizes to its own content. Without an explicit width, panels stretch to
# whatever the terminal reports — sometimes far wider than is readable,
# and inconsistent with the tables printed alongside them. Cap it.
MAX_PANEL_WIDTH = 78


def _panel_width() -> int:
    """Panel width capped to a readable max, but never wider than the terminal."""
    return min(console.width - 2, MAX_PANEL_WIDTH)


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _safe_prompt(
    message: str,
    choices: Optional[list] = None,
    default: str = "1",
) -> Optional[str]:
    """Prompt with graceful handling of Ctrl+C and Ctrl+Z/Ctrl+D."""
    try:
        from rich.prompt import Prompt
        if choices:
            return Prompt.ask(message, choices=choices, default=default, show_choices=False)
        return Prompt.ask(message, default=default)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        return None


# ──────────────────────────────────────────────────────────────
# MAIN DETECT COMMAND
# ──────────────────────────────────────────────────────────────

def detect() -> None:
    """Detect your project type and stack."""
    try:
        _show_detect_screen()
    except typer.Exit:
        raise
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Detection cancelled.[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print_exception()
        msg.error(
            f"Unexpected error: {e}",
            suggestion="Try again or run `opun8 help` for assistance.",
        )
        raise typer.Exit(1)


def _show_detect_screen() -> None:
    """
    Main detection screen with partner tone.

    ✅ FIX: The while loop naturally re-runs detection after folder change.
    ✅ FIX: Reruns are separated with a rule instead of clearing the
             screen, so prior output (and the user's own terminal
             scrollback) is never wiped out from under them.
    """
    first_pass = True
    while True:
        if not first_pass:
            console.print()
            console.rule("[dim]Re-scanning project[/dim]", style="dim")
        first_pass = False

        console.print()
        msg.detection_start()

        with msg.scanning_spinner():
            result = detect_project(".")

        if result.framework == "unknown" and not result.is_static:
            msg.no_project_detected()
            return

        _display_detection_results(result)
        action = _show_detect_menu(result)

        if action == "rescan":
            continue  # ✅ Re-runs detection naturally, appended below
        return


# ──────────────────────────────────────────────────────────────
# DISPLAY RESULTS
# ──────────────────────────────────────────────────────────────

def _display_detection_results(result: ProjectInfo) -> None:
    """Display detection results with partner tone."""
    console.print()
    console.print(Panel(
        f"[bold green]{msg._sym('hooray')} HOORAY! Everything looks perfect and healthy! {msg._sym('heart')}[/bold green]\n"
        f"[dim]{msg._emoji_or_empty('point_down')}Here's everything I found for us, partner — take a look:[/dim]",
        border_style="green",
        padding=(1, 2),
        width=_panel_width(),
    ))
    console.print()

    # Project Details Table
    table = Table(
        title=f"{msg._emoji_or_empty('clipboard')}Project Details",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table.add_column("Field", style="bold white", width=18, no_wrap=True)
    table.add_column("Value", style="white", no_wrap=False)

    project_name = result.metadata.get("name", Path.cwd().name)
    framework = result.framework or "Unknown"
    package_manager = result.package_manager or "Unknown"
    project_type = "Static HTML" if result.is_static else "Dynamic"

    framework_display = {
        "react": "React",
        "nextjs": "Next.js",
        "vue": "Vue",
        "angular": "Angular",
        "vite": "Vite",
        "nodejs": "Node.js",
        "django": "Django",
        "flask": "Flask",
        "fastapi": "FastAPI",
        "python": "Python",
        "static": "Static HTML",
        "unknown": "Unknown",
    }.get(framework, framework.capitalize())

    table.add_row(f"{msg._sym('folder')} Project Name", msg._escape_text(project_name))
    table.add_row(f"{msg._sym('box')} Framework", msg._escape_text(framework_display))
    table.add_row(f"{msg._sym('box')} Package Manager", msg._escape_text(package_manager))
    table.add_row(f"{msg._emoji_or_empty('clipboard')}Type", msg._escape_text(project_type))

    console.print(table)

    # Build Configuration Table
    console.print()
    table2 = Table(
        title=f"{msg._emoji_or_empty('hammer')}Build Configuration",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        show_lines=False,
        padding=(0, 1),
    )
    table2.add_column("Field", style="bold white", width=18, no_wrap=True)
    table2.add_column("Value", style="white", no_wrap=False)

    needs_build = result.needs_build
    build_command = result.build_command or "None"
    output_dir = result.output_dir or "."

    table2.add_row(
        f"{msg._emoji_or_empty('hammer')}Needs Build",
        f"{msg._sym('success')} Yes" if needs_build else f"{msg._sym('error')} No (static)"
    )
    table2.add_row(
        f"{msg._emoji_or_empty('clipboard')}Build Command",
        msg._escape_text(build_command)
    )
    table2.add_row(
        f"{msg._sym('folder')} Output Directory",
        msg._escape_text(output_dir)
    )

    build_folder_exists = f"{msg._sym('success')} Exists" if Path(output_dir).exists() else f"{msg._sym('error')} Not built yet"
    table2.add_row(f"{msg._sym('browse')} Build Folder", build_folder_exists)

    console.print(table2)
    console.print()


# ──────────────────────────────────────────────────────────────
# DETECT MENU
# ──────────────────────────────────────────────────────────────

def _show_detect_menu(result: ProjectInfo) -> str:
    """
    Show next steps menu after detection.

    Returns:
        "rescan" if folder changed (re-run detection)
        "done" if user selected an action
    """
    while True:
        console.print(Panel(
            f"[bold green]{msg._sym('point')} WHAT SHOULD WE DO NEXT, PARTNER? {msg._sym('smile')}[/bold green]\n\n"
            f"  [bold cyan]1[/] {msg._sym('rocket')}  [white]LAUNCH THIS WEBSITE TO THE INTERNET NOW![/white] [dim](Recommended)[/dim]\n"
            f"  [bold cyan]2[/] {msg._sym('browse')}  [white]Select a different project[/white]\n"
            f"  [bold cyan]3[/] {msg._sym('history')}  [white]View deployment history[/white]\n"
            f"  [bold cyan]4[/] {msg._sym('badge')}  [white]View badges[/white]\n"
            f"  [bold cyan]5[/] {msg._sym('door')}  [white]Close app[/white]\n\n"
            f"[green]{msg._sym('success')} STUCK OR NOT SURE? Just smash the ENTER key! {msg._sym('joy')}[/green]\n"
            f"[dim]   I'll go ahead and put your site live, partner! {msg._sym('party')}[/dim]",
            border_style="green",
            padding=(1, 2),
            width=_panel_width(),
        ))
        console.print()

        choice = _safe_prompt(
            f"[bold cyan]{msg._emoji_or_empty('arrow')}[/] Press a number or Enter",
            choices=["1", "2", "3", "4", "5"],
            default="1",
        )

        if choice is None:
            msg.goodbye()
            raise typer.Exit()

        if choice == "1":
            from opun8.commands.deploy import deploy
            deploy(detected_project=result)
            return "done"

        elif choice == "2":
            # ✅ FIX: Change folder, return "rescan" to re-run detection
            if _browse_and_change_folder():
                return "rescan"
            continue

        elif choice == "3":
            from opun8.commands.history import history
            history()
            console.print()
            console.print(f"[dim]{msg._sym('point')} Back to your project, partner —[/dim]")
            console.print()
            continue

        elif choice == "4":
            from opun8.commands.badges import badges
            badges()
            console.print()
            console.print(f"[dim]{msg._sym('point')} Back to your project, partner —[/dim]")
            console.print()
            continue

        else:
            msg.goodbye()
            raise typer.Exit()


# ──────────────────────────────────────────────────────────────
# FOLDER BROWSING
# ──────────────────────────────────────────────────────────────

def _browse_and_change_folder() -> bool:
    """
    Open the native OS folder picker and change to the selected folder.

    Returns:
        True if folder was selected and directory changed, False if cancelled.
    """
    console.print()
    console.print(Panel(
        f"[bold cyan]{msg._sym('browse')} Let's find your project, partner![/bold cyan]\n"
        f"[dim]The folder picker dialog will open — just select your project folder.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(),
    ))
    console.print()

    from opun8.services.navigation import browse_to_folder
    selected = browse_to_folder()

    if not selected:
        console.print(f"[dim]{msg._sym('smile')} All good — folder selection cancelled.[/dim]")
        return False

    os.chdir(selected)
    console.print()
    console.print(
        f"[green]{msg._sym('success')} Hopped into [cyan]{escape(str(selected))}[/cyan] "
        f"— let's see what we've got![/green]"
    )
    console.print()

    # ✅ FIX: Just return True, let the main loop handle re-running detection
    return True


def go_to_folder() -> None:
    """
    Interactive folder navigation to select a project, then run detection.
    """
    if _browse_and_change_folder():
        detect()


# ──────────────────────────────────────────────────────────────
# MODULE EXPORTS
# ──────────────────────────────────────────────────────────────

__all__ = [
    "detect",
    "go_to_folder",
]