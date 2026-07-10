"""
UI messages for Opun8.
All user-facing messages in one place.
"""

import os
import shutil
from contextlib import contextmanager

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from opun8.auth import is_authenticated, get_authenticated_user

console = Console()


# ──────────────────────────────────────────────────────────────
# EMOJI / SYMBOL HANDLING
# ──────────────────────────────────────────────────────────────
# Some terminals (older Windows cmd.exe, SSH sessions, CI logs) and
# screen readers don't render emoji well. Set OPUN8_NO_EMOJI=1 to
# fall back to plain-text tags instead.

_NO_EMOJI = os.environ.get("OPUN8_NO_EMOJI", "").lower() in ("1", "true", "yes")

_SYMBOLS = {
    "success": "✅" if not _NO_EMOJI else "[OK]",
    "info": "ℹ️" if not _NO_EMOJI else "[i]",
    "warning": "⚠️" if not _NO_EMOJI else "[!]",
    "error": "❌" if not _NO_EMOJI else "[ERR]",
    "wave": "👋" if not _NO_EMOJI else "",
    "star": "⭐" if not _NO_EMOJI else "*",
    "owl": "🦉" if not _NO_EMOJI else "",
    "folder": "📁" if not _NO_EMOJI else "",
    "search": "🔍" if not _NO_EMOJI else "",
    "link": "🔗" if not _NO_EMOJI else "",
    "books": "📚" if not _NO_EMOJI else "",
    "door": "🚪" if not _NO_EMOJI else "",
    "bulb": "💡" if not _NO_EMOJI else "*",
    "brain": "🧠" if not _NO_EMOJI else "",
    "rocket": "🚀" if not _NO_EMOJI else "",
    "chart": "📊" if not _NO_EMOJI else "",
    "cycle": "🔄" if not _NO_EMOJI else "",
    "back": "🔙" if not _NO_EMOJI else "<",
    "arrow": "➜" if not _NO_EMOJI else ">",
    "point": "👉" if not _NO_EMOJI else "->",
    "party": "🎉" if not _NO_EMOJI else "",
}


def _sym(key: str) -> str:
    return _SYMBOLS.get(key, "")


# ──────────────────────────────────────────────────────────────
# WIDTH HANDLING
# ──────────────────────────────────────────────────────────────
# Panels adapt to the terminal width instead of using a fixed size,
# so they don't wrap awkwardly on narrow terminals or look tiny and
# off-center on wide ones.

def _panel_width(preferred: int = 65, minimum: int = 40) -> int:
    term_width = shutil.get_terminal_size(fallback=(preferred, 24)).columns
    return max(minimum, min(preferred, term_width - 4))


# ──────────────────────────────────────────────────────────────
# CORE MESSAGES
# ──────────────────────────────────────────────────────────────

def success(message: str) -> None:
    console.print(f"[bold green]{_sym('success')} {message}[/bold green]")


def info(message: str) -> None:
    console.print(f"[bold blue]{_sym('info')} {message}[/bold blue]")


def warning(message: str) -> None:
    console.print(f"[bold yellow]{_sym('warning')} {message}[/bold yellow]")


