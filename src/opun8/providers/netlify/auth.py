"""
Netlify OAuth authentication for Opun8.
Now uses the Opun8 API backend instead of local .env file.

✅ FIX: UI has been removed from this file. All UI is now handled by
`ui/messages.py` -> `netlify_auth_start()` to avoid duplicate flows.

✅ FIX: Added clear user-facing error messages when API is unavailable.
✅ FIX: Shows specific error details (403, 404, timeout, connection refused).
"""

import os
import stat
import time
import webbrowser
import requests
import json
import threading
import hashlib
import base64
import secrets
import datetime
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional, Dict, Callable, List
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table
from rich.panel import Panel

console = Console()

# ------------------------------------------------------------------------------
# API Configuration - Calls your deployed backend
# ------------------------------------------------------------------------------

# Your deployed API URL on Render
API_BASE_URL = os.environ.get("OPUN8_API_URL", "https://opun8-api.onrender.com")

# OAuth Configuration - these are handled by your API, not stored locally
# The CLI only needs the redirect URI for the callback server
CALLBACK_HOST = "localhost"
CALLBACK_PORT = 4242
CALLBACK_PATH = "/netlify/callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"

AUTHORIZATION_ENDPOINT = "https://app.netlify.com/authorize"
TOKEN_ENDPOINT = "https://api.netlify.com/oauth/token"
USERINFO_ENDPOINT = "https://api.netlify.com/api/v1/user"

SCOPES = ""  # Netlify doesn't require specific scopes for basic access

# How long before an access token's real expiry we proactively refresh it.
TOKEN_REFRESH_SKEW_SECONDS = 120

TOKEN_FILE = Path.home() / ".opun8" / "netlify_token.json"
DEBUG_LOG_FILE = Path.home() / ".opun8" / "debug.log"

_DIR_MODE = stat.S_IRWXU
_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR

# Token cache with TTL to prevent redundant reads
_token_cache: Optional[Dict] = None
_cache_timestamp: float = 0
CACHE_TTL: int = 2  # seconds


def _debug_log(message: str) -> None:
    """Record technical detail for later troubleshooting."""
    try:
        DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass
    if os.environ.get("OPUN8_DEBUG"):
        console.print(f"[dim]debug: {message}[/dim]")


def _show_error(message: str, hint: Optional[str] = None, debug_detail: Optional[str] = None) -> None:
    """Show user-friendly error message."""
    console.print(f"[red]❌ {message}[/red]")
    if hint:
        console.print(f"[dim]{hint}[/dim]")
    if debug_detail:
        _debug_log(debug_detail)


def _show_api_error_panel(error_message: str, error_detail: Optional[str] = None) -> None:
    """
    Show a clear, user-friendly error panel when the API is unavailable.
    
    ✅ FIX: New function to display clear error messages.
    """
    console.print()
    
    # Determine error type and provide helpful guidance
    error_type = "Connection Error"
    guidance = "The backend authentication service cannot be reached."
    
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
        f"[bold red]❌ Authentication Service Unavailable[/bold red]\n\n"
        f"[yellow]⚠️  {guidance}[/yellow]\n\n"
        f"[bold]Error Details:[/bold]\n"
        f"  Type: {error_type}\n"
        f"  {_escape_text(error_detail or 'Unknown error')}\n\n"
        f"[bold white]What you can do:[/bold white]\n"
        f"  • Wait a few minutes and try again\n"
        f"  • Check your internet connection\n"
        f"  • Try again later when the service is restored\n\n"
        f"[dim]💡 The authentication service is hosted on Render.com[/dim]\n"
        f"[dim]   Free tier services may sleep after periods of inactivity.[/dim]",
        border_style="red",
        padding=(1, 2),
        width=_panel_width(70),
    ))
    console.print()
    
    _debug_log(f"API error shown to user: {error_type} - {error_detail}")


def _escape_text(value) -> str:
    """Escape rich markup in dynamic values."""
    from rich.markup import escape
    return escape(str(value))


