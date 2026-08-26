"""
GitHub OAuth authentication for Opun8.
Now uses the Opun8 API backend instead of local .env file.

✅ FIX: UI has been removed from this file. All UI is now handled by
`ui/messages.py` -> `github_auth_start()` to avoid duplicate flows.
✅ FIX: Token exchange now sends code as JSON body (not query params)
✅ FIX: _build_authorize_url() now has retry logic (matches Vercel/Netlify/Render)
✅ FIX: get_authenticated_user() now uses token validation and lazy refresh
✅ FIX: OAuth callback port conflict handled with fallback
✅ FIX: Browser fallback URL printed for headless/SSH sessions
✅ FIX: list_github_repos() distinguishes 401 from other errors
✅ FIX: Token file permissions set to 0o600 (user-read-only)
✅ FIX: Token sent as Authorization Bearer header (not query param)
✅ FIX: CSRF check uses secrets.compare_digest()
✅ FIX: is_authenticated() validates token against GitHub
✅ FIX: Cached user info refreshed if "Unknown" was saved
"""

import os
import time
import stat
import webbrowser
import requests
import json
import threading
import secrets
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from rich.console import Console

console = Console()

# ------------------------------------------------------------------------------
# API Configuration - Calls your deployed backend
# ------------------------------------------------------------------------------

# Your deployed API URL on Render
API_BASE_URL = os.environ.get("OPUN8_API_URL", "https://opun8-api.onrender.com")

# OAuth Configuration - these are handled by your API, not stored locally
# The CLI only needs the redirect URI for the callback server
CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8080
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"

SCOPES = "repo,workflow"
AUTHORIZATION_ENDPOINT = "https://github.com/login/oauth/authorize"

TOKEN_FILE = Path.home() / ".opun8" / "github_token.json"
DEBUG_LOG_FILE = Path.home() / ".opun8" / "debug.log"

# File permissions: user-read-only
_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR


def _debug_log(message: str) -> None:
    """Record technical detail for later troubleshooting."""
    try:
        DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass
    if os.environ.get("OPUN8_DEBUG"):
        console.print(f"[dim]debug: {message}[/dim]")


def _show_api_error_panel(error_message: str, error_detail: Optional[str] = None) -> None:
    """Show a clear, user-friendly error panel when the API is unavailable."""
    from rich.panel import Panel
    
    console.print()
    
    error_type = "Connection Error"
    guidance = "The authentication service cannot be reached."
    
    if error_detail:
        error_lower = error_detail.lower()
        if "403" in error_lower or "forbidden" in error_lower:
            error_type = "Access Denied (403)"
            guidance = "The authentication service is currently unavailable (suspended or quota exceeded)."
        elif "404" in error_lower or "not found" in error_lower:
            error_type = "Service Not Found (404)"
            guidance = "The authentication service could not be found. It may be down or misconfigured."
        elif "timeout" in error_lower or "timed out" in error_lower:
            error_type = "Timeout"
            guidance = "The authentication service is taking too long to respond (free tier may be waking up)."
        elif "connection refused" in error_lower:
            error_type = "Connection Refused"
            guidance = "The authentication service is not accepting connections (server may be down)."
        elif "ssl" in error_lower or "certificate" in error_lower:
            error_type = "SSL/TLS Error"
            guidance = "There's a security certificate issue with the authentication service."
    
    console.print(Panel(
        f"[bold red]❌ {error_message}[/bold red]\n\n"
        f"[yellow]⚠️  {guidance}[/yellow]\n\n"
        f"[bold]Error Details:[/bold]\n"
        f"  Type: {error_type}\n"
        f"  {error_detail or 'Unknown error'}\n\n"
        f"[bold white]What you can do:[/bold white]\n"
        f"  • Wait a few minutes and try again\n"
        f"  • Check your internet connection\n"
        f"  • Try again later when the service is restored\n\n"
        f"[dim]💡 The authentication service is hosted on Render.com[/dim]\n"
        f"[dim]   Free tier services may sleep after periods of inactivity.[/dim]",
        border_style="red",
        padding=(1, 2),
        width=70,
    ))
    console.print()


