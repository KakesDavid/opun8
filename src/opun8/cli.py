"""
Opun8 CLI - Command Line Interface for the Universal Deployment Platform.
"""

import typer
from typing import Optional
from rich.console import Console
from rich.prompt import Prompt

from opun8 import __version__
from opun8.ui.messages import show_welcome
from opun8.auth import (
    login_to_github,
    logout as logout_github,
    is_authenticated,
    get_authenticated_user,
    list_github_repos,
)
from opun8.providers.vercel.auth import (
    login_to_vercel,
    is_vercel_authenticated,
    logout_vercel,
    show_vercel_projects,
    switch_vercel_team,
    set_deploy_callback,
)
from opun8.providers.render.auth import (
    login_to_render,
    is_render_authenticated,
    logout_render,
    show_render_auth_status,
    switch_render_owner,
    list_render_owners,
    get_render_token,
    get_render_owner_id,  # ← Fixed: Added missing import
)
from opun8.providers.render.deploy import list_render_services

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


# ──────────────────────────────────────────────────────────────
# COMMANDS
# ──────────────────────────────────────────────────────────────

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
def deploy(
    platform: Optional[str] = typer.Argument(
        None,
        help="Platform to deploy to (vercel, netlify, render). Optional.",
    ),
):
    """Deploy your project to the cloud."""
    from opun8.commands.deploy import deploy as deploy_cmd
    deploy_cmd(platform_arg=platform)


@app.command()
def history():
    """View and manage your deployment history."""
    from opun8.commands.history import history as history_cmd
    history_cmd()


@app.command()
def badges():
    """Show your badge progress and achievements."""
    from opun8.commands.badges import badges as badges_cmd
    badges_cmd()


# ──────────────────────────────────────────────────────────────
# GITHUB COMMANDS
# ──────────────────────────────────────────────────────────────

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
        logout_github()
        return

    if is_authenticated():
        user = get_authenticated_user()
        console.print(f"[green]✅ Already connected as: {user}[/green]")
        console.print("[dim]To disconnect, run: opun8 github --logout[/dim]")
        console.print()

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

        choice = Prompt.ask(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2", "3"],
            default="3",
            show_choices=False,
        )

        if choice == "1":
            _deploy_repository_from_github()
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


def _deploy_repository_from_github() -> None:
    """
    Handle the "Deploy a repository" flow from the GitHub menu.
    Allows user to select a repo and deploy it.
    """
    console.print()
    console.print("[bold cyan]🚀 Deploy a GitHub Repository[/bold cyan]")
    console.print("[dim]Select a repository to clone and deploy.[/dim]")
    console.print()

    repos = list_github_repos()
    if not repos:
        console.print("[yellow]No repositories found.[/yellow]")
        return

    # Show repository list with numbers
    console.print("[bold]Select a repository:[/bold]")
    console.print()
    for i, repo in enumerate(repos[:20], 1):
        private_tag = "[dim](private)[/dim]" if repo.get("private") else ""
        console.print(f"  [bold cyan]{i}[/]  [white]{repo['name']}[/white] {private_tag}")
    if len(repos) > 20:
        console.print(f"  [dim]... and {len(repos) - 20} more[/dim]")

    console.print()
    console.print("  [bold cyan]0[/] 🔙  [white]Go back[/white]")
    console.print()

    choice = Prompt.ask(
        "[bold cyan]➜[/] Select a repository",
        default="0",
        show_choices=False,
    )

    try:
        idx = int(choice) - 1
        if idx < 0:
            return
        if idx >= len(repos):
            console.print("[red]Invalid selection.[/red]")
            return
        
        selected_repo = repos[idx]
        repo_name = selected_repo.get("name")
        clone_url = selected_repo.get("url", f"https://github.com/{get_authenticated_user()}/{repo_name}")
        
        console.print()
        console.print(f"[bold]Selected: [cyan]{repo_name}[/cyan][/bold]")
        console.print()
        
        # Ask for deployment platform
        console.print("[bold]Which platform would you like to deploy to?[/bold]")
        console.print()
        console.print("  [bold cyan]1[/] ▲  [white]Vercel[/white]  [dim](Recommended for frontend)[/dim]")
        console.print("  [bold cyan]2[/] 📦  [white]Netlify[/white]  [dim](Coming soon)[/dim]")
        console.print("  [bold cyan]3[/] ☁️  [white]Render[/white]  [dim](Great for full-stack and Python)[/dim]")
        console.print()
        
        platform_choice = Prompt.ask(
            "[bold cyan]➜[/] Select a platform",
            choices=["1", "2", "3"],
            default="1",
            show_choices=False,
        )
        
        if platform_choice == "1":
            from opun8.commands.repo import deploy_repository
            deploy_repository(clone_url, repo_name, platform="vercel")
        elif platform_choice == "3":
            from opun8.commands.repo import deploy_repository
            deploy_repository(clone_url, repo_name, platform="render")
        elif platform_choice == "2":
            console.print(f"[yellow]⚠️ Netlify support coming soon![/yellow]")
        else:
            console.print("[yellow]Invalid platform selection.[/yellow]")
            
    except ValueError:
        console.print("[red]Please enter a valid number.[/red]")
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Cancelled by user.[/yellow]")
        raise typer.Exit()