def _panel_width(preferred: int = 70, minimum: int = 40) -> int:
    """Calculate safe panel width based on terminal size."""
    import shutil
    term_width = shutil.get_terminal_size(fallback=(preferred, 24)).columns
    return max(minimum, min(preferred, term_width - 4))


def _fetch_netlify_config(retries: int = 3, timeout: int = 15) -> Optional[str]:
    """
    Fetch Netlify client ID from the API with retry logic.
    
    ✅ FIX: Now shows clear user-facing error messages.
    
    Args:
        retries: Number of retry attempts (default: 3)
        timeout: Timeout per attempt in seconds (default: 15)
    
    Returns:
        client_id string, or None if all attempts fail
    """
    last_error = None
    console.print("[dim]🔍 Connecting to authentication service...[/dim]")
    
    for attempt in range(retries):
        try:
            if attempt > 0:
                console.print(f"[dim]⏳ Retry {attempt + 1}/{retries}...[/dim]")
                time.sleep(1.5 * attempt)
            
            response = requests.get(
                f"{API_BASE_URL}/netlify/config",
                timeout=timeout
            )
            
            # 2xx success
            if 200 <= response.status_code < 300:
                client_id = response.json().get("client_id")
                if client_id:
                    if attempt > 0:
                        console.print("[green]✅ Connected to authentication service[/green]")
                    return client_id
                last_error = "Response missing client_id"
                _debug_log(f"Netlify config response missing client_id: {response.text}")
                continue
            
            # 3xx redirect
            if 300 <= response.status_code < 400:
                last_error = f"Redirect: {response.status_code} - {response.headers.get('Location')}"
                _debug_log(last_error)
                continue
            
            # 5xx server errors - retry
            if response.status_code >= 500:
                last_error = f"Server error (HTTP {response.status_code})"
                _debug_log(f"Netlify config failed: {response.status_code} - {response.text}")
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
                _debug_log(f"Netlify config failed: {response.status_code} - {response.text}")
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
            _debug_log(f"Error fetching Netlify config: {e}")
            break
    
    # ✅ FIX: Show clear error message to user
    _debug_log(f"Failed to fetch Netlify config after {retries} attempts: {last_error}")
    _show_api_error_panel(
        error_message="Could not connect to authentication service",
        error_detail=last_error or "Unknown error"
    )
    return None


_DEPLOY_CALLBACK: Optional[Callable] = None


def set_deploy_callback(callback: Callable) -> None:
    global _DEPLOY_CALLBACK
    _DEPLOY_CALLBACK = callback


def get_deploy_callback() -> Optional[Callable]:
    return _DEPLOY_CALLBACK


def _generate_pkce_pair():
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(40)).rstrip(b"=").decode("ascii")
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    return code_verifier, code_challenge


def _build_authorize_url(state: str, code_challenge: str, client_id: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZATION_ENDPOINT}?{urllib.parse.urlencode(params)}"


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
            try:
                if result.code:
                    self.wfile.write(
                        b"<html><body><h2>Netlify authorization complete.</h2>"
                        b"<p>You can close this tab and return to the terminal.</p></body></html>"
                    )
                else:
                    self.wfile.write(
                        b"<html><body><h2>Authorization failed.</h2>"
                        b"<p>You can close this tab and return to the terminal.</p></body></html>"
                    )
            except (BrokenPipeError, ConnectionResetError):
                pass
            done_event.set()

        def log_message(self, format, *args):
            pass

    return Handler


def _wait_for_callback(timeout: int = 180) -> _CallbackResult:
    result = _CallbackResult()
    done_event = threading.Event()
    handler = _make_handler(result, done_event)

    try:
        server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), handler)
    except OSError as e:
        result.error = f"port {CALLBACK_PORT} unavailable"
        _debug_log(f"Couldn't bind local OAuth callback server on {CALLBACK_HOST}:{CALLBACK_PORT}: {e}")
        return result

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        got_it = done_event.wait(timeout=timeout)
    finally:
        server.shutdown()
        server_thread.join()
    if not got_it:
        result.error = "timed out waiting for Netlify to redirect back"
    return result


