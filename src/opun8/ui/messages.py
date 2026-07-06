"""
UI messages for Opun8.
"""

from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm, Prompt

from .console import console


def welcome() -> None:
    """Display the welcome message."""
    console.print()
    console.print(Panel(
        "[bold cyan]Welcome to Opun8[/bold cyan]\n"
        "[dim]The deployment platform for developers.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    
    console.print()
    console.print("I can help you deploy your projects without the usual hassle.")
    console.print()
    
    console.print("[bold]Here's what I can do for you:[/bold]")
    console.print()
    
    features = Table(show_header=False, box=None, padding=(0, 2))
    features.add_column(style="bold", width=4)
    features.add_column(style="white")
    
    features.add_row("", "Deploy to [bold]Vercel[/bold], [bold]Netlify[/bold], and more")
    features.add_row("", "Detect your project type [bold]automatically[/bold]")
    features.add_row("", "Connect to [bold]GitHub[/bold] seamlessly")
    features.add_row("", "Check your environment with [bold]doctor[/bold]")
    
    console.print(features)
    
    console.print()
    console.print("[bold]Quick Start:[/bold]")
    console.print()
    
    commands = Table(show_header=False, box=None, padding=(0, 2))
    commands.add_column(style="bold green", width=18)
    commands.add_column(style="white")
    
    commands.add_row("opun8 doctor", "Check if everything is ready")
    commands.add_row("opun8 detect", "Find out what project type you have")
    commands.add_row("opun8 deploy", "Deploy your project")
    
    console.print(commands)
    
    console.print()
    console.print("[dim]Need help? Visit: [cyan]https://opun8.dev/docs[/cyan][/dim]")
    console.print()
    
    show_menu()


def show_menu() -> None:
    """Display interactive menu."""
    console.print()
    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    
    console.print("  [bold cyan]1[/]  Deploy my project")
    console.print("  [bold cyan]2[/]  Login to GitHub")
    console.print("  [bold cyan]3[/]  Settings")
    console.print("  [bold cyan]4[/]  Exit")
    console.print()
    
    choice = Prompt.ask(
        "[bold cyan]Select an option[/]",
        choices=["1", "2", "3", "4"],
        default="1",
        show_choices=False,
    )
    
    if choice == "1":
        console.print("\n[yellow]Deploying your project... (coming soon)[/]")
    elif choice == "2":
        console.print("\n[yellow]Connecting to GitHub... (coming soon)[/]")
    elif choice == "3":
        console.print("\n[yellow]Opening settings... (coming soon)[/]")
    elif choice == "4":
        console.print("\n[dim]Goodbye![/]")
        raise typer.Exit()


def success(message: str) -> None:
    """Display a success message."""
    console.print(f"[bold green]OK[/bold green] {message}")


def info(message: str) -> None:
    """Display an informational message."""
    console.print(f"[bold blue]Info[/bold blue] {message}")


def warning(message: str) -> None:
    """Display a warning message."""
    console.print(f"[bold yellow]Warning[/bold yellow] {message}")


def error(message: str) -> None:
    """Display an error message."""
    console.print(f"[bold red]Error[/bold red] {message}")