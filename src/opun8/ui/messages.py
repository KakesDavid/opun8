"""
UI messages for Opun8.
All user-facing messages in one place.
"""

import os
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt

from opun8.auth import is_authenticated, get_authenticated_user
from opun8.services.recent_projects import get_recent_projects

console = Console()


# ──────────────────────────────────────────────────────────────
# EMOJI / SYMBOL HANDLING
# ──────────────────────────────────────────────────────────────

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
    "browse": "📂" if not _NO_EMOJI else "",
    "history": "📜" if not _NO_EMOJI else "",
    "badge": "🏅" if not _NO_EMOJI else "",
    "cloud": "☁️" if not _NO_EMOJI else "",
    "triangle": "▲" if not _NO_EMOJI else "",
}


def _sym(key: str) -> str:
    return _SYMBOLS.get(key, "")


# ──────────────────────────────────────────────────────────────
# WIDTH HANDLING
# ──────────────────────────────────────────────────────────────

def _panel_width(preferred: int = 65, minimum: int = 40) -> int:
    term_width = shutil.get_terminal_size(fallback=(preferred, 24)).columns
    return max(minimum, min(preferred, term_width - 4))


# ──────────────────────────────────────────────────────────────
# FOLDER DIALOG
# ──────────────────────────────────────────────────────────────

def open_folder_dialog(title: str = "Select a project folder") -> Optional[Path]:
    """
    Open a native folder browser dialog for the user to select a folder.
    
    Returns:
        Path of the selected folder, or None if cancelled.
    """
    # Try tkinter first (built-in on Windows/macOS/Linux)
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        # Create a minimal root window and hide it
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        
        # Open folder dialog
        folder_path = filedialog.askdirectory(
            title=title,
            mustexist=True
        )
        
        root.destroy()
        
        if folder_path:
            return Path(folder_path)
        return None
        
    except ImportError:
        # Fallback: try PyQt5
        try:
            from PyQt5.QtWidgets import QApplication, QFileDialog
            from PyQt5.QtCore import QCoreApplication
            
            app = QApplication.instance()
            if app is None:
                app = QApplication([])
            
            folder_path = QFileDialog.getExistingDirectory(
                None,
                title,
                os.path.expanduser("~"),
                QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
            )
            
            if folder_path:
                return Path(folder_path)
            return None
            
        except ImportError:
            # Fallback: try easygui
            try:
                import easygui
                folder_path = easygui.diropenbox(
                    title=title,
                    default=os.path.expanduser("~")
                )
                if folder_path:
                    return Path(folder_path)
                return None
                
            except ImportError:
                # Last resort: use input prompt
                console.print("[yellow]⚠️ Could not open folder dialog. Please enter path manually.[/yellow]")
                folder_path = Prompt.ask(
                    f"[bold cyan]{_sym('arrow')}[/] Project folder path (leave blank to cancel)"
                )
                if folder_path:
                    path = Path(folder_path).expanduser().resolve()
                    if path.exists():
                        return path
                    console.print(f"[red]❌ Path does not exist: {folder_path}[/red]")
                    return None
                return None


def prompt_select_folder_with_dialog(title: str = "Select a project folder") -> Optional[Path]:
    """
    Wrapper for open_folder_dialog with user-friendly messages.
    """
    console.print()
    console.print(f"[bold cyan]{_sym('browse')} {title}[/bold cyan]")
    console.print("[dim]A file browser will open. Select the folder containing your project.[/dim]")
    console.print()
    
    folder = open_folder_dialog(title)
    
    if folder:
        console.print(f"[green]{_sym('success')} Selected: {folder}[/green]")
        return folder
    else:
        console.print("[yellow]Folder selection cancelled.[/yellow]")
        return None


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

    if is_authenticated():
        user = get_authenticated_user()
        console.print(f"[dim]{_sym('link')} Connected to GitHub as [green]{user}[/green] — you're all set to deploy.[/dim]")
    else:
        console.print(f"[dim]{_sym('link')} Not connected to GitHub yet. Run 'opun8 github' anytime to connect.[/dim]")

    recent = get_recent_projects()
    if recent:
        console.print()
        console.print("[bold]📁 Recent Projects:[/bold]")
        console.print()
        for i, project in enumerate(recent[:5], 1):
            console.print(f"  [bold cyan]{i}[/]  [white]{project['name']}[/white]  [dim]({project['path']})[/dim]")
        if len(recent) > 5:
            console.print(f"  [dim]... and {len(recent) - 5} more[/dim]")

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
    else:
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
    table.add_column("Command", style="bold green", width=18)
    table.add_column("Description", style="white", width=42)

    table.add_row("opun8", "Show welcome screen")
    table.add_row("opun8 --version", "Show version")
    table.add_row("opun8 doctor", "Check environment")
    table.add_row("opun8 detect", "Detect project type")
    table.add_row("opun8 deploy", "Deploy your project")
    table.add_row("opun8 github", "Connect to GitHub")
    table.add_row("opun8 vercel", "Connect to Vercel")
    table.add_row("opun8 render", "Connect to Render")
    table.add_row("opun8 logout", "Logout from all services")
    table.add_row("opun8 history", "View deployment history")
    table.add_row("opun8 badges", "View badge progress")
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