def _read_token_file() -> Dict:
    """Read token file with TTL caching to avoid redundant disk I/O."""
    global _token_cache, _cache_timestamp
    
    now = time.time()
    if _token_cache is not None and (now - _cache_timestamp) < CACHE_TTL:
        return _token_cache
    
    try:
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, "r") as f:
                _token_cache = json.load(f)
                _cache_timestamp = now
                return _token_cache
    except Exception as e:
        _debug_log(f"Failed to read token file: {e}")
    
    _token_cache = {}
    _cache_timestamp = now
    return _token_cache


def _invalidate_cache() -> None:
    """Force cache invalidation after writes."""
    global _token_cache, _cache_timestamp
    _token_cache = None
    _cache_timestamp = 0


def _write_token_file(data: Dict) -> bool:
    token_dir = TOKEN_FILE.parent
    try:
        token_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(token_dir, _DIR_MODE)
        except OSError as e:
            _debug_log(f"Failed to chmod token dir: {e}")

        tmp_path = token_dir / f".{TOKEN_FILE.name}.tmp"
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, _FILE_MODE)
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, TOKEN_FILE)
        finally:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        try:
            os.chmod(TOKEN_FILE, _FILE_MODE)
        except OSError as e:
            _debug_log(f"Failed to chmod token file: {e}")
        
        _invalidate_cache()
        return True
    except Exception as e:
        _debug_log(f"Failed to write token file: {e}")
        _show_error(
            "Couldn't save your Netlify login on this machine.",
            hint="Check that this app can write to your home folder, then try again.",
        )
        return False


def is_netlify_authenticated() -> bool:
    """Cheap local check — NO network I/O."""
    data = _read_token_file()
    
    if data.get("pat_token"):
        return True
    
    access_token = data.get("access_token")
    if not access_token:
        return False
    
    expires_at = data.get("expires_at")
    if expires_at is None:
        return True
    
    return time.time() < expires_at


def refresh_if_needed() -> Optional[str]:
    """Explicit refresh function with network I/O."""
    data = _read_token_file()
    
    if data.get("pat_token"):
        return data["pat_token"]
    
    access_token = data.get("access_token")
    if not access_token:
        return None
    
    expires_at = data.get("expires_at")
    if expires_at and time.time() >= expires_at - TOKEN_REFRESH_SKEW_SECONDS:
        return refresh_netlify_token()
    
    return access_token


def get_netlify_token() -> Optional[str]:
    """Get token with optional refresh if needed."""
    data = _read_token_file()
    pat = data.get("pat_token")
    if pat:
        return pat
    
    return refresh_if_needed()


def refresh_netlify_token() -> Optional[str]:
    data = _read_token_file()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return None

    try:
        response = requests.post(
            f"{API_BASE_URL}/netlify/refresh",
            json={"refresh_token": refresh_token},
            timeout=30,
        )
    except requests.RequestException as e:
        _debug_log(f"refresh_netlify_token network error: {e}")
        return None

    if response.status_code != 200:
        _debug_log(f"refresh_netlify_token HTTP {response.status_code}: {response.text}")
        return None

    try:
        payload = response.json()
    except ValueError as e:
        _debug_log(f"refresh_netlify_token: response wasn't valid JSON: {e}")
        return None

    new_access_token = payload.get("access_token")
    if not new_access_token:
        _debug_log(f"refresh_netlify_token: response missing access_token: {payload}")
        return None

    new_refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    
    existing_user = data.get("user", {"email": "Unknown"})

    save_netlify_token(new_access_token, existing_user, new_refresh_token, expires_in or 3600)
    _debug_log("refresh_netlify_token: access token refreshed successfully")
    return new_access_token


def get_netlify_user() -> Optional[Dict]:
    return _read_token_file().get("user")