def error(message: str, suggestion: str = "") -> None:
    console.print()
    console.print(Panel(
        f"[bold red]{_sym('error')} {message}[/bold red]\n\n"
        f"[dim]{_sym('bulb')} {suggestion or 'Try again, or run opun8 --help to see all commands.'}[/dim]",
        border_style="red",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()


def goodbye() -> None:
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('wave')} Thanks for stopping by![/bold cyan]\n\n"
        "[dim]Come back anytime — I'll be right here when you're ready to ship.[/dim]\n"
        "[dim]Built with care by the Kakes David team.[/dim]\n"
        f"[dim]{_sym('star')} Enjoying Opun8? Star us on GitHub: github.com/KakesDavid/opun8[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()


# ──────────────────────────────────────────────────────────────
# WELCOME & MAIN MENU
# ──────────────────────────────────────────────────────────────
#
# show_welcome() and show_help() used to call each other directly
# ("go back" -> show_welcome(), "view commands" -> show_help()).
# That mutual recursion grows the call stack by one frame every
# time a user bounces between menus, and will eventually hit
# Python's recursion limit on a long interactive session.
#
# Both entry points now drive the same small state machine instead,
# so navigating between screens is a loop, not recursive calls.

def show_welcome():
    """Display the welcome screen and route to the chosen action."""
    _run_menu_loop("welcome")


def show_help():
    """Display all commands."""
    _run_menu_loop("help")


def _run_menu_loop(start_screen: str) -> None:
    screen = start_screen
    while screen in ("welcome", "help"):
        if screen == "welcome":
            screen = _render_welcome_and_get_next()
        else:
            screen = _render_help_and_get_next()


def _render_welcome_and_get_next() -> str:
    console.print("\n" * 2)
    console.print(Panel(
        f"[bold cyan]{_sym('owl')} Welcome to Opun8[/bold cyan]\n"
        "[dim]Your friendly guide from idea to live website — no DevOps degree required.[/dim]\n\n"
        "I'll walk you through everything step by step. Ready when you are!\n\n"
        f"[bold]{_sym('point')} Pick an option below to get started.[/bold]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(65),
    ))
    console.print()

    # Show GitHub status if connected
    if is_authenticated():
        user = get_authenticated_user()
        console.print(f"[dim]{_sym('link')} Connected to GitHub as [green]{user}[/green] — you're all set to deploy.[/dim]")
    else:
        console.print(f"[dim]{_sym('link')} Not connected to GitHub yet. Run 'opun8 github' anytime to connect.[/dim]")

    console.print()
    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_sym('folder')}  [white]Detect my project[/white]  [dim](Recommended)[/dim]")
    console.print(f"  [bold cyan]2[/] {_sym('search')}  [white]Check my environment[/white]")
    console.print(f"  [bold cyan]3[/] {_sym('link')}  [white]Connect GitHub[/white]")
    console.print(f"  [bold cyan]4[/] {_sym('books')}  [white]View all commands[/white]")
    console.print(f"  [bold cyan]5[/] {_sym('door')}  [white]Exit[/white]")
    console.print()
    console.print(f"[dim]{_sym('bulb')} Tip: Not sure where to start? Just press Enter — I'll detect your project for you.[/dim]")
    console.print()

    choice = Prompt.ask(
        f"[bold cyan]{_sym('arrow')}[/] Select an option",
        choices=["1", "2", "3", "4", "5"],
        default="1",
        show_choices=False,
    )

    if choice == "1":
        from opun8.commands.detect import detect
        detect()
        return "done"
    elif choice == "2":
        from opun8.commands.doctor import doctor
        doctor()
        return "done"
    elif choice == "3":
        from opun8.cli import github
        github()
        return "done"
    elif choice == "4":
        return "help"
    else:  # choice == "5"
        goodbye()
        raise typer.Exit()


