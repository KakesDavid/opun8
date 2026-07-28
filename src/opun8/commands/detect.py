"""
Detect command - Detect your project type and stack.

This command scans the current directory and identifies:
    - Project name
    - Framework (React, Next.js, Vue, etc.)
    - Package manager (npm, yarn, pnpm)
    - Build command
    - Output directory
    - Whether a build is needed

Usage:
    opun8 detect

Author: OPUN8 Team
Version: 0.1.4
"""

import os
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from opun8.core.detector import detect_project, ProjectInfo
from opun8.services.build_service import get_build_service
from opun8.ui import messages as msg


console = Console()


# ──────────────────────────────────────────────────────────────
# CORE IMPLEMENTATION
# ──────────────────────────────────────────────────────────────

def _run_detection() -> None:
    """
    Core detection logic.
    Always shows formatted output.
    """
    try:
        _print_header()

        # Detect the project
        with console.status("[bold cyan]🔍 Scanning project...[/bold cyan]"):
            project_info = detect_project(".")

        # Check if detection was successful
        if project_info.framework == "unknown" and not project_info.is_static:
            _show_no_project_detected()
            return

        # Get build service info
        build_service = get_build_service()
        build_info = build_service.get_build_info()

        # Always show formatted output
        _output_formatted(project_info, build_info)

    except PermissionError:
        msg.error(
            "Permission denied reading this folder.",
            suggestion="Make sure you have read access to this directory.",
        )
        raise typer.Exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Detection cancelled.[/yellow]")
        raise typer.Exit(0)
    except Exception as exc:
        msg.error(
            f"Unexpected error while detecting project: {exc}",
            suggestion="Try running from a different directory or check for broken files.",
        )
        raise typer.Exit(1)


# ──────────────────────────────────────────────────────────────
# TYPER COMMAND
# ──────────────────────────────────────────────────────────────

def detect() -> None:
    """
    Detect your project type and stack.

    This command scans the current directory and identifies:
        - Project name
        - Framework (React, Next.js, Vue, etc.)
        - Package manager (npm, yarn, pnpm)
        - Build command
        - Output directory
        - Whether a build is needed
    """
    _run_detection()


# ──────────────────────────────────────────────────────────────
# OUTPUT FUNCTIONS
# ──────────────────────────────────────────────────────────────

