"""
Opun8 CLI - Command Line Interface for the Universal Deployment Platform.

This is the main entry point for the OPUN8 CLI. It provides commands for:
    - Authentication (register, login, verify, logout)
    - Website cloning (clone, clone with options)
    - Deployment (deploy to Vercel, Render, Netlify)
    - Account management (upgrade, status, history)
    - GitHub integration (connect, list repos, deploy from repo)
    - Provider management (Vercel, Render, Netlify)

Author: OPUN8 Team
Version: 0.1.5
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
    switch_render_owner,
    list_render_owners,
    get_render_token,
    get_render_owner_id,
    prompt_owner_selection,
)
from opun8.providers.render.deploy import list_render_services
from opun8.providers.netlify.auth import (
    login_to_netlify,
    is_netlify_authenticated,
    logout_netlify,
    netlify_auth_command,
    show_netlify_sites,
    set_deploy_callback as set_netlify_deploy_callback,
)

from opun8.commands.clone import clone as clone_cmd
from opun8.commands.upgrade import upgrade as upgrade_cmd

app = typer.Typer(
    name="opun8",
    help="Developer-first deployment platform.",
    add_completion=False,
    no_args_is_help=False,
)

console = Console(legacy_windows=True)


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def _sym(key: str) -> str:
    """Get emoji symbol by key (no-emoji mode aware)."""
    from opun8.ui.messages import _sym
    return _sym(key)


def _safe_prompt(message: str, choices: list, default: str = "1") -> str:
    """Prompt wrapper with Ctrl+C / Ctrl+D handling."""
    try:
        return Prompt.ask(
            message,
            choices=choices,
            default=default,
            show_choices=False,
        )
    except (KeyboardInterrupt, EOFError):
        console.print(f"\n{_sym('wave')} Goodbye, friend!")
        raise typer.Exit(0)


# ──────────────────────────────────────────────────────────────
# MAIN CALLBACK
# ──────────────────────────────────────────────────────────────

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
    """Main entry point for the CLI."""
    if version:
        console.print(f"Opun8 v{__version__}")
        raise typer.Exit()

    if ctx.invoked_subcommand is None:
        show_welcome()


# ──────────────────────────────────────────────────────────────
# AUTHENTICATION COMMANDS
# ──────────────────────────────────────────────────────────────

@app.command()
def register(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Your email address"),
    username: Optional[str] = typer.Option(None, "--username", "-u", help="Desired username"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Your password"),
):
    """Create a new OPUN8 account."""
    from opun8.commands.auth import register as register_cmd
    register_cmd(email=email, username=username, password=password)


@app.command()
def login(
    email: Optional[str] = typer.Option(None, "--email", "-e", help="Your email address"),
    password: Optional[str] = typer.Option(None, "--password", "-p", help="Your password"),
):
    """Log in to your OPUN8 account."""
    from opun8.commands.auth import login as login_cmd
    login_cmd(email=email, password=password)


@app.command()
def verify(
    code: Optional[str] = typer.Option(None, "--code", "-c", help="6-digit verification code"),
):
    """Verify your email with the OTP code."""
    from opun8.commands.auth import verify as verify_cmd
    verify_cmd(code=code)


@app.command(name="resend-otp")
def resend_otp():
    """Resend the OTP verification code."""
    from opun8.commands.auth import resend_otp as resend_otp_cmd
    resend_otp_cmd()


@app.command()
def status():
    """Check your OPUN8 account status."""
    from opun8.commands.auth import status as status_cmd
    status_cmd()


# ──────────────────────────────────────────────────────────────
# CLONE COMMAND
# ──────────────────────────────────────────────────────────────

@app.command()
def clone(
    url: str = typer.Argument(..., help="URL of the website to clone"),
    clean: bool = typer.Option(False, "--clean", help="Clean up messy code"),
    single_page: bool = typer.Option(False, "--single-page", "-s", help="Clone only the current page"),
    output: str = typer.Option("./cloned-site", "--output", "-o", help="Output directory"),
):
    """Clone any website to your local machine."""
    clone_cmd(url=url, clean=clean, single_page=single_page, output=output)


# ──────────────────────────────────────────────────────────────
# UPGRADE COMMAND
# ──────────────────────────────────────────────────────────────

@app.command()
def upgrade(
    plan: Optional[str] = typer.Argument(None, help="Plan to upgrade to (starter, pro)."),
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation prompt."),
):
    """Upgrade your OPUN8 subscription plan."""
    upgrade_cmd(plan_arg=plan, force=force)


# ──────────────────────────────────────────────────────────────
# CORE COMMANDS
# ──────────────────────────────────────────────────────────────

@app.command()
def doctor():
    """Check your environment and project setup."""
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
# GITHUB COMMANDS ✅ FIXED (no recursion)
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
    """
    Connect to GitHub account.
    
    ✅ FIX: Uses partner tone UI.
    ✅ FIX: No recursion — github_auth_start() calls login_to_github() directly.
    """
    if logout_flag:
        logout_github()
        console.print(f"[green]{_sym('success')} Logged out of GitHub.[/green]")
        return

    if is_authenticated():
        user = get_authenticated_user()
        console.print(f"[green]{_sym('success')} Already connected as: {user}[/green]")
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

        choice = _safe_prompt(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2", "3"],
            default="3",
        )

        if choice == "1":
            _deploy_repository_from_github()
        elif choice == "2":
            from opun8.commands.detect import detect as detect_cmd
            detect_cmd()
        else:
            show_welcome()
        return

    from opun8.ui.messages import github_auth_start
    github_auth_start()


def _deploy_repository_from_github() -> None:
    """Handle the 'Deploy a repository' flow from the GitHub menu."""
    console.print()
    console.print("[bold cyan]🚀 Deploy a GitHub Repository[/bold cyan]")
    console.print("[dim]Select a repository to clone and deploy.[/dim]")
    console.print()

    repos = list_github_repos()
    if not repos:
        console.print("[yellow]No repositories found.[/yellow]")
        return

    for i, repo in enumerate(repos[:20], 1):
        private_tag = "[dim](private)[/dim]" if repo.get("private") else ""
        console.print(f"  [bold cyan]{i}[/]  [white]{repo['name']}[/white] {private_tag}")
    if len(repos) > 20:
        console.print(f"  [dim]... and {len(repos) - 20} more[/dim]")

    console.print()
    console.print("  [bold cyan]0[/] 🔙  [white]Go back[/white]")
    console.print()

    choice = _safe_prompt(
        "[bold cyan]➜[/] Select a repository",
        choices=[str(i) for i in range(0, min(len(repos) + 1, 21))],
        default="0",
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
        clone_url = selected_repo.get("url") or f"https://github.com/{get_authenticated_user()}/{repo_name}"

        console.print()
        console.print(f"[bold]Selected: [cyan]{repo_name}[/cyan][/bold]")
        console.print()

        console.print("[bold]Which platform would you like to deploy to?[/bold]")
        console.print()
        console.print("  [bold cyan]1[/] ▲  [white]Vercel[/white]  [dim](Recommended for frontend)[/dim]")
        console.print("  [bold cyan]2[/] 📦  [white]Netlify[/white]  [dim](Great for static sites and frontend)[/dim]")
        console.print("  [bold cyan]3[/] ☁️  [white]Render[/white]  [dim](Great for full-stack and Python)[/dim]")
        console.print()

        platform_choice = _safe_prompt(
            "[bold cyan]➜[/] Select a platform",
            choices=["1", "2", "3"],
            default="1",
        )

        if platform_choice == "1":
            from opun8.commands.repo import deploy_repository
            deploy_repository(clone_url, repo_name, platform="vercel")
        elif platform_choice == "2":
            from opun8.commands.repo import deploy_repository
            deploy_repository(clone_url, repo_name, platform="netlify")
        elif platform_choice == "3":
            from opun8.commands.repo import deploy_repository
            deploy_repository(clone_url, repo_name, platform="render")
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
        console.print(f"[green]{_sym('success')} Logged out of Vercel.[/green]")
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

    from opun8.ui.messages import vercel_auth_start
    vercel_auth_start()


# ──────────────────────────────────────────────────────────────
# RENDER COMMANDS ✅ FIXED (uses partner tone UI)
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
        console.print(f"[green]{_sym('success')} Logged out of Render.[/green]")
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

    # ✅ FIX: Use partner tone UI instead of old flow
    from opun8.ui.messages import render_auth_start
    render_auth_start()


def _switch_render_owner() -> None:
    """Interactive owner/workspace switching for Render."""
    token = get_render_token()
    if not token:
        console.print("[yellow]Not connected to Render. Run `opun8 render` first.[/yellow]")
        return

    owners = list_render_owners(token)
    if not owners:
        console.print("[yellow]No workspaces found.[/yellow]")
        return

    selected = prompt_owner_selection(token)
    if selected:
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
    table.add_column("Name", style="bold white", width=20, no_wrap=False)
    table.add_column("Type", style="dim", width=14)
    table.add_column("Status", style="dim", width=12)
    table.add_column("URL", style="cyan", width=30, no_wrap=False)

    for idx, service in enumerate(services, 1):
        name = _truncate(service.get("name", "Unknown"), 20)
        service_type = _truncate(service.get("type", "unknown"), 14)
        status = _truncate(service.get("status", "unknown"), 12)
        url = _truncate(service.get("url", "N/A"), 30)

        table.add_row(str(idx), name, service_type, status, url)

    console.print(table)
    console.print()

    console.print("[dim]Run [cyan]opun8 deploy[/cyan] to create a new service.[/dim]")
    console.print("[dim]Or visit [cyan]https://dashboard.render.com[/cyan] to manage your services.[/dim]")


def _truncate(value, length: int) -> str:
    """Truncate string with ellipsis."""
    text = str(value) if value is not None else ""
    if len(text) > length:
        return text[: max(length - 1, 0)] + "…"
    return text


# ──────────────────────────────────────────────────────────────
# NETLIFY COMMANDS
# ──────────────────────────────────────────────────────────────

@app.command()
def netlify(
    logout_flag: bool = typer.Option(
        False,
        "--logout",
        "-l",
        help="Logout from Netlify.",
    ),
    show_flag: bool = typer.Option(
        False,
        "--show",
        help="Show sites without re-authenticating.",
    ),
):
    """Connect to Netlify account."""
    if logout_flag:
        logout_netlify()
        console.print(f"[green]{_sym('success')} Logged out of Netlify.[/green]")
        return

    if show_flag:
        from opun8.commands.deploy import deploy as deploy_cmd
        set_netlify_deploy_callback(deploy_cmd)
        show_netlify_sites()
        return

    if is_netlify_authenticated():
        console.print("[green]✅ Already connected to Netlify.[/green]")
        console.print("[dim]To disconnect, run: opun8 netlify --logout[/dim]")
        console.print()
        from opun8.commands.deploy import deploy as deploy_cmd
        set_netlify_deploy_callback(deploy_cmd)
        show_netlify_sites()
        return

    from opun8.ui.messages import netlify_auth_start
    netlify_auth_start()


# ──────────────────────────────────────────────────────────────
# LOGOUT
# ──────────────────────────────────────────────────────────────

@app.command(name="logout")
def logout_all():
    """Logout from all services."""
    logout_github()
    logout_vercel()
    logout_render()
    logout_netlify()
    console.print("[green]✅ Logged out from all services.[/green]")


# ──────────────────────────────────────────────────────────────
# HELP
# ──────────────────────────────────────────────────────────────

@app.command()
def help():
    """Show all available commands."""
    from opun8.ui.messages import show_help
    show_help()


# ──────────────────────────────────────────────────────────────
# RUN THE APP
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app()