def save_netlify_token(
    token: str,
    user_info: Dict,
    refresh_token: Optional[str] = None,
    expires_in: Optional[int] = None,
) -> None:
    data = _read_token_file()
    
    data.pop("pat_token", None)
    
    data["access_token"] = token
    data["user"] = user_info
    if refresh_token:
        data["refresh_token"] = refresh_token
    
    if expires_in is not None:
        data["expires_at"] = time.time() + expires_in
    elif "expires_at" not in data:
        data["expires_at"] = time.time() + 3600
    
    _write_token_file(data)


def save_pat_token(token: str, user_info: Optional[Dict] = None) -> None:
    data = _read_token_file()
    data["pat_token"] = token
    
    if user_info:
        data["user"] = user_info
    elif "user" not in data:
        data["user"] = {"email": "PAT User"}
    
    _write_token_file(data)


def get_pat_token() -> Optional[str]:
    return _read_token_file().get("pat_token")


def clear_pat_token() -> None:
    data = _read_token_file()
    data.pop("pat_token", None)
    _write_token_file(data)


# ──────────────────────────────────────────────────────────────
# LOGIN TO NETLIFY
# ──────────────────────────────────────────────────────────────

def login_to_netlify() -> Optional[str]:
    """
    Authenticate with Netlify using OAuth.
    
    ✅ FIX: Now shows clear user-facing error messages.
    
    Returns:
        Access token if successful, None otherwise.
    """
    client_id = _fetch_netlify_config()
    if not client_id:
        # Error already shown by _fetch_netlify_config()
        return None

    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    authorize_url = _build_authorize_url(state, code_challenge, client_id)

    console.print("[dim]🌐 Opening browser for Netlify authorization...[/dim]")
    opened = webbrowser.open(authorize_url)
    if not opened:
        console.print("[yellow]⚠️ Could not open browser automatically.[/yellow]")
        console.print(f"[dim]Please open this URL manually:[/dim]")
        console.print(f"[cyan]{authorize_url}[/cyan]")
        console.print()
    else:
        console.print("[green]✅ Browser opened. Please authorize Opun8 to access Netlify.[/green]")
        console.print("[dim]Waiting for authorization...[/dim]")
        console.print()

    result = _wait_for_callback()

    if result.error and not result.code:
        console.print(f"[red]❌ Authorization failed: {result.error}[/red]")
        return None

    if not secrets.compare_digest(result.state or "", state):
        console.print("[red]❌ Security check failed. Please try again.[/red]")
        return None

    token = _exchange_code_for_token(result.code, code_verifier)
    if not token:
        console.print("[red]❌ Failed to exchange authorization code for token.[/red]")
        console.print("[dim]The authentication service may be temporarily unavailable.[/dim]")
        return None

    console.print("[green]✅ Successfully authenticated with Netlify![/green]")
    return token


def _pat_login_flow(pat: str, max_attempts: int = 3) -> Optional[str]:
    """
    Handle PAT-based authentication with retry logic.
    
    Args:
        pat: Personal Access Token to validate
        max_attempts: Number of retry attempts (default: 3)
    
    Returns:
        Access token if valid, None otherwise.
    """
    if not pat or not pat.strip():
        _debug_log("_pat_login_flow: Empty PAT provided")
        return None
    
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            _debug_log(f"_pat_login_flow: Retry attempt {attempt}/{max_attempts}")
            time.sleep(1 * attempt)
        
        user = get_netlify_user_info(pat)
        if user:
            save_pat_token(pat, user)
            _debug_log(f"_pat_login_flow: PAT validated and saved successfully (attempt {attempt})")
            return pat
        
        _debug_log(f"_pat_login_flow: PAT validation failed on attempt {attempt}")
    
    _debug_log(f"_pat_login_flow: PAT validation failed after {max_attempts} attempts")
    return None


