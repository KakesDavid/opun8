"""
Vercel OAuth authentication for Opun8.
Fixed: catches the OAuth redirect automatically via a local HTTP server
instead of asking the user to paste the code by hand.
"""

import os
import webbrowser
import requests
import json
import threading
import hashlib
import base64
import secrets
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional, Dict, Callable
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from dotenv import load_dotenv

load_dotenv()

console = Console()

# ------------------------------------------------------------------------------
# OAuth Configuration — READ FROM .env ONLY — NO HARDCODED VALUES
#
# This targets the "Sign in with Vercel" Authorization Server (Apps created
# under Team Settings -> Apps, client_id like cl_xxx). It is NOT the same as
# the classic "Integration" OAuth flow and uses different endpoints, plus
# mandatory PKCE.
# ------------------------------------------------------------------------------

CLIENT_ID = os.environ.get("VERCEL_CLIENT_ID")
CLIENT_SECRET = os.environ.get("VERCEL_CLIENT_SECRET")

CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8080
CALLBACK_PATH = "/vercel/callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"

AUTHORIZATION_ENDPOINT = "https://vercel.com/oauth/authorize"
TOKEN_ENDPOINT = "https://api.vercel.com/login/oauth/token"
USERINFO_ENDPOINT = "https://api.vercel.com/login/oauth/userinfo"

# Identity scopes only. Whether the resulting access token can call
# deployment/project endpoints depends on what's enabled in the App's
# Permissions tab in the Vercel dashboard, not on these scopes.
SCOPES = "openid email profile offline_access"

if not CLIENT_ID:
    console.print("[red]❌ VERCEL_CLIENT_ID not found in .env file.[/red]")
    console.print("[dim]Please ensure VERCEL_CLIENT_ID is set in .env[/dim]")
    console.print(
        "[dim]VERCEL_CLIENT_SECRET is not required for this flow — Opun8 authenticates "
        "as a public client using PKCE, per Vercel's guidance for CLIs.[/dim]"
    )

TOKEN_FILE = Path.home() / ".opun8" / "vercel_token.json"


# ------------------------------------------------------------------------------
# Deploy Callback
# ------------------------------------------------------------------------------

_DEPLOY_CALLBACK: Optional[Callable] = None


def set_deploy_callback(callback: Callable) -> None:
    """Set the deploy callback function for empty-state flow."""
    global _DEPLOY_CALLBACK
    _DEPLOY_CALLBACK = callback


def get_deploy_callback() -> Optional[Callable]:
    """Get the deploy callback function."""
    return _DEPLOY_CALLBACK


# ------------------------------------------------------------------------------
# PKCE helpers
# ------------------------------------------------------------------------------

def _generate_pkce_pair():
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode("ascii")
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return code_verifier, code_challenge


def _build_authorize_url(state: str, nonce: str, code_challenge: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}"


# ------------------------------------------------------------------------------
# Local callback server — catches the redirect instead of asking the user
# to copy/paste a code out of a dead browser tab.
# ------------------------------------------------------------------------------

class _CallbackResult:
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