def show_deploy_menu():
    """Show menu after detection with 5 options."""
    console.print()
    console.print(f"[bold]{_sym('party')} Nice! Your project is ready. What would you like to do?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_sym('rocket')}  [white]Deploy this project[/white]")
    console.print(f"  [bold cyan]2[/] {_sym('browse')}  [white]Select a different project[/white]")
    console.print(f"  [bold cyan]3[/] {_sym('history')}  [white]View deployment history[/white]")
    console.print(f"  [bold cyan]4[/] {_sym('badge')}  [white]View badges[/white]")
    console.print(f"  [bold cyan]5[/] {_sym('door')}  [white]Exit[/white]")
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


# ──────────────────────────────────────────────────────────────
# HISTORY UI
# ──────────────────────────────────────────────────────────────

def prompt_select_folder(title: str = "Select a project folder") -> Optional[Path]:
    """
    Prompt the user to select a folder using the native file browser.
    This is the main function called from history.py and other commands.
    """
    return prompt_select_folder_with_dialog(title)


# ──────────────────────────────────────────────────────────────
# RENDER-SPECIFIC MESSAGES
# ──────────────────────────────────────────────────────────────

def render_auth_start() -> None:
    """Show Render authentication start message."""
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('cloud')} Render Authentication[/bold cyan]\n\n"
        "Opun8 needs access to Render to:\n"
        "  • Create services\n"
        "  • Deploy your code\n"
        "  • Get deployment URLs\n\n"
        "[dim]Your browser will open for authorization if using OAuth.[/dim]"
        "\n[dim]Or paste your Render API key as an alternative.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()


def render_auth_success(username: str) -> None:
    """Show Render authentication success message."""
    console.print()
    console.print(f"[bold green]{_sym('success')} Connected to Render as: [white]{username}[/white][/bold green]")
    console.print("[dim]Token saved securely for future use.[/dim]")


def render_auth_failed() -> None:
    """Show Render authentication failure message."""
    error(
        "Render authentication failed.",
        suggestion="Run `opun8 render` to try again, or use an API key.",
    )


def render_deploy_start(project_name: str, region: str) -> None:
    """Show Render deployment start message."""
    console.print()
    console.print(f"[bold cyan]{_sym('cloud')} Deploying to Render[/bold cyan]")
    console.print(f"[dim]Project: {project_name}[/dim]")
    console.print(f"[dim]Region: {region}[/dim]")
    console.print()


def render_deploy_success(url: str) -> None:
    """Show Render deployment success message."""
    console.print()
    console.print(f"[bold green]{_sym('success')} Deployment successful![/bold green]")
    console.print(f"[dim]🌐 {url}[/dim]")


def render_deploy_failed(message: str) -> None:
    """Show Render deployment failure message."""
    error(
        f"Deployment failed: {message}",
        suggestion="Check your project for build errors and try again.",
    )


def render_services_list(services: list) -> None:
    """Show Render services list."""
    if not services:
        console.print("[yellow]No services found on Render.[/yellow]")
        console.print("[dim]Run [cyan]opun8 deploy[/cyan] to create your first service.[/dim]")
        return

    from rich.table import Table
    
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('cloud')} Render Services[/bold cyan]\n"
        f"[dim]{len(services)} service(s) found[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()

    table = Table(border_style="cyan")
    table.add_column("#", style="bold white", width=4)
    table.add_column("Name", style="bold white", width=20)
    table.add_column("Type", style="dim", width=12)
    table.add_column("Status", style="dim", width=12)
    table.add_column("URL", style="cyan", width=25)

    for idx, service in enumerate(services, 1):
        name = service.get("name", "Unknown")[:20]
        service_type = service.get("type", "unknown")[:12]
        status = service.get("status", "unknown")[:12]
        url = service.get("url", "N/A")[:25]

        table.add_row(str(idx), name, service_type, status, url)

    console.print(table)
    console.print()


def render_api_key_prompt() -> None:
    """Show Render API key prompt message."""
    console.print()
    console.print(Panel(
        f"[bold cyan]{_sym('key')} Render API Key[/bold cyan]\n\n"
        "You can get your API key from:\n"
        "[dim]https://dashboard.render.com/settings/keys[/dim]\n\n"
        "Create a new key with 'read' and 'write' permissions.\n"
        "This is useful for CI/CD and team deployments.",
        border_style="cyan",
        padding=(1, 2),
        width=_panel_width(60),
    ))
    console.print()
    console.print("[dim]🌐 Opening Render API keys page in your browser...[/dim]")