def _exchange_code_for_token(code: str, code_verifier: str) -> Optional[str]:
    """Exchange code for token using your API."""
    try:
        if not code:
            _debug_log("No authorization code received from Netlify.")
            return None

        response = requests.post(
            f"{API_BASE_URL}/netlify/exchange",
            json={
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": REDIRECT_URI,
            },
            timeout=30,
        )

        if response.status_code != 200:
            try:
                error_data = response.json()
                error_msg = error_data.get("detail", error_data.get("error", "Unknown error"))
            except (ValueError, json.JSONDecodeError):
                error_msg = response.text[:200] if response.text else f"HTTP {response.status_code}"
            _debug_log(f"Token exchange API error: {error_msg}")
            return None

        data = response.json()
        if "access_token" not in data:
            _debug_log(f"Token exchange response missing access_token: {data}")
            return None

        token = data["access_token"]
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")
        
        user = get_netlify_user_info(token)

        if user:
            save_netlify_token(token, user, refresh_token, expires_in)
        else:
            save_netlify_token(token, {"email": "Unknown"}, refresh_token, expires_in)
            _debug_log("Connected, but couldn't load your profile details.")

        return token

    except requests.exceptions.ConnectionError:
        _debug_log(f"Connection error to {API_BASE_URL}")
        return None
    except requests.RequestException as e:
        _debug_log(f"Token exchange network error: {e}")
        return None
    except Exception as e:
        _debug_log(f"Token exchange unexpected error: {e}")
        return None


def get_netlify_user_info(token: str, retries: int = 3, timeout: int = 15) -> Optional[Dict]:
    """
    Get Netlify user info - uses your API with retry logic.
    
    Args:
        token: Netlify access token
        retries: Number of retry attempts (default: 3)
        timeout: Timeout per attempt in seconds (default: 15)
    
    Returns:
        User info dict, or None if all attempts fail
    """
    last_error = None
    
    for attempt in range(retries):
        try:
            if attempt > 0:
                time.sleep(1.5 * attempt)
            
            response = requests.get(
                f"{API_BASE_URL}/netlify/user",
                headers={"Authorization": f"Bearer {token}"},
                timeout=timeout,
            )
            
            if response.status_code == 200:
                data = response.json()
                _debug_log(f"get_netlify_user_info: success for user {data.get('email', 'unknown')}")
                return data
            
            if response.status_code >= 500:
                last_error = f"API returned {response.status_code}"
                _debug_log(f"get_netlify_user_info HTTP {response.status_code}: {response.text}")
                continue
            
            if response.status_code >= 400:
                last_error = f"API returned {response.status_code}"
                _debug_log(f"get_netlify_user_info HTTP {response.status_code}: {response.text}")
                break
                
        except requests.exceptions.ConnectionError as e:
            last_error = str(e)
            _debug_log(f"Connection error to API: {e}")
            if attempt < retries - 1:
                console.print("[dim]⏳ API is waking up (Render free tier sleep)...[/dim]")
            continue
            
        except requests.exceptions.Timeout as e:
            last_error = str(e)
            _debug_log(f"Timeout connecting to API: {e}")
            if attempt < retries - 1:
                console.print("[dim]⏳ API taking longer than expected (waking up)...[/dim]")
            continue
            
        except Exception as e:
            last_error = str(e)
            _debug_log(f"get_netlify_user_info error: {e}")
            break
    
    _debug_log(f"Failed to fetch Netlify user after {retries} attempts: {last_error}")
    return None


def logout_netlify() -> None:
    try:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
            _invalidate_cache()
            console.print("[green]✅ Logged out of Netlify.[/green]")
        else:
            console.print("[yellow]Not logged in.[/yellow]")
    except Exception as e:
        _show_error(
            "Couldn't log you out on this machine.",
            hint="Please try again.",
            debug_detail=f"Failed to remove token file: {e}",
        )


SITES_ENDPOINT = "https://api.netlify.com/api/v1/sites"