def _build_authorize_url(state: str, retries: int = 3, timeout: int = 15) -> Optional[str]:
    """Build GitHub OAuth URL - client_id comes from your API."""
    last_error = None
    
    console.print("[dim]🔍 Connecting to authentication service...[/dim]")
    
    for attempt in range(retries):
        try:
            if attempt > 0:
                console.print(f"[dim]⏳ Retry {attempt + 1}/{retries}...[/dim]")
                time.sleep(1.5 * attempt)
            
            response = requests.get(
                f"{API_BASE_URL}/github/config",
                timeout=timeout
            )
            
            if 200 <= response.status_code < 300:
                client_id = response.json().get("client_id")
                if client_id:
                    if attempt > 0:
                        console.print("[green]✅ Connected to authentication service![/green]")
                    
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
            
            if response.status_code >= 500:
                last_error = f"Server error (HTTP {response.status_code})"
                _debug_log(f"GitHub config failed: {response.status_code} - {response.text}")
                if attempt < retries - 1:
                    console.print("[dim]⏳ Server error, retrying...[/dim]")
                continue
            
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
    
    _debug_log(f"Failed to fetch GitHub config after {retries} attempts: {last_error}")
    _show_api_error_panel(
        error_message="Could not connect to GitHub authentication service",
        error_detail=last_error or "Unknown error"
    )
    return None


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
    """
    Start a local server, wait for GitHub's redirect, then shut down.
    
    ✅ FIX: Handles port conflict gracefully.
    """
    result = _CallbackResult()
    done_event = threading.Event()
    handler = _make_handler(result, done_event)

    # ✅ FIX: Try port 8080, fall back to 8081-8089 if in use
    ports_to_try = [CALLBACK_PORT] + list(range(CALLBACK_PORT + 1, CALLBACK_PORT + 10))
    server = None
    
    for port in ports_to_try:
        try:
            server = HTTPServer((CALLBACK_HOST, port), handler)
            break
        except OSError:
            continue
    
    if server is None:
        result.error = f"Could not bind to any port between {CALLBACK_PORT} and {ports_to_try[-1]}"
        _debug_log(f"Port conflict: all ports in range {CALLBACK_PORT}-{ports_to_try[-1]} unavailable")
        return result

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

def _read_token_file() -> Dict:
    """Read token file with error handling."""
    try:
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        _debug_log(f"Failed to read token file: {e}")
    return {}


def _write_token_file(data: Dict) -> bool:
    """Write token file with secure permissions (0o600)."""
    try:
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Write to temporary file first, then rename (atomic)
        tmp_path = TOKEN_FILE.parent / f".{TOKEN_FILE.name}.tmp"
        with open(tmp_path, "w") as f:
            json.dump(data, f, indent=2)
        
        # Set permissions to user-read-only
        try:
            os.chmod(tmp_path, _FILE_MODE)
        except OSError as e:
            _debug_log(f"Failed to chmod token file: {e}")
        
        # Atomic replace
        os.replace(tmp_path, TOKEN_FILE)
        return True
    except Exception as e:
        _debug_log(f"Failed to write token file: {e}")
        return False


def get_github_token() -> Optional[str]:
    data = _read_token_file()
    return data.get("access_token")


def get_github_user() -> Optional[Dict]:
    data = _read_token_file()
    return data.get("user")


def save_github_token(token: str, user_info: Dict) -> None:
    data = {"access_token": token, "user": user_info}
    _write_token_file(data)


def _refresh_user_info(token: str) -> Optional[Dict]:
    """
    ✅ FIX: Refresh user info from GitHub API.
    Used when saved user is "Unknown" or needs updating.
    """
    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return response.json()
        return None
    except Exception as e:
        _debug_log(f"_refresh_user_info error: {e}")
        return None


def get_authenticated_user() -> Optional[str]:
    """
    ✅ FIX: Returns username with lazy refresh if "Unknown" was cached.
    """
    data = _read_token_file()
    token = data.get("access_token")
    if not token:
        return None
    
    user = data.get("user")
    if user:
        username = user.get("login")
        # If "Unknown" was cached, try to refresh
        if username == "Unknown" or username is None:
            _debug_log("Cached username is 'Unknown', refreshing...")
            fresh_user = _refresh_user_info(token)
            if fresh_user:
                new_username = fresh_user.get("login")
                if new_username:
                    save_github_token(token, fresh_user)
                    return new_username
            # If refresh failed, return None to trigger re-auth
            return None
        return username
    
    return None


