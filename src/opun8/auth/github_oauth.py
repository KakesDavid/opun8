"""
GitHub OAuth authentication for Opun8.
"""

import os
import webbrowser
import requests
import json
import threading
import secrets
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional, Dict, List
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from dotenv import load_dotenv

load_dotenv()

console = Console()

# ------------------------------------------------------------------------------
# OAuth Configuration — READ FROM .env ONLY — NO HARDCODED VALUES
# ------------------------------------------------------------------------------

CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID")
CLIENT_SECRET = os.environ.get("GITHUB_CLIENT_SECRET")

# Actually honor GITHUB_REDIRECT_URI from .env instead of silently ignoring it.
REDIRECT_URI = os.environ.get("GITHUB_REDIRECT_URI", "http://localhost:8080/callback")

_parsed_redirect = urllib.parse.urlparse(REDIRECT_URI)
CALLBACK_HOST = _parsed_redirect.hostname or "localhost"
CALLBACK_PORT = _parsed_redirect.port or 8080
CALLBACK_PATH = _parsed_redirect.path or "/callback"

SCOPES = "repo,workflow"  # GitHub accepts comma-delimited scopes.

AUTHORIZATION_ENDPOINT = "https://github.com/login/oauth/authorize"
TOKEN_ENDPOINT = "https://github.com/login/oauth/access_token"

if not CLIENT_ID or not CLIENT_SECRET:
    console.print("[red]❌ GitHub credentials not found in .env file.[/red]")
    console.print("[dim]Please ensure GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET are set in .env[/dim]")

TOKEN_FILE = Path.home() / ".opun8" / "github_token.json"


def _build_authorize_url(state: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
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
                    b"<html><body><h2>GitHub authorization complete.</h2>"
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
    """Start a local server, wait for GitHub's redirect, then shut down."""
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
        result.error = "timed out waiting for GitHub to redirect back"

    return result


# ------------------------------------------------------------------------------
# Token Storage
# ------------------------------------------------------------------------------

def get_github_token() -> Optional[str]:
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f).get("access_token")
        except Exception:
            return None
    return None


def get_github_user() -> Optional[Dict]:
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r") as f:
                return json.load(f).get("user")
        except Exception:
            return None
    return None


def save_github_token(token: str, user_info: Dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TOKEN_FILE, "w") as f:
        json.dump({"access_token": token, "user": user_info}, f, indent=2)


# ------------------------------------------------------------------------------
# Login Flow
# ------------------------------------------------------------------------------

def login_to_github() -> Optional[str]:
    console.print()
    console.print(Panel(
        "[bold cyan]🔐 GitHub Authentication[/bold cyan]\n\n"
        "Opun8 needs access to GitHub to:\n"
        "  • Create repositories\n"
        "  • Push your code\n"
        "  • Enable auto-deploy\n\n"
        "[dim]Your browser will open for authorization.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()
    console.print("[bold]1[/] 🔑  [white]Login with GitHub[/white]  [dim](opens browser)[/dim]")
    console.print("[bold]2[/] ⏭️  [white]Skip[/white]  [dim](deploy without GitHub)[/dim]")
    console.print()

    choice = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2"],
        default="1",
        show_choices=False,
    )

    if choice == "2":
        console.print("\n[yellow]Skipping GitHub authentication.[/yellow]")
        return None

    if not CLIENT_ID or not CLIENT_SECRET:
        console.print("[red]❌ Missing GitHub credentials in .env file.[/red]")
        return None

    state = secrets.token_urlsafe(32)
    authorize_url = _build_authorize_url(state)

    console.print()
    console.print("[dim]🌐 Opening browser for GitHub authorization...[/dim]")
    console.print(f"[dim]Waiting on {REDIRECT_URI} for the redirect...[/dim]")
    console.print()

    webbrowser.open(authorize_url)

    console.print("[bold]Waiting for GitHub to redirect back...[/bold]")
    console.print("[dim]This happens automatically — no need to paste anything.[/dim]")
    console.print()

    result = _wait_for_callback()

    if result.error and not result.code:
        console.print(f"[red]❌ Authorization failed: {result.error}[/red]")
        return None

    if result.state != state:
        console.print("[red]❌ State mismatch — possible CSRF, aborting.[/red]")
        return None

    token = exchange_github_code_for_token(result.code)
    if not token:
        console.print("[red]❌ Failed to exchange code for a token.[/red]")
    return token


def exchange_github_code_for_token(code: str) -> Optional[str]:
    try:
        if not code:
            console.print("[red]❌ No authorization code received.[/red]")
            return None

        if not CLIENT_SECRET:
            console.print("[red]❌ GITHUB_CLIENT_SECRET not found in .env file.[/red]")
            return None

        response = requests.post(
            TOKEN_ENDPOINT,
            headers={"Accept": "application/json"},
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=30,
        )

        data = response.json()

        if "access_token" in data:
            token = data["access_token"]

            user = get_github_user_info(token)
            if user:
                save_github_token(token, user)
                console.print()
                console.print(f"[bold green]✅ Connected as: {user.get('login', 'Unknown')}[/bold green]")
                console.print("[dim]Token saved securely for future use.[/dim]")
            else:
                save_github_token(token, {"login": "Unknown"})

            return token
        else:
            error_msg = data.get("error_description", data.get("error", "Unknown error"))
            console.print(f"[red]Failed to get token: {error_msg}[/red]")
            return None

    except Exception as e:
        console.print(f"[red]Error exchanging code: {e}[/red]")
        return None


def get_github_user_info(token: str) -> Optional[Dict]:
    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        return response.json() if response.status_code == 200 else None
    except Exception:
        return None


def is_authenticated() -> bool:
    return get_github_token() is not None


def logout() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        console.print("[green]✅ Logged out of GitHub.[/green]")
    else:
        console.print("[yellow]Not logged in.[/yellow]")


def get_authenticated_user() -> Optional[str]:
    user = get_github_user()
    if user:
        return user.get("login")
    return None


def list_github_repos(token: Optional[str] = None) -> List[Dict]:
    if token is None:
        token = get_github_token()

    if not token:
        return []

    try:
        response = requests.get(
            "https://api.github.com/user/repos",
            headers={"Authorization": f"Bearer {token}"},
            params={"per_page": 50, "sort": "updated"},
            timeout=10,
        )

        if response.status_code == 200:
            repos = response.json()
            return [
                {
                    "name": repo["name"],
                    "full_name": repo["full_name"],
                    "private": repo["private"],
                    "url": repo["html_url"],
                    "description": repo.get("description", ""),
                    "updated_at": repo.get("updated_at", ""),
                }
                for repo in repos
            ]
        return []
    except Exception:
        return []


def create_github_repo(token: Optional[str], name: str, description: str = "", private: bool = False) -> Optional[Dict]:
    if token is None:
        token = get_github_token()

    if not token:
        return None

    try:
        response = requests.post(
            "https://api.github.com/user/repos",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "name": name,
                "description": description,
                "private": private,
                "auto_init": True,
            },
            timeout=30,
        )

        if response.status_code == 201:
            return response.json()
        return None
    except Exception:
        return None