def list_netlify_sites(token: str) -> Optional[List[Dict]]:
    """List all Netlify sites with pagination."""
    all_sites = []
    page = 1
    per_page = 100
    
    try:
        while True:
            response = requests.get(
                SITES_ENDPOINT,
                headers={"Authorization": f"Bearer {token}"},
                params={"limit": per_page, "page": page},
                timeout=15,
            )
            
            if response.status_code == 401:
                _show_error(
                    "Your saved Netlify login has expired.",
                    hint="Run `opun8 netlify` to reconnect.",
                )
                return None
            if response.status_code != 200:
                _show_error(
                    "We couldn't load your Netlify sites.",
                    hint="Please try again in a moment.",
                    debug_detail=f"list_netlify_sites HTTP {response.status_code}: {response.text}",
                )
                return None
            
            data = response.json()
            if not data:
                break
            
            all_sites.extend(data)
            
            if len(data) < per_page:
                break
            
            page += 1
            
        return all_sites
        
    except requests.RequestException as e:
        _show_error(
            "We couldn't reach Netlify to load your sites.",
            hint="Check your internet connection and try again.",
            debug_detail=f"list_netlify_sites network error: {e}",
        )
        return None
    except Exception as e:
        _show_error(
            "Something went wrong loading your Netlify sites.",
            debug_detail=f"list_netlify_sites unexpected error: {e}",
        )
        return None


def show_netlify_sites(deploy_callback=None) -> None:
    token = get_netlify_token()
    if not token:
        console.print("[yellow]Not connected to Netlify yet. Run the login flow first.[/yellow]")
        return
    if deploy_callback is None:
        deploy_callback = get_deploy_callback()
    user = get_netlify_user()
    console.print()
    if user:
        console.print(f"[dim]Connected as {user.get('full_name', user.get('email', 'Unknown'))}[/dim]")
    sites = list_netlify_sites(token)
    if sites is None:
        return
    if len(sites) == 0:
        console.print()
        console.print(Panel(
            "[bold]No site yet[/bold]\n\n[dim]You haven't deployed anything to Netlify through Opun8 yet.[/dim]",
            border_style="cyan", padding=(1, 2), width=60,
        ))
        console.print()
        choice = Prompt.ask("[bold cyan]➜[/] Deploy your first site now?", choices=["y", "n"], default="y", show_choices=False)
        if choice.lower() == "y":
            if deploy_callback:
                deploy_callback()
            else:
                console.print("[yellow]No deploy command wired up yet — run your deploy command directly.[/yellow]")
        return
    table = Table(title=f"📦 Netlify Sites ({len(sites)})", border_style="cyan")
    table.add_column("Name", style="bold white")
    table.add_column("URL", style="cyan")
    table.add_column("Created", style="dim")
    for site in sites:
        name = site.get("name", "—")
        url = site.get("url", "—")
        created_at = site.get("created_at", "—")
        if created_at:
            try:
                created_at = datetime.datetime.fromisoformat(created_at.replace("Z", "+00:00")).strftime("%Y-%m-%d")
            except Exception:
                pass
        table.add_row(name, url, created_at)
    console.print()
    console.print(table)
    console.print()


# ------------------------------------------------------------------------------
# CLI COMMAND
# ------------------------------------------------------------------------------

def netlify_auth_command() -> None:
    """CLI command for Netlify authentication."""
    if is_netlify_authenticated():
        user = get_netlify_user()
        if user:
            console.print(f"[green]✅ Already authenticated as: {user.get('full_name', user.get('email', 'Unknown'))}[/green]")
        else:
            console.print("[green]✅ Already authenticated with Netlify.[/green]")
        return
    
    login_to_netlify()


# ------------------------------------------------------------------------------
# EXPORTS
# ------------------------------------------------------------------------------

__all__ = [
    "login_to_netlify",
    "is_netlify_authenticated",
    "get_netlify_token",
    "logout_netlify",
    "netlify_auth_command",
    "get_netlify_user",
    "get_netlify_user_info",
    "show_netlify_sites",
    "list_netlify_sites",
    "save_netlify_token",
    "refresh_netlify_token",
    "set_deploy_callback",
    "save_pat_token",
    "get_pat_token",
    "clear_pat_token",
    "refresh_if_needed",
]