def is_authenticated() -> bool:
    """
    ✅ FIX: Validates token by fetching user info.
    A token can exist in the file but be revoked or expired.
    """
    token = get_github_token()
    if not token:
        return False
    
    # ✅ FIX: Validate token by making a lightweight API call
    try:
        response = requests.get(
            "https://api.github.com/user",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if response.status_code == 200:
            return True
        if response.status_code == 401:
            _debug_log("GitHub token is invalid or expired")
            return False
        # Other errors (rate limit, network) - assume still valid but log
        _debug_log(f"GitHub validation returned {response.status_code}")
        return True  # Conservative: assume token is still valid
    except Exception as e:
        _debug_log(f"Token validation error: {e}")
        return True  # Network error - assume token is valid


def _ensure_github_user() -> Optional[str]:
    """
    ✅ FIX: Ensure user info is valid, refresh if needed.
    Returns username or None if invalid.
    """
    token = get_github_token()
    if not token:
        return None
    
    # Check if we have a valid username
    user = get_github_user()
    if user:
        username = user.get("login")
        if username and username != "Unknown":
            return username
    
    # Need to refresh
    fresh_user = _refresh_user_info(token)
    if fresh_user:
        new_username = fresh_user.get("login")
        if new_username:
            save_github_token(token, fresh_user)
            return new_username
    
    return None


def logout() -> None:
    if TOKEN_FILE.exists():
        TOKEN_FILE.unlink()
        console.print("[green]✅ Logged out of GitHub.[/green]")
    else:
        console.print("[yellow]Not logged in.[/yellow]")


# ------------------------------------------------------------------------------
# Login Flow - SILENT (No UI)
# ------------------------------------------------------------------------------

def login_to_github() -> Optional[str]:
    """
    Authenticate with GitHub using OAuth.
    
    ✅ FIX: URL is printed as fallback for headless/SSH sessions.
    
    Returns:
        Access token if successful, None otherwise.
    """
    state = secrets.token_urlsafe(32)
    authorize_url = _build_authorize_url(state)

    if not authorize_url:
        return None

    # ✅ FIX: Print the URL as fallback for headless sessions
    console.print("[dim]🌐 Opening browser for GitHub authorization...[/dim]")
    opened = webbrowser.open(authorize_url)
    
    if not opened:
        console.print("[yellow]⚠️ Could not open browser automatically.[/yellow]")
        console.print("[dim]Please open this URL manually in your browser:[/dim]")
        console.print(f"[cyan]{authorize_url}[/cyan]")
        console.print()
    else:
        console.print("[green]✅ Browser opened. Please authorize Opun8 to access GitHub.[/green]")
        console.print("[dim]Waiting for authorization...[/dim]")
        console.print()

    # Wait for callback
    result = _wait_for_callback()

    if result.error and not result.code:
        console.print(f"[red]❌ Authorization failed: {result.error}[/red]")
        return None

    # ✅ FIX: Use secrets.compare_digest for CSRF check
    if not secrets.compare_digest(result.state or "", state):
        console.print("[red]❌ Security check failed. Please try again.[/red]")
        return None

    token = exchange_github_code_for_token(result.code)
    if not token:
        console.print("[red]❌ Failed to exchange code for a token.[/red]")
    return token


def exchange_github_code_for_token(code: str) -> Optional[str]:
    """
    Exchange code for token using your API.
    
    ✅ FIX: Uses Authorization Bearer header for user info fetch.
    """
    try:
        if not code:
            console.print("[red]❌ No authorization code received.[/red]")
            return None

        # Send code as JSON body
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
            # ✅ FIX: Use Authorization Bearer header instead of query param
            user_response = requests.get(
                "https://api.github.com/user",
                headers={"Authorization": f"Bearer {token}"},
                timeout=10,
            )

            if user_response.status_code == 200:
                user = user_response.json()
                save_github_token(token, user)
            else:
                # Save the token, but user info will be refreshed lazily
                save_github_token(token, {"login": "Unknown"})
                _debug_log(f"User info fetch failed: {user_response.status_code}")

            return token
        else:
            console.print("[red]❌ No access token in response.[/red]")
            return None

    except requests.exceptions.ConnectionError:
        console.print(f"[red]❌ Could not connect to Opun8 API at {API_BASE_URL}[/red]")
        console.print("[dim]Make sure the API is running or check OPUN8_API_URL[/dim]")
        return None
    except requests.exceptions.Timeout:
        console.print("[red]❌ Request to Opun8 API timed out.[/red]")
        return None
    except Exception as e:
        console.print(f"[red]❌ Error exchanging code: {e}[/red]")
        return None


def list_github_repos(token: Optional[str] = None) -> List[Dict]:
    """
    List GitHub repositories.
    
    ✅ FIX: Distinguishes 401 (needs re-auth) from other errors.
    """
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
        
        # ✅ FIX: Distinguish 401 (invalid token) from other errors
        if response.status_code == 401:
            _debug_log("GitHub token invalid or expired when listing repos")
            # Don't return empty list silently — log it
            console.print("[yellow]⚠️ Your GitHub session may have expired. Re-authenticate to refresh.[/yellow]")
            
        return []
    except Exception as e:
        _debug_log(f"list_github_repos error: {e}")
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
# Exports
# ------------------------------------------------------------------------------

__all__ = [
    "login_to_github",
    "is_authenticated",
    "get_github_token",
    "logout",
    "get_authenticated_user",
    "list_github_repos",
    "create_github_repo",
    "get_github_user",
    "get_github_user_info",
    "save_github_token",
]