# ──────────────────────────────────────────────────────────────
# VERCEL COMMANDS
# ──────────────────────────────────────────────────────────────

@app.command()
def vercel(
    logout_flag: bool = typer.Option(
        False,
        "--logout",
        "-l",
        help="Logout from Vercel.",
    ),
    switch_flag: bool = typer.Option(
        False,
        "--switch",
        "-s",
        help="Switch Vercel team/scope.",
    ),
    show_flag: bool = typer.Option(
        False,
        "--show",
        help="Show projects without re-authenticating.",
    ),
):
    """Connect to Vercel account."""

    if logout_flag:
        logout_vercel()
        return

    if switch_flag:
        switch_vercel_team()
        return

    if show_flag:
        from opun8.commands.deploy import deploy as deploy_cmd
        set_deploy_callback(deploy_cmd)
        show_vercel_projects()
        return

    if is_vercel_authenticated():
        console.print("[green]✅ Already connected to Vercel.[/green]")
        console.print("[dim]To disconnect, run: opun8 vercel --logout[/dim]")
        console.print("[dim]To switch teams, run: opun8 vercel --switch[/dim]")
        console.print()
        from opun8.commands.deploy import deploy as deploy_cmd
        set_deploy_callback(deploy_cmd)
        show_vercel_projects()
        return

    console.print()
    console.print("[bold cyan]▲ Connect to Vercel[/bold cyan]")
    console.print("[dim]This will allow Opun8 to deploy projects to Vercel.[/dim]")
    console.print()

    from opun8.commands.deploy import deploy as deploy_cmd
    set_deploy_callback(deploy_cmd)

    token = login_to_vercel()

    if token:
        console.print("[green]✅ Connected to Vercel successfully![/green]")
    else:
        console.print("[red]❌ Connection failed.[/red]")


# ──────────────────────────────────────────────────────────────
# RENDER COMMANDS
# ──────────────────────────────────────────────────────────────

@app.command()
def render(
    logout_flag: bool = typer.Option(
        False,
        "--logout",
        "-l",
        help="Logout from Render.",
    ),
    switch_flag: bool = typer.Option(
        False,
        "--switch",
        "-s",
        help="Switch Render workspace/owner.",
    ),
    show_flag: bool = typer.Option(
        False,
        "--show",
        help="Show services without re-authenticating.",
    ),
):
    """Connect to Render account."""

    if logout_flag:
        logout_render()
        return

    if switch_flag:
        _switch_render_owner()
        return

    if show_flag:
        _show_render_services()
        return

    if is_render_authenticated():
        console.print("[green]✅ Already connected to Render.[/green]")
        console.print("[dim]To disconnect, run: opun8 render --logout[/dim]")
        console.print("[dim]To switch workspace, run: opun8 render --switch[/dim]")
        console.print()
        _show_render_services()
        return

    console.print()
    console.print("[bold cyan]☁️ Connect to Render[/bold cyan]")
    console.print("[dim]This will allow Opun8 to deploy projects to Render.[/dim]")
    console.print()

    token = login_to_render()

    if token:
        console.print("[green]✅ Connected to Render successfully![/green]")
        console.print("[dim]Run [cyan]opun8 render[/cyan] again to see your services.[/dim]")
    else:
        console.print("[red]❌ Connection failed.[/red]")


def _switch_render_owner() -> None:
    """Interactive owner/workspace switching for Render."""
    token = get_render_token()
    if not token:
        console.print("[yellow]Not connected to Render. Run `opun8 render` first.[/yellow]")
        return

    from opun8.providers.render.auth import list_render_owners, prompt_owner_selection

    owners = list_render_owners(token)
    if not owners:
        console.print("[yellow]No workspaces found.[/yellow]")
        return

    selected = prompt_owner_selection(token)
    if selected:
        from opun8.providers.render.auth import switch_render_owner
        switch_render_owner(selected)


def _show_render_services() -> None:
    """Show Render services for the authenticated user."""
    token = get_render_token()
    if not token:
        console.print("[yellow]Not connected to Render. Run `opun8 render` first.[/yellow]")
        return

    owner_id = get_render_owner_id()
    services = list_render_services(token, owner_id)

    if services is None:
        console.print("[red]Could not fetch Render services.[/red]")
        return

    if not services:
        console.print()
        console.print("[yellow]No services found on Render.[/yellow]")
        console.print("[dim]Run [cyan]opun8 deploy[/cyan] to create your first service.[/dim]")
        return

    from rich.table import Table
    from rich.panel import Panel

    console.print()
    console.print(Panel(
        "[bold cyan]☁️ Render Services[/bold cyan]\n"
        f"[dim]{len(services)} service(s) found[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
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


# ──────────────────────────────────────────────────────────────
# LOGOUT
# ──────────────────────────────────────────────────────────────

@app.command(name="logout")
def logout_all():
    """Logout from all services."""
    logout_github()
    logout_vercel()
    logout_render()
    console.print("[green]✅ Logged out from all services.[/green]")


# ──────────────────────────────────────────────────────────────
# HELP
# ──────────────────────────────────────────────────────────────

@app.command()
def help():
    """Show all available commands."""
    from opun8.ui.messages import show_help
    show_help()