def _render_help_and_get_next() -> str:
    console.print("\n" * 2)
    console.print(Panel(
        f"[bold cyan]{_sym('books')} Opun8 Commands[/bold cyan]\n"
        "[dim]Everything you can do, all in one place.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()

    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("Command", style="bold green", width=16)
    table.add_column("Description", style="white", width=40)

    table.add_row("opun8", "Show welcome screen")
    table.add_row("opun8 --version", "Show version")
    table.add_row("opun8 doctor", "Check environment")
    table.add_row("opun8 detect", "Detect project type")
    table.add_row("opun8 deploy", "Deploy your project")
    table.add_row("opun8 github", "Connect to GitHub")
    table.add_row("opun8 logout", "Logout from GitHub")
    table.add_row("opun8 help", "Show this help")

    console.print(table)
    console.print()
    console.print(f"[dim]{_sym('bulb')} For more details, visit: [cyan]https://opun8.dev/docs[/cyan][/dim]")
    console.print()

    console.print("[bold]What would you like to do next?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_sym('back')}  [white]Go back to main menu[/white]")
    console.print(f"  [bold cyan]2[/] {_sym('door')}  [white]Exit[/white]")
    console.print()

    choice = Prompt.ask(
        f"[bold cyan]{_sym('arrow')}[/] Select an option",
        choices=["1", "2"],
        default="1",
        show_choices=False,
    )

    if choice == "1":
        return "welcome"
    else:
        goodbye()
        raise typer.Exit()


# ──────────────────────────────────────────────────────────────
# DETECTION UI
# ──────────────────────────────────────────────────────────────

def detection_start():
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('folder')} Detecting Your Project[/bold cyan]\n"
        "[dim]Give me a second to look around...[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))


@contextmanager
def scanning_spinner(message: str = "Scanning your current folder..."):
    """Live spinner shown while the actual detection logic runs.

    detection_start() only prints a static header now; wrap the real
    scanning call in this context manager from commands/detect.py so
    users get live feedback instead of a screen that looks frozen on
    larger repos:

        messages.detection_start()
        with messages.scanning_spinner():
            result = run_detection()
        messages.detection_complete(result)
    """
    with console.status(f"[dim]{message}[/dim]", spinner="dots"):
        yield


def detection_complete(result: dict):
    console.print()
    console.print(f"[bold green]{_sym('success')} Nice! I found your project.[/bold green]")
    console.print()
    console.print(f"[bold]{_sym('brain')} Here's what I detected:[/bold]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold white", width=16)
    table.add_column(style="white", width=40)

    table.add_row("Type", result.get("type", "Unknown"))
    table.add_row("Framework", result.get("framework", "Unknown"))
    table.add_row("Package Manager", result.get("package_manager", "Unknown"))
    table.add_row("Build Command", result.get("build_command", "Not found"))
    table.add_row("Output Directory", result.get("output_dir", "Unknown"))

    console.print(table)


def no_project_detected():
    console.print()
    console.print(f"[yellow]{_sym('warning')} Hmm, I couldn't find a project here.[/yellow]")
    console.print()
    console.print("[dim]I'm looking for one of these in your current folder:[/dim]")
    console.print("[dim]  • package.json (Node.js/React/Next.js)[/dim]")
    console.print("[dim]  • index.html (Static HTML)[/dim]")
    console.print("[dim]  • requirements.txt (Python)[/dim]")
    console.print()
    console.print("[dim]Navigate to your project folder and run 'opun8 detect' again — I'll be ready.[/dim]")
    console.print()


def show_deploy_menu():
    """Show menu after detection with 4 options."""
    console.print()
    console.print(f"[bold]{_sym('party')} Nice! Your project is ready. What would you like to do next?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_sym('rocket')}  [white]Deploy this project[/white]")
    console.print(f"  [bold cyan]2[/] {_sym('chart')}  [white]View more details[/white]")
    console.print(f"  [bold cyan]3[/] {_sym('cycle')}  [white]Go back[/white]")
    console.print(f"  [bold cyan]4[/] {_sym('door')}  [white]Exit[/white]")
    console.print()


def show_details(result: dict):
    console.print()
    console.print(f"[bold cyan]{_sym('chart')} Project Details[/bold cyan]")
    console.print()

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="bold white", width=20)
    table.add_column(style="white", width=40)

    fields = ["type", "framework", "package_manager", "build_command", "output_dir", "node_version"]

    for key in fields:
        value = result.get(key)
        if value:
            display_key = key.replace("_", " ").title()
            if isinstance(value, list):
                value = ", ".join(value[:5]) + ("..." if len(value) > 5 else "")
            table.add_row(display_key, str(value))

    deps = result.get("dependencies", [])
    if deps:
        table.add_row("Dependencies", ", ".join(deps[:5]) + ("..." if len(deps) > 5 else ""))

    console.print(table)
    console.print()