def _make_handler(result: _CallbackResult, done_event: threading.Event):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path != CALLBACK_PATH:
                self.send_response(404)
                self.end_headers()
                return

            params = urllib.parse.parse_qs(parsed.query)
            result.code = params.get("code", [None])[0]
            result.state = params.get("state", [None])[0]
            result.error = params.get("error_description", params.get("error", [None]))[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if result.code:
                self.wfile.write(
                    b"<html><body><h2>Vercel authorization complete.</h2>"
                    b"<p>You can close this tab and return to the terminal.</p></body></html>"
                )
            else:
                self.wfile.write(
                    b"<html><body><h2>Authorization failed.</h2>"
                    b"<p>You can close this tab and return to the terminal.</p></body></html>"
                )
            done_event.set()

        def log_message(self, format, *args):
            pass  # silence default HTTP server logging

    return Handler


def _wait_for_callback(timeout: int = 180) -> _CallbackResult:
    """Start a local server, wait for Vercel's redirect, then shut down."""
    result = _CallbackResult()
    done_event = threading.Event()
    handler = _make_handler(result, done_event)

    server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    got_it = done_event.wait(timeout=timeout)
    server.shutdown()
    server_thread.join()

    if not got_it:
        result.error = "timed out waiting for Vercel to redirect back"

    return result


# ------------------------------------------------------------------------------
# Token Storage
# ------------------------------------------------------------------------------

def _read_token_file() -> Dict:
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def _write_token_file(data: Dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_vercel_token() -> Optional[str]:
    return _read_token_file().get("access_token")


def get_vercel_user() -> Optional[Dict]:
    return _read_token_file().get("user")


def save_vercel_token(token: str, user_info: Dict, refresh_token: Optional[str] = None) -> None:
    """Save the token/user, preserving any existing team scope selection."""
    data = _read_token_file()
    data.update({
        "access_token": token,
        "refresh_token": refresh_token,
        "user": user_info,
    })
    _write_token_file(data)


def get_vercel_scope() -> Dict:
    """Returns {'team_id': str|None, 'team_name': str}. team_id=None means Personal Account."""
    return _read_token_file().get("scope", {"team_id": None, "team_name": "Personal Account"})


def save_vercel_scope(team_id: Optional[str], team_name: str) -> None:
    data = _read_token_file()
    data["scope"] = {"team_id": team_id, "team_name": team_name}
    _write_token_file(data)


# ------------------------------------------------------------------------------
# Login Flow
# ------------------------------------------------------------------------------

def login_to_vercel() -> Optional[str]:
    console.print()
    console.print(Panel(
        "[bold cyan]▲ Vercel Authentication[/bold cyan]\n\n"
        "Opun8 needs access to Vercel to:\n"
        "  • Create projects\n"
        "  • Deploy your code\n"
        "  • Get deployment URLs\n\n"
        "[dim]Your browser will open for authorization.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()
    console.print("[bold]1[/] 🔑  [white]Login with Vercel[/white]  [dim](opens browser)[/dim]")
    console.print("[bold]2[/] ⏭️  [white]Skip[/white]  [dim](deploy without Vercel)[/dim]")
    console.print()

    choice = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2"],
        default="1",
        show_choices=False,
    )

    if choice == "2":
        console.print("\n[yellow]Skipping Vercel authentication.[/yellow]")
        return None

    if not CLIENT_ID:
        console.print("[red]❌ Missing VERCEL_CLIENT_ID in .env file.[/red]")
        return None

    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    authorize_url = _build_authorize_url(state, nonce, code_challenge)

    console.print()
    console.print("[dim]🌐 Opening browser for Vercel authorization...[/dim]")
    console.print(f"[dim]Waiting on {REDIRECT_URI} for the redirect...[/dim]")
    console.print()

    webbrowser.open(authorize_url)

    console.print("[bold]Waiting for Vercel to redirect back...[/bold]")
    console.print("[dim]This happens automatically — no need to paste anything.[/dim]")
    console.print()

    result = _wait_for_callback()

    if result.error and not result.code:
        console.print(f"[red]❌ Authorization failed: {result.error}[/red]")
        return None

    if result.state != state:
        console.print("[red]❌ State mismatch — possible CSRF, aborting.[/red]")
        return None

    token = exchange_code_for_token(result.code, code_verifier)
    if not token:
        console.print("[red]❌ Failed to exchange code for a token.[/red]")
    else:
        prompt_team_selection(token)
        show_vercel_projects()
    return token


def exchange_code_for_token(code: str, code_verifier: str) -> Optional[str]:
    """Exchange OAuth code for access token via the Sign-in-with-Vercel token endpoint."""
    try:
        if not code:
            console.print("[red]❌ No authorization code received.[/red]")
            return None

        response = requests.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": REDIRECT_URI,
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            timeout=30,
        )

        if response.status_code == 200:
            data = response.json()
            if "access_token" in data:
                token = data["access_token"]
                refresh_token = data.get("refresh_token")
                user = get_vercel_user_info(token)
                if user:
                    save_vercel_token(token, user, refresh_token)
                    console.print()
                    console.print(f"[bold green]✅ Connected to Vercel as: {user.get('name', 'Unknown')}[/bold green]")
                else:
                    save_vercel_token(token, {"name": "Unknown"}, refresh_token)
                    console.print("[yellow]Could not get user info, but token saved.[/yellow]")
                return token
            else:
                error = data.get("error_description", data.get("error", "Unknown error"))
                console.print(f"[red]Failed to get token: {error}[/red]")
                return None
        else:
            console.print(f"[red]HTTP {response.status_code}: {response.text}[/red]")
            return None

    except Exception as e:
        console.print(f"[red]Error exchanging code: {e}[/red]")
        return None


def get_vercel_user_info(token: str) -> Optional[Dict]:
    try:
        response = requests.post(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code != 200:
            return None
        data = response.json()
        # userinfo returns OIDC claims (name/preferred_username/email), not
        # the classic /v2/user shape — normalize "name" for the console print.
        if "name" not in data and "preferred_username" in data:
            data["name"] = data["preferred_username"]
        return data
    except Exception:
        return None


def is_vercel_authenticated() -> bool:
    return get_vercel_token() is not None


def logout_vercel() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        console.print("[green]✅ Logged out of Vercel.[/green]")
    else:
        console.print("[yellow]Not logged in.[/yellow]")


# ------------------------------------------------------------------------------
# Teams
# ------------------------------------------------------------------------------

TEAMS_ENDPOINT = "https://api.vercel.com/v2/teams"


def list_vercel_teams(token: str) -> Optional[list]:
    """
    Fetch the Teams the authenticated user is a member of.
    Returns [] if the user has none, None on a real fetch failure.
    """
    try:
        response = requests.get(
            TEAMS_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            params={"limit": 100},
            timeout=15,
        )

        if response.status_code == 200:
            return response.json().get("teams", [])

        if response.status_code == 403:
            console.print("[red]❌ Access denied fetching teams.[/red]")
            console.print(
                "[dim]Enable the team-read permission (App → Permissions tab in the "
                "Vercel dashboard) if you want team support.[/dim]"
            )
        else:
            console.print(f"[red]HTTP {response.status_code}: {response.text}[/red]")
        return None

    except Exception as e:
        console.print(f"[red]Error fetching teams: {e}[/red]")
        return None


def prompt_team_selection(token: str) -> None:
    """Ask which account/team scope to use going forward, and persist the choice."""
    teams = list_vercel_teams(token)

    if not teams:
        # No teams, or the fetch failed/lacks permission — fall back to personal account.
        save_vercel_scope(None, "Personal Account")
        return

    console.print()
    console.print("[bold]Where should Opun8 deploy to?[/bold]")
    console.print("[bold]0[/] 👤  [white]Personal Account[/white]")
    for i, team in enumerate(teams, start=1):
        label = team.get("name") or team.get("slug") or "Unnamed team"
        console.print(f"[bold]{i}[/] 👥  [white]{label}[/white]")
    console.print()

    selection = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=[str(i) for i in range(0, len(teams) + 1)],
        default="0",
        show_choices=False,
    )

    if selection == "0":
        save_vercel_scope(None, "Personal Account")
        console.print("[green]✅ Using Personal Account.[/green]")
    else:
        team = teams[int(selection) - 1]
        label = team.get("name") or team.get("slug") or "Unnamed team"
        save_vercel_scope(team.get("id"), label)
        console.print(f"[green]✅ Using team: {label}[/green]")


def switch_vercel_team() -> None:
    """Standalone entry point (e.g. `opun8 vercel switch-team`) to change scope
    without re-running the full login flow."""
    token = get_vercel_token()
    if not token:
        console.print("[yellow]Not connected to Vercel yet. Run the login flow first.[/yellow]")
        return
    prompt_team_selection(token)


# ------------------------------------------------------------------------------
# Project Listing
# ------------------------------------------------------------------------------

PROJECTS_ENDPOINT = "https://api.vercel.com/v9/projects"


def list_vercel_projects(token: str, team_id: Optional[str] = None) -> Optional[list]:
    """
    Fetch the user's (or team's) Vercel projects.
    Returns a list of project dicts, or None on failure (auth/permission error).
    """
    try:
        params = {"limit": 100}
        if team_id:
            params["teamId"] = team_id

        response = requests.get(
            PROJECTS_ENDPOINT,
            headers={"Authorization": f"Bearer {token}"},
            params=params,
            timeout=15,
        )

        if response.status_code == 200:
            return response.json().get("projects", [])

        if response.status_code == 403:
            console.print("[red]❌ Access denied fetching projects.[/red]")
            console.print(
                "[dim]Your Vercel App may not have the project-read permission enabled "
                "(App → Permissions tab in the Vercel dashboard).[/dim]"
            )
        else:
            console.print(f"[red]HTTP {response.status_code}: {response.text}[/red]")
        return None

    except Exception as e:
        console.print(f"[red]Error fetching projects: {e}[/red]")
        return None


def show_vercel_projects(deploy_callback=None, team_id: Optional[str] = None) -> None:
    """
    Display the authenticated user's Vercel projects, scoped to whichever
    team (or personal account) was selected via prompt_team_selection /
    switch_vercel_team — unless team_id is explicitly passed to override it.

    If there are none, show an empty state with an option to deploy the first one.

    deploy_callback: an optional zero-arg function to call if the user chooses
    to deploy their first project from the empty state (wire this up to your
    existing deploy command).
    """
    token = get_vercel_token()
    if not token:
        console.print("[yellow]Not connected to Vercel yet. Run the login flow first.[/yellow]")
        return

    # Use provided callback or fallback to global one
    if deploy_callback is None:
        deploy_callback = get_deploy_callback()

    user = get_vercel_user()
    scope = get_vercel_scope()
    effective_team_id = team_id if team_id is not None else scope.get("team_id")

    console.print()
    if user:
        console.print(f"[dim]Connected as {user.get('name', 'Unknown')}[/dim]")
    console.print(f"[dim]Scope: {scope.get('team_name', 'Personal Account')}[/dim]")

    projects = list_vercel_projects(token, team_id=effective_team_id)

    if projects is None:
        # Fetch failed — error already printed by list_vercel_projects.
        return

    if len(projects) == 0:
        console.print()
        console.print(Panel(
            "[bold]No project yet[/bold]\n\n"
            "[dim]You haven't deployed anything to Vercel through Opun8 yet.[/dim]",
            border_style="cyan",
            padding=(1, 2),
            width=60,
        ))
        console.print()
        choice = Prompt.ask(
            "[bold cyan]➜[/] Deploy your first project now?",
            choices=["y", "n"],
            default="y",
            show_choices=False,
        )
        if choice.lower() == "y":
            if deploy_callback:
                deploy_callback()
            else:
                console.print("[yellow]No deploy command wired up yet — run your deploy command directly.[/yellow]")
        return

    from rich.table import Table

    table = Table(title=f"▲ Vercel Projects ({len(projects)})", border_style="cyan")
    table.add_column("Name", style="bold white")
    table.add_column("Framework", style="dim")
    table.add_column("Latest Domain", style="cyan")
    table.add_column("Updated", style="dim")

    for project in projects:
        name = project.get("name", "—")
        framework = project.get("framework") or "—"
        targets = project.get("targets", {}) or {}
        production = targets.get("production") or {}
        domain = production.get("alias", [None])[0] if production.get("alias") else "—"
        updated_at = project.get("updatedAt")
        updated_display = "—"
        if updated_at:
            import datetime
            updated_display = datetime.datetime.fromtimestamp(updated_at / 1000).strftime("%Y-%m-%d")

        table.add_row(name, framework, domain or "—", updated_display)

    console.print()
    console.print(table)
    console.print()