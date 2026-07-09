"""
UI messages for Opun8.
All user-facing messages in one place.
"""

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm

from opun8.auth import is_authenticated, get_authenticated_user

console = Console()


# ──────────────────────────────────────────────────────────────
# CORE MESSAGES
# ──────────────────────────────────────────────────────────────

def success(message: str) -> None:
    console.print(f"[bold green]✅ {message}[/bold green]")


def info(message: str) -> None:
    console.print(f"[bold blue]ℹ️ {message}[/bold blue]")


def warning(message: str) -> None:
    console.print(f"[bold yellow]⚠️ {message}[/bold yellow]")


def error(message: str, suggestion: str = "") -> None:
    console.print()
    console.print(Panel(
        f"[bold red]❌ {message}[/bold red]\n\n"
        f"[dim]💡 {suggestion or 'Try again or run: opun8 --help'}[/dim]",
        border_style="red",
        padding=(1, 2),
        width=60,
    ))
    console.print()


def goodbye() -> None:
    console.print()
    console.print(Panel(
        "[bold cyan]👋 Thanks for using Opun8![/bold cyan]\n\n"
        "[dim]Built by Kakes David Team[/dim]\n"
        "[dim]⭐ Star us on GitHub: github.com/KakesDavid/opun8[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()


# ──────────────────────────────────────────────────────────────
# WELCOME & MAIN MENU
# ──────────────────────────────────────────────────────────────

def show_welcome():
    """Display the welcome screen."""
    console.print("\n" * 2)
    console.print(Panel(
        "[bold cyan]🦉 Welcome to Opun8[/bold cyan]\n"
        "[dim]The deployment platform that guides you from idea to live website.[/dim]\n\n"
        "I'm here to help you deploy your project. Let's do this together.\n\n"
        "[bold]Before we start, let me understand what you're working on.[/bold]",
        border_style="cyan",
        padding=(1, 2),
        width=65,
    ))
    console.print()
    
    # Show GitHub status if connected
    if is_authenticated():
        user = get_authenticated_user()
        console.print(f"[dim]🔗 Connected to GitHub as: [green]{user}[/green][/dim]")
    else:
        console.print("[dim]🔗 Not connected to GitHub. Use 'opun8 github' to connect.[/dim]")
    
    console.print()
    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] 📁  [white]Detect my project[/white]  [dim](Recommended)[/dim]")
    console.print("  [bold cyan]2[/] 🔍  [white]Check my environment[/white]")
    console.print("  [bold cyan]3[/] 🔗  [white]Connect GitHub[/white]")
    console.print("  [bold cyan]4[/] 📚  [white]View all commands[/white]")
    console.print("  [bold cyan]5[/] 🚪  [white]Exit[/white]")
    console.print()
    console.print("[dim]💡 Tip: Start with 'Detect my project' so I can understand your code.[/dim]")
    console.print()
    
    choice = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2", "3", "4", "5"],
        default="1",
        show_choices=False,
    )
    
    if choice == "1":
        from opun8.commands.detect import detect
        detect()
    elif choice == "2":
        from opun8.commands.doctor import doctor
        doctor()
    elif choice == "3":
        from opun8.cli import github
        github()
    elif choice == "4":
        show_help()
    elif choice == "5":
        goodbye()
        raise typer.Exit()


def show_help():
    """Display all commands."""
    console.print("\n" * 2)
    console.print(Panel(
        "[bold cyan]📚 Opun8 Commands[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
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
    console.print("[dim]💡 For more details, visit: [cyan]https://opun8.dev/docs[/cyan][/dim]")
    console.print()
    
    console.print("[bold]What would you like to do next?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] 🔙  [white]Go back to main menu[/white]")
    console.print("  [bold cyan]2[/] 🚪  [white]Exit[/white]")
    console.print()
    
    choice = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2"],
        default="1",
        show_choices=False,
    )
    
    if choice == "1":
        show_welcome()
    else:
        goodbye()
        raise typer.Exit()


# ──────────────────────────────────────────────────────────────
# DETECTION UI
# ──────────────────────────────────────────────────────────────

def detection_start():
    console.print()
    console.print(Panel(
        "[bold cyan]📁 Detecting Your Project[/bold cyan]\n"
        "[dim]Scanning your current folder...[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))


def detection_complete(result: dict):
    console.print()
    console.print("[bold green]✅ Project detected successfully![/bold green]")
    console.print()
    console.print("[bold]🧠 I've analyzed your project:[/bold]")
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
    console.print("[yellow]⚠️ No project detected.[/yellow]")
    console.print()
    console.print("[dim]Make sure you're in a project folder with:[/dim]")
    console.print("[dim]  • package.json (Node.js/React/Next.js)[/dim]")
    console.print("[dim]  • index.html (Static HTML)[/dim]")
    console.print("[dim]  • requirements.txt (Python)[/dim]")
    console.print()


def show_deploy_menu():
    """Show menu after detection with 4 options."""
    console.print()
    console.print("[bold]What would you like to do next?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] 🚀  [white]Deploy this project[/white]")
    console.print("  [bold cyan]2[/] 📊  [white]View more details[/white]")
    console.print("  [bold cyan]3[/] 🔄  [white]Go back[/white]")
    console.print("  [bold cyan]4[/] 🚪  [white]Exit[/white]")
    console.print()


def show_details(result: dict):
    console.print()
    console.print("[bold cyan]📊 Project Details[/bold cyan]")
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