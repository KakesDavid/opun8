"""
Opun8 CLI - Command Line Interface for the Universal Deployment Platform.
"""

import typer
from rich.console import Console

from opun8 import __version__
from opun8.ui.messages import show_welcome
from opun8.auth import (
    login_to_github,
    logout,
    is_authenticated,
    get_authenticated_user,
    list_github_repos,
)

app = typer.Typer(
    name="opun8",
    help="Developer-first deployment platform.",
    add_completion=False,
    no_args_is_help=False,
)

console = Console()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        "-v",
        help="Show Opun8 version.",
    ),
):
    if version:
        console.print(f"Opun8 v{__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        show_welcome()


@app.command()
def doctor():
    """Check your environment and project."""
    from opun8.commands.doctor import doctor as doctor_cmd
    doctor_cmd()


@app.command()
def detect():
    """Detect your project type and stack."""
    from opun8.commands.detect import detect as detect_cmd
    detect_cmd()


@app.command()
def deploy():
    """Deploy your project to the cloud."""
    from opun8.commands.deploy import deploy as deploy_cmd
    deploy_cmd()


@app.command()
def github(
    logout_flag: bool = typer.Option(
        False,
        "--logout",
        "-l",
        help="Logout from GitHub.",
    ),
):
    """Connect to GitHub account."""
    
    if logout_flag:
        logout()
        return
    
    if is_authenticated():
        user = get_authenticated_user()
        console.print(f"[green]✅ Already connected as: {user}[/green]")
        console.print("[dim]To disconnect, run: opun8 github --logout[/dim]")
        console.print()
        
        # Show repositories
        console.print("[bold]📁 Your GitHub Repositories:[/bold]")
        console.print()
        repos = list_github_repos()
        if repos:
            for i, repo in enumerate(repos[:10], 1):
                private_tag = "[dim](private)[/dim]" if repo.get("private") else ""
                console.print(f"  [bold cyan]{i}[/]  [white]{repo['name']}[/white] {private_tag}")
            if len(repos) > 10:
                console.print(f"  [dim]... and {len(repos) - 10} more[/dim]")
        else:
            console.print("  [dim]No repositories found[/dim]")
        console.print()
        console.print("[bold]What would you like to do?[/bold]")
        console.print()
        console.print("  [bold cyan]1[/] 🚀  [white]Deploy a repository[/white]")
        console.print("  [bold cyan]2[/] 📁  [white]Detect my current project[/white]")
        console.print("  [bold cyan]3[/] 🔄  [white]Go back[/white]")
        console.print()
        
        choice = typer.prompt("[bold cyan]➜[/] Select an option", default="3")
        
        if choice == "1":
            console.print("[yellow]🚀 Deploy repository coming soon![/yellow]")
        elif choice == "2":
            from opun8.commands.detect import detect as detect_cmd
            detect_cmd()
        else:
            show_welcome()
        return
    
    console.print()
    console.print("[bold cyan]🔐 Connect to GitHub[/bold cyan]")
    console.print("[dim]This will allow Opun8 to create repositories and push code on your behalf.[/dim]")
    console.print()
    
    token = login_to_github()
    
    if token:
        console.print("[green]✅ Connected successfully![/green]")
        console.print("[dim]Run [cyan]opun8 github[/cyan] again to see your repositories.[/dim]")
    else:
        console.print("[red]❌ Connection failed.[/red]")


@app.command()
def help():
    """Show all available commands."""
    from opun8.ui.messages import show_help
    show_help()