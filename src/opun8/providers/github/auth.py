"""
GitHub OAuth authentication for Opun8.
Now uses the Opun8 API backend instead of local .env file.

✅ FIX: UI has been removed from this file. All UI is now handled by
`ui/messages.py` -> `github_auth_start()` to avoid duplicate flows.
✅ FIX: Added retry logic to API config fetch (matches Vercel/Netlify/Render)
✅ FIX: User-visible progress messages during retries
✅ FIX: Exponential backoff for transient failures
✅ FIX: Proper error handling for all failure scenarios

Author: OPUN8 Team
Version: 0.1.6
"""

import os
import time
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

console = Console()

# ------------------------------------------------------------------------------
# API Configuration - Calls your deployed backend
# ------------------------------------------------------------------------------

# Your deployed API URL on Render
API_BASE_URL = os.environ.get("OPUN8_API_URL", "https://opun8-api.onrender.com")

# OAuth Configuration - these are handled by your API, not stored locally
# The CLI only needs the redirect URI for the callback server
REDIRECT_URI = "http://localhost:8080/callback"

_parsed_redirect = urllib.parse.urlparse(REDIRECT_URI)
CALLBACK_HOST = _parsed_redirect.hostname or "localhost"
CALLBACK_PORT = _parsed_redirect.port or 8080
CALLBACK_PATH = _parsed_redirect.path or "/callback"

SCOPES = "repo,workflow"
AUTHORIZATION_ENDPOINT = "https://github.com/login/oauth/authorize"

TOKEN_FILE = Path.home() / ".opun8" / "github_token.json"


def _build_authorize_url(state: str, retries: int = 3, timeout: int = 15) -> Optional[str]:
    """
    Build GitHub OAuth URL - client_id comes from your API.
    
    ✅ FIX: Added retry logic with exponential backoff.
    ✅ FIX: User-visible progress messages.
    
    Args:
        state: OAuth state parameter for CSRF protection
        retries: Number of retry attempts (default: 3)
        timeout: Timeout per attempt in seconds (default: 15)
    
    Returns:
        Full authorization URL, or None if all attempts fail
    """
    last_error = None
    console.print("[dim]🔍 Connecting to authentication service...[/dim]")
    
    for attempt in range(retries):
        try:
            if attempt > 0:
                console.print(f"[dim]⏳ Connecting to API (attempt {attempt + 1}/{retries})...[/dim]")
                time.sleep(1.5 * attempt)
            
            response = requests.get(
                f"{API_BASE_URL}/github/config",
                timeout=timeout
            )
            
            # 2xx success
            if 200 <= response.status_code < 300:
                client_id = response.json().get("client_id")
                if client_id:
                    if attempt > 0:
                        console.print("[green]✅ Connected to API successfully![/green]")
                    # Build the full URL with client_id
                    params = {
                        "client_id": client_id,
                        "redirect_uri": REDIRECT_URI,
                        "scope": SCOPES,
                        "state": state,
                    }
                    return f"{AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}"
                last_error = "Response missing client_id"
                _debug_log(f"GitHub config response missing client_id: {response.text}")
                continue
            
            # 3xx redirect - unlikely but handle
            if 300 <= response.status_code < 400:
                last_error = f"Redirect: {response.status_code} - {response.headers.get('Location')}"
                _debug_log(last_error)
                continue
            
            # 5xx server errors - retry
            if response.status_code >= 500:
                last_error = f"Server error (HTTP {response.status_code})"
                _debug_log(f"GitHub config failed: {response.status_code} - {response.text}")
                if attempt < retries - 1:
                    console.print("[dim]⏳ Server error, retrying...[/dim]")
                continue
            
            # 4xx client errors
            if response.status_code == 403:
                last_error = "403 Forbidden - Service suspended or quota exceeded"
                _debug_log(f"API returned 403: {response.text}")
                break
            
            if response.status_code == 404:
                last_error = "404 Not Found - Service not available"
                _debug_log(f"API returned 404")
                if attempt < retries - 1:
                    console.print("[dim]⏳ Service is waking up (Render free tier sleep)...[/dim]")
                continue
            
            if 400 <= response.status_code < 500:
                last_error = f"HTTP {response.status_code}"
                _debug_log(f"GitHub config failed: {response.status_code} - {response.text}")
                break
                
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection refused: {str(e)}"
            _debug_log(f"Connection error to API: {e}")
            if attempt < retries - 1:
                console.print("[dim]⏳ Cannot connect (service may be down or waking up)...[/dim]")
            continue
            
        except requests.exceptions.Timeout as e:
            last_error = f"Timeout: {str(e)}"
            _debug_log(f"Timeout connecting to API: {e}")
            if attempt < retries - 1:
                console.print("[dim]⏳ Service taking too long to respond...[/dim]")
            continue
            
        except requests.exceptions.SSLError as e:
            last_error = f"SSL Error: {str(e)}"
            _debug_log(f"SSL error: {e}")
            break
            
        except Exception as e:
            last_error = str(e)
            _debug_log(f"Error fetching GitHub config: {e}")
            break
    
    # ✅ FIX: Show clear error message
    console.print()
    console.print(Panel(
        f"[bold red]❌ Could not connect to GitHub authentication service[/bold red]\n\n"
        f"[yellow]⚠️  The backend API is currently unavailable.[/yellow]\n\n"
        f"[white]What you can do:[/white]\n"
        f"  • Wait a few minutes and try again (Render free tier may be waking up)\n"
        f"  • Check your internet connection\n"
        f"  • Try again later when the service is restored\n\n"
        f"[dim]💡 Error details: {last_error}[/dim]",
        border_style="red",
        padding=(1, 2),
        width=70,
    ))
    console.print()
    
    _debug_log(f"Failed to fetch GitHub config after {retries} attempts: {last_error}")
    return None


