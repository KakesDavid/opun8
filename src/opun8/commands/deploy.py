"""
Deploy command - Placeholder until deployment is fully built.
"""

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

console = Console()


def deploy():
    """Deploy your project to the cloud."""
    console.print()
    console.print(Panel(
        "[bold yellow]🚀 Deploy Coming Soon![/bold yellow]\n"
        "[dim]The deploy feature is currently under development.[/dim]\n\n"
        "This feature will allow you to deploy to Vercel, Netlify, Render, and more.\n\n"
        "Expected release: [bold]v0.2.0[/bold]",
        border_style="yellow",
        padding=(1, 2),
        width=60,
    ))
    console.print()
    
    console.print("[dim]What would you like to do?[/dim]")
    console.print()
    console.print("  [bold cyan]1[/] 🔄  [white]Go back[/white]")
    console.print("  [bold cyan]2[/] 🚪  [white]Exit[/white]")
    console.print()
    
    choice = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2"],
        default="1",
        show_choices=False,
    )
    
    if choice == "1":
        from opun8.commands.detect import detect
        detect()
    else:
        from opun8.ui.messages import goodbye
        goodbye()