def _print_header() -> None:
    """Print the detection header."""
    console.print()
    console.print(Panel(
        "[bold cyan]🔍 Opun8 Project Detector[/bold cyan]\n"
        "[dim]I'll scan your current directory and identify your project type.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()


def _output_formatted(project_info: ProjectInfo, build_info: dict) -> None:
    """
    Display detection results in a formatted table.
    """
    console.print()
    console.print("[bold green]✅ Project detected![/bold green]")
    console.print()

    # ──────────────────────────────────────────────────────────────
    # Project Details Table
    # ──────────────────────────────────────────────────────────────

    table = Table(
        title="📋 Project Details",
        box=box.ROUNDED,
        title_style="bold cyan",
        border_style="cyan",
    )
    table.add_column("Field", style="bold white", width=20)
    table.add_column("Value", style="white")

    # Get project name from metadata or directory name
    project_name = project_info.metadata.get("name", Path.cwd().name)

    table.add_row("📁 Project Name", project_name)
    table.add_row("📦 Framework", project_info.framework.capitalize() if project_info.framework else "Unknown")

    if project_info.package_manager:
        table.add_row("📦 Package Manager", project_info.package_manager)
    else:
        table.add_row("📦 Package Manager", "[dim]None[/dim]")

    if project_info.is_static:
        table.add_row("📄 Type", "[dim]Static HTML[/dim]")
    else:
        table.add_row("📄 Type", "Application")

    console.print(table)
    console.print()

    # ──────────────────────────────────────────────────────────────
    # Build Configuration Table
    # ──────────────────────────────────────────────────────────────

    build_table = Table(
        title="🔨 Build Configuration",
        box=box.ROUNDED,
        title_style="bold yellow",
        border_style="yellow",
    )
    build_table.add_column("Field", style="bold white", width=20)
    build_table.add_column("Value", style="white")

    if project_info.needs_build:
        build_table.add_row("🛠️  Needs Build", "✅ Yes")
    else:
        build_table.add_row("🛠️  Needs Build", "❌ No (static or Python)")

    if project_info.build_command:
        build_table.add_row("📝 Build Command", f"[cyan]{project_info.build_command}[/cyan]")
    else:
        build_table.add_row("📝 Build Command", "[dim]None[/dim]")

    if project_info.dev_command:
        build_table.add_row("🔄 Dev Command", f"[cyan]{project_info.dev_command}[/cyan]")

    build_table.add_row("📁 Output Directory", f"[cyan]{project_info.output_dir}[/cyan]")

    # Check if build folder exists
    build_folder_exists = build_info.get("build_exists", False)
    if build_folder_exists:
        build_table.add_row("📂 Build Folder", "[green]✅ Exists[/green]")
    else:
        build_table.add_row("📂 Build Folder", "[yellow]❌ Not found (will be auto-created)[/yellow]")

    console.print(build_table)
    console.print()

    # ──────────────────────────────────────────────────────────────
    # Next Steps
    # ──────────────────────────────────────────────────────────────

    _show_next_steps(project_info)


def _show_no_project_detected() -> None:
    """Show message when no project is detected."""
    console.print()
    console.print("[yellow]⚠️  No project detected in this directory.[/yellow]")
    console.print()
    console.print("[dim]I looked for:[/dim]")
    console.print("  • [dim]package.json[/dim] [dim](Node.js/React/Next.js)[/dim]")
    console.print("  • [dim]requirements.txt[/dim] [dim](Python)[/dim]")
    console.print("  • [dim]app.py / main.py[/dim] [dim](Python/FastAPI)[/dim]")
    console.print("  • [dim]index.html[/dim] [dim](Static HTML)[/dim]")
    console.print()
    console.print("[dim]💡 Make sure you're in your project's root directory.[/dim]")


def _show_next_steps(project_info: ProjectInfo) -> None:
    """Show recommended next steps with clear, actionable guidance."""
    console.print()
    console.print("[bold]📋 Next Steps[/bold]")
    console.print()

    # Show project type-specific guidance
    if project_info.is_static:
        console.print("  [dim]1. Deploy your static site:[/dim]")
        console.print("     [cyan]  opun8 deploy vercel[/cyan]")
        console.print("     [cyan]  opun8 deploy render[/cyan]")

    elif project_info.needs_build:
        # Check if build folder exists
        build_folder_exists = (Path.cwd() / project_info.output_dir).exists()

        if build_folder_exists:
            console.print("  [dim]1. Deploy your project:[/dim]")
            console.print("     [cyan]  opun8 deploy vercel[/cyan]")
            console.print("     [cyan]  opun8 deploy render[/cyan]")
            console.print()
            console.print(f"  [dim]📁 Build folder: [cyan]{project_info.output_dir}[/cyan] (found!)[/dim]")
        else:
            console.print("  [dim]1. Build your project:[/dim]")
            console.print(f"     [cyan]  {project_info.build_command}[/cyan]")
            console.print()
            console.print("  [dim]2. Deploy your project:[/dim]")
            console.print("     [cyan]  opun8 deploy vercel[/cyan]")
            console.print("     [cyan]  opun8 deploy render[/cyan]")
            console.print()
            console.print(f"  [dim]📁 Output will be in: [cyan]{project_info.output_dir}[/cyan][/dim]")
            console.print("  [dim]💡 Opun8 will auto-build if you run [cyan]opun8 deploy[/cyan][/dim]")

    else:
        console.print("  [dim]1. Deploy your project directly:[/dim]")
        console.print("     [cyan]  opun8 deploy vercel[/cyan]")
        console.print("     [cyan]  opun8 deploy render[/cyan]")

    console.print()
    console.print("[dim]💡 Run [cyan]opun8 deploy[/cyan] to start the interactive deployment flow.[/dim]")
    console.print("[dim]📖 Run [cyan]opun8 help[/cyan] to see all available commands.[/dim]")


# ──────────────────────────────────────────────────────────────
# FOLDER SELECTION
# ──────────────────────────────────────────────────────────────

def go_to_folder() -> None:
    """
    Handle the "Select a different project" flow from the deploy menu.
    This opens a folder browser and re-runs detection.
    """
    from opun8.services.navigation import browse_to_folder

    folder = browse_to_folder()
    if folder:
        console.print(f"[dim]📂 Changed to: {folder}[/dim]")
        os.chdir(folder)
        _run_detection()
    else:
        console.print("[yellow]No folder selected. Returning to main menu.[/yellow]")


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "detect",
    "go_to_folder",
]