def _debug_log(message: str) -> None:
    """Log debug message to console if DEBUG enabled."""
    if os.environ.get("OPUN8_DEBUG"):
        console.print(f"[dim]🐛 {message}[/dim]")


def _panel_width(preferred: int = 70, minimum: int = 40) -> int:
    """Calculate safe panel width based on terminal size."""
    import shutil
    term_width = shutil.get_terminal_size(fallback=(preferred, 24)).columns
    return max(minimum, min(preferred, term_width - 4))


# ------------------------------------------------------------------------------
# Local callback server - catches the redirect
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
            pass

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
# Token Storage (local cache for user's access token)
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
# Login Flow - SILENT (No UI)
# ✅ FIX: All UI is now handled by ui/messages.py -> github_auth_start()
# ------------------------------------------------------------------------------

def login_to_github() -> Optional[str]:
    """
    Authenticate with GitHub using OAuth.
    
    ✅ FIX: This function is now SILENT — it does NOT show any UI.
    All UI is handled by ui/messages.py -> github_auth_start().
    
    Returns:
        Access token if successful, None otherwise.
    """
    state = secrets.token_urlsafe(32)
    authorize_url = _build_authorize_url(state)

    if not authorize_url:
        return None

    # Open browser silently
    webbrowser.open(authorize_url)

    # Wait for callback
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
    """
    Exchange code for token using your API (not .env)
    
    ✅ FIX: Sends code as JSON body, not query params.
    """
    try:
        if not code:
            console.print("[red]❌ No authorization code received.[/red]")
            return None

        # ✅ FIX: Send code as JSON body, not query params
        response = requests.post(
            f"{API_BASE_URL}/github/exchange",
            json={"code": code},
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

        if response.status_code != 200:
            try:
                error_data = response.json()
                error_msg = error_data.get("detail", error_data.get("message", "Unknown error"))
            except json.JSONDecodeError:
                error_msg = response.text[:200] if response.text else f"HTTP {response.status_code}"
            
            console.print(f"[red]❌ Token exchange failed: {error_msg}[/red]")
            return None

        data = response.json()
        token = data.get("access_token")

        if token:
            # Get user info from your API
            user_response = requests.get(
                f"{API_BASE_URL}/github/user",
                params={"access_token": token},
                timeout=10,
            )

            if user_response.status_code == 200:
                user = user_response.json()
                save_github_token(token, user)
            else:
                save_github_token(token, {"login": "Unknown"})

            return token
        else:
            console.print(f"[red]❌ No access token in response.[/red]")
            return None

    except requests.exceptions.ConnectionError:
        console.print(f"[red]❌ Could not connect to Opun8 API at {API_BASE_URL}[/red]")
        console.print("[dim]Make sure the API is running or check OPUN8_API_URL[/dim]")
        return None
    except requests.exceptions.Timeout:
        console.print(f"[red]❌ Request to Opun8 API timed out.[/red]")
        return None
    except Exception as e:
        console.print(f"[red]❌ Error exchanging code: {e}[/red]")
        return None


def get_github_user_info(token: str) -> Optional[Dict]:
    """Get GitHub user info - uses your API"""
    try:
        response = requests.get(
            f"{API_BASE_URL}/github/user",
            params={"access_token": token},
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
                    "clone_url": repo.get("clone_url", repo["html_url"] + ".git"),
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


# ------------------------------------------------------------------------------
# EXPORTS
# ------------------------------------------------------------------------------

__all__ = [
    "login_to_github",
    "is_authenticated",
    "get_github_token",
    "logout",
    "get_authenticated_user",
    "get_github_user",
    "get_github_user_info",
    "list_github_repos",
    "create_github_repo",
    "exchange_github_code_for_token",
]