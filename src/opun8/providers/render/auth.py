"""
Render OAuth authentication for Opun8.

Handles:
    - Personal API key authentication (primary method)
    - Token storage and refresh
    - User info retrieval
    - Team/workspace management

Render API endpoints are at https://api.render.com/v1/ (NOT render.com/api/v1 —
that host does not serve the API and will make every request fail auth).
"""

import base64
import hashlib
import os
import stat
import time
import webbrowser
import json
import threading
import secrets
import urllib.parse
import datetime
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple

import requests
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from opun8.providers.render.models import User, OAuthTokenResponse

console = Console()

# ------------------------------------------------------------------------------
# API Configuration
# ------------------------------------------------------------------------------

# Render API endpoints - CORRECTED (the real host is api.render.com, not render.com)
RENDER_API_BASE = "https://api.render.com/v1"
RENDER_OWNERS_ENDPOINT = f"{RENDER_API_BASE}/owners"

# OAuth Configuration (kept for reference, but API key is the primary method)
RENDER_OAUTH_AUTHORIZE = "https://render.com/oauth/authorize"
RENDER_OAUTH_TOKEN = "https://api.render.com/v1/oauth/token"

# OAuth Configuration
CALLBACK_HOST = "localhost"
CALLBACK_PORT = int(os.environ.get("OPUN8_OAUTH_CALLBACK_PORT", "8080"))
CALLBACK_PATH = "/render/callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"

# Scopes requested
SCOPES = "read write"

# Token refresh skew (refresh 2 minutes before expiry)
TOKEN_REFRESH_SKEW_SECONDS = 120

# Token storage
TOKEN_FILE = Path.home() / ".opun8" / "render_token.json"
DEBUG_LOG_FILE = Path.home() / ".opun8" / "debug.log"

# File permissions
_DIR_MODE = stat.S_IRWXU
_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR


# ──────────────────────────────────────────────────────────────
# DEBUG LOGGING
# ──────────────────────────────────────────────────────────────

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


# ──────────────────────────────────────────────────────────────
# HTTP HELPERS
# ──────────────────────────────────────────────────────────────

def _safe_json(response: requests.Response, context: str = "") -> Optional[Any]:
    """Parse a response body as JSON, tolerating non-JSON bodies."""
    try:
        return response.json()
    except ValueError as e:
        _debug_log(f"Response from {context or response.url} wasn't valid JSON: {e}")
        return None


def _api_get(url: str, token: str, timeout: int = 10) -> Optional[Any]:
    """
    GET an authenticated Render API endpoint.
    Returns parsed JSON, or None on failure.
    """
    try:
        response = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
    except requests.RequestException as e:
        _debug_log(f"GET {url} network error: {e}")
        return None

    # Accept any 2xx status code (200, 201, 202, 204, etc.)
    if response.status_code < 200 or response.status_code >= 300:
        _debug_log(f"GET {url} HTTP {response.status_code}: {response.text[:500]}")
        return None

    return _safe_json(response, context=url)


def _api_post(url: str, token: str, data: Dict[str, Any], timeout: int = 30) -> Optional[Any]:
    """POST to an authenticated Render API endpoint. Returns parsed JSON, or None on failure."""
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=data,
            timeout=timeout,
        )
    except requests.RequestException as e:
        _debug_log(f"POST {url} network error: {e}")
        return None

    if response.status_code < 200 or response.status_code >= 300:
        _debug_log(f"POST {url} HTTP {response.status_code}: {response.text[:500]}")
        return None

    return _safe_json(response, context=url)


def _normalize_list_items(raw: Any, resource_key: str) -> List[Dict[str, Any]]:
    """
    Normalize a Render list-endpoint response into a flat list of resource dicts.
    Tolerates both wrapped (cursor-paginated) and flat array responses, and the
    common Render pattern of `[{"owner": {...}, "cursor": "..."}]`.
    """
    if isinstance(raw, dict):
        raw = raw.get(f"{resource_key}s") or raw.get("items") or []
    if not isinstance(raw, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        wrapped = item.get(resource_key)
        normalized.append(wrapped if isinstance(wrapped, dict) else item)
    return normalized


# ──────────────────────────────────────────────────────────────
# TOKEN STORAGE
# ──────────────────────────────────────────────────────────────

def _read_token_file() -> Dict[str, Any]:
    """Read the token file, returning empty dict if it doesn't exist."""
    try:
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        _debug_log(f"Failed to read token file: {e}")
    return {}


def _write_token_file(data: Dict[str, Any]) -> bool:
    """Write token data to file with secure permissions."""
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
        return True
    except Exception as e:
        _debug_log(f"Failed to write token file: {e}")
        _show_error(
            "Couldn't save your Render login on this machine.",
            hint="Check that this app can write to your home folder, then try again.",
        )
        return False


def get_render_token() -> Optional[str]:
    """
    Return a usable Render access token, refreshing if needed.
    Falls back to API key if OAuth token is not available.
    """
    data = _read_token_file()

    # Check for API key first (user-provided)
    api_key = data.get("api_key")
    if api_key:
        return api_key

    # Check for OAuth token
    access_token = data.get("access_token")
    if not access_token:
        return None

    # Check if token needs refreshing
    expires_at = data.get("expires_at")
    if expires_at is not None:
        now = time.time()
        if now >= expires_at - TOKEN_REFRESH_SKEW_SECONDS:
            refreshed = refresh_render_token()
            if refreshed:
                return refreshed
            if now >= expires_at:
                return None

    return access_token


def get_render_user() -> Optional[Dict[str, Any]]:
    """Get the user info from the token file."""
    return _read_token_file().get("user")


def get_render_owner_id() -> Optional[str]:
    """Get the owner/workspace ID from the token file."""
    data = _read_token_file()
    return data.get("owner_id")


def save_render_token(
    access_token: str,
    refresh_token: Optional[str] = None,
    expires_in: Optional[int] = None,
    user_info: Optional[Dict[str, Any]] = None,
    owner_id: Optional[str] = None,
) -> None:
    """Persist an OAuth access token."""
    data = _read_token_file()
    data["access_token"] = access_token
    if refresh_token:
        data["refresh_token"] = refresh_token
    if expires_in is not None:
        data["expires_at"] = time.time() + expires_in
    if user_info:
        data["user"] = user_info
    if owner_id:
        data["owner_id"] = owner_id
    _write_token_file(data)


def save_api_key(api_key: str) -> None:
    """Save a Render API key (Personal Access Token)."""
    data = _read_token_file()
    data["api_key"] = api_key
    # Clear any OAuth tokens to avoid confusion
    data.pop("access_token", None)
    data.pop("refresh_token", None)
    data.pop("expires_at", None)
    _write_token_file(data)


def clear_api_key() -> None:
    """Remove a saved API key from storage."""
    data = _read_token_file()
    data.pop("api_key", None)
    _write_token_file(data)


def refresh_render_token() -> Optional[str]:
    """Exchange the saved refresh token for a new access token."""
    data = _read_token_file()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return None

    client_id = os.environ.get("RENDER_CLIENT_ID")
    client_secret = os.environ.get("RENDER_CLIENT_SECRET")
    if not client_id or not client_secret:
        _debug_log("refresh_render_token: missing client credentials")
        return None

    try:
        response = requests.post(
            RENDER_OAUTH_TOKEN,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
    except requests.RequestException as e:
        _debug_log(f"refresh_render_token network error: {e}")
        return None

    if response.status_code != 200:
        body = _safe_json(response, context="refresh_render_token") or {}
        _debug_log(f"refresh_render_token HTTP {response.status_code}: {body or response.text[:500]}")
        if body.get("error") == "invalid_grant":
            data.pop("access_token", None)
            data.pop("refresh_token", None)
            data.pop("expires_at", None)
            _write_token_file(data)
        return None

    payload = _safe_json(response, context="refresh_render_token")
    if payload is None:
        return None

    try:
        parsed = OAuthTokenResponse.model_validate(payload)
        new_access_token = parsed.access_token
        new_refresh_token = parsed.refresh_token
        expires_in = parsed.expires_in
    except ValidationError as e:
        _debug_log(f"refresh_render_token: response didn't match expected shape: {e}")
        new_access_token = payload.get("access_token")
        new_refresh_token = payload.get("refresh_token")
        expires_in = payload.get("expires_in")

    if not new_access_token:
        _debug_log(f"refresh_render_token: response missing access_token: {payload}")
        return None

    save_render_token(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_in=expires_in,
        user_info=data.get("user"),
        owner_id=data.get("owner_id"),
    )

    _debug_log("refresh_render_token: access token refreshed successfully")
    return new_access_token


# ──────────────────────────────────────────────────────────────
# SHARED USER/OWNER FETCHING
# ──────────────────────────────────────────────────────────────

def _fetch_user_info(token: str) -> Optional[Dict[str, Any]]:
    """
    Fetch and normalize user info for either an OAuth access token or API key.

    Render's public API does not expose a dedicated "who am I" /user endpoint.
    The documented way to identify the authenticated principal is the
    /owners (workspaces) list — the personal workspace comes back with
    type "user" and carries the name/email. This also doubles as our
    "is this key valid at all" check.
    """
    owners = list_render_owners(token)
    if not owners:
        return None

    # Prefer the personal ("user"-type) owner if present, else just take the first.
    personal = next((o for o in owners if o.get("type") == "user"), owners[0])

    try:
        user = User.model_validate(personal)
        return user.model_dump(mode="json", by_alias=False, include={"id", "name", "email", "username"})
    except ValidationError as e:
        _debug_log(f"Owner response didn't match expected User shape, using raw fields: {e}")
        return {
            "id": personal.get("id"),
            "name": personal.get("name"),
            "email": personal.get("email"),
            "username": personal.get("username"),
        }


def _fetch_default_owner_id(token: str) -> Optional[str]:
    """Get the default owner/workspace ID (usually the personal workspace)."""
    owners = list_render_owners(token)
    if not owners:
        return None
    return owners[0].get("id") if owners else None


def _verify_and_fetch_user(token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Shared implementation for verifying a token and fetching user/owner."""
    user_info = _fetch_user_info(token)
    if not user_info or not user_info.get("id"):
        return None, None
    return user_info, _fetch_default_owner_id(token)


# ──────────────────────────────────────────────────────────────
# OAUTH FLOW (API Key is the primary method - OAuth is experimental)
# ──────────────────────────────────────────────────────────────

@dataclass
class _CallbackResult:
    """Result of the OAuth callback."""
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


def _make_handler(result: _CallbackResult, done_event: threading.Event):
    """Create a callback handler for the local HTTP server."""
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
                    b"<html><body><h2>Render authorization complete.</h2>"
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
    """Start a local server, wait for the OAuth redirect."""
    result = _CallbackResult()
    done_event = threading.Event()
    handler = _make_handler(result, done_event)

    try:
        server = HTTPServer((CALLBACK_HOST, CALLBACK_PORT), handler)
    except OSError as e:
        result.error = f"port {CALLBACK_PORT} unavailable"
        _debug_log(
            f"Couldn't bind local OAuth callback server on {CALLBACK_HOST}:{CALLBACK_PORT}: {e}. "
            f"Set OPUN8_OAUTH_CALLBACK_PORT to use a different port."
        )
        return result

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        got_it = done_event.wait(timeout=timeout)
    finally:
        server.shutdown()
        server_thread.join()

    if not got_it:
        result.error = "timed out waiting for Render to redirect back"

    return result


def _get_render_client_id() -> Optional[str]:
    """Get Render client ID from environment."""
    client_id = os.environ.get("RENDER_CLIENT_ID")
    if not client_id:
        _debug_log("RENDER_CLIENT_ID not set in environment")
        return None
    return client_id


def _generate_pkce_pair() -> Tuple[str, str]:
    """Generate an RFC 7636 PKCE code_verifier/code_challenge (S256) pair."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _build_authorize_url(state: str, client_id: str, code_challenge: str) -> str:
    """Build the Render OAuth authorization URL."""
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{RENDER_OAUTH_AUTHORIZE}?{urllib.parse.urlencode(params)}"


def login_to_render() -> Optional[str]:
    """
    Authenticate with Render.

    Returns:
        Access token on success, None on failure.
    """
    console.print()
    console.print(Panel(
        "[bold cyan]☁️ Render Authentication[/bold cyan]\n\n"
        "Opun8 needs access to Render to:\n"
        "  • Create services\n"
        "  • Deploy your code\n"
        "  • Get deployment URLs\n\n"
        "[bold]Recommended:[/bold] Use API Key (option 3) — quick and reliable.\n"
        "[dim]OAuth (option 1) is experimental and may not work.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()
    console.print("[bold]1[/] 🔑  [white]Login with Render (OAuth)[/white]  [dim](experimental)[/dim]")
    console.print("[bold]2[/] ⏭️  [white]Skip[/white]  [dim](deploy without Render)[/dim]")
    console.print()
    console.print("[bold]3[/] 🔑  [white]Use API Key[/white]  [dim](recommended)[/dim]")
    console.print()

    choice = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=["1", "2", "3"],
        default="3",
        show_choices=False,
    )

    if choice == "2":
        console.print("\n[yellow]Skipping Render authentication.[/yellow]")
        return None

    if choice == "3":
        return _api_key_login()

    # OAuth login flow (experimental)
    client_id = _get_render_client_id()
    if not client_id:
        _show_error(
            "Render OAuth isn't available right now.",
            hint="Please use API Key (option 3) instead.",
            debug_detail="Render OAuth misconfigured: missing RENDER_CLIENT_ID in environment",
        )
        return None

    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = _generate_pkce_pair()
    authorize_url = _build_authorize_url(state, client_id, code_challenge)

    console.print()
    console.print("[dim]🌐 Opening browser for Render authorization...[/dim]")
    webbrowser.open(authorize_url)
    console.print("[bold]Waiting for Render to redirect back...[/bold]")
    console.print()

    result = _wait_for_callback()

    if result.error and not result.code:
        _show_error(
            "We couldn't complete the Render login.",
            hint="Please use API Key (option 3) instead.",
            debug_detail=f"OAuth callback error: {result.error}",
        )
        return None

    if result.state != state:
        _show_error(
            "Something looked wrong with the login response, so we stopped here for your safety.",
            hint="Please use API Key (option 3) instead.",
            debug_detail="OAuth state mismatch on callback — possible CSRF, aborting login.",
        )
        return None

    token = _exchange_code_for_token(result.code, code_verifier)
    if not token:
        _show_error(
            "We couldn't finish connecting your Render account.",
            hint="Please use API Key (option 3) instead.",
        )
        return None

    return token


def _api_key_login() -> Optional[str]:
    """Authenticate with Render using a Personal API Key."""
    console.print()
    console.print(Panel(
        "[bold cyan]🔑 Render API Key[/bold cyan]\n\n"
        "To get your Render API key:\n"
        "1. Go to [dim]https://dashboard.render.com/settings/keys[/dim]\n"
        "2. Click [bold]Create API Key[/bold]\n"
        "3. Give it a name (e.g., [dim]opun8-cli[/dim])\n"
        "4. Click [bold]Create API Key[/bold]\n"
        "5. [bold]Copy the key[/bold] immediately (it's only shown once)\n\n"
        "[dim]Your browser will open to the API keys page.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()

    webbrowser.open("https://dashboard.render.com/settings/keys")

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        console.print()
        console.print(f"[dim]Attempt {attempt} of {max_attempts}[/dim]")
        api_key = Prompt.ask(
            "[bold cyan]➜[/] Paste your Render API key"
        ).strip()

        if not api_key:
            console.print("[yellow]No API key provided.[/yellow]")
            break

        console.print("[dim]Verifying API key...[/dim]")

        # Debug logging (never logs the full key)
        _debug_log(f"API key provided (first 10 chars): {api_key[:10]}... (length: {len(api_key)})")

        user_info, owner_id = _verify_and_fetch_user(api_key)

        if user_info:
            save_api_key(api_key)
            console.print()
            console.print(f"[bold green]✅ Connected to Render as: {user_info.get('name', 'Unknown')}[/bold green]")
            console.print("[dim]API key saved securely for future use.[/dim]")
            return api_key

        console.print(f"[red]❌ Invalid API key or insufficient permissions. (attempt {attempt} of {max_attempts})[/red]")
        if attempt < max_attempts:
            retry = Prompt.ask(
                "[bold cyan]➜[/] Try again?", choices=["y", "n"], default="y", show_choices=False
            )
            if retry.lower() != "y":
                break

    console.print()
    console.print("[yellow]Skipping Render authentication.[/yellow]")
    return None


def _exchange_code_for_token(code: str, code_verifier: Optional[str] = None) -> Optional[str]:
    """Exchange an authorization code for an access token."""
    client_id = os.environ.get("RENDER_CLIENT_ID")
    client_secret = os.environ.get("RENDER_CLIENT_SECRET")

    if not client_id or not client_secret:
        _show_error(
            "Render OAuth isn't configured properly.",
            hint="Please use API Key (option 3) instead.",
            debug_detail="Missing RENDER_CLIENT_ID or RENDER_CLIENT_SECRET",
        )
        return None

    body = {
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    if code_verifier:
        body["code_verifier"] = code_verifier

    try:
        response = requests.post(
            RENDER_OAUTH_TOKEN,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
    except requests.RequestException as e:
        _show_error(
            "We couldn't reach Render to finish logging in.",
            hint="Please use API Key (option 3) instead.",
            debug_detail=f"Token exchange network error: {e}",
        )
        return None

    if response.status_code != 200:
        error_body = _safe_json(response, context="_exchange_code_for_token") or {}
        error_msg = error_body.get("error_description", response.text[:500])
        _show_error(
            "Render rejected the login request.",
            hint="Please use API Key (option 3) instead.",
            debug_detail=f"Token exchange HTTP {response.status_code}: {error_msg}",
        )
        return None

    payload = _safe_json(response, context="_exchange_code_for_token")
    if payload is None:
        _show_error(
            "We couldn't finish connecting your Render account.",
            hint="Please use API Key (option 3) instead.",
            debug_detail="Token exchange response wasn't valid JSON",
        )
        return None

    try:
        parsed = OAuthTokenResponse.model_validate(payload)
        access_token = parsed.access_token
        refresh_token = parsed.refresh_token
        expires_in = parsed.expires_in
    except ValidationError as e:
        _debug_log(f"Token response didn't match expected shape, using raw fields: {e}")
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        expires_in = payload.get("expires_in")

    if not access_token:
        _show_error(
            "We couldn't finish connecting your Render account.",
            hint="Please use API Key (option 3) instead.",
            debug_detail=f"Token exchange response missing access_token: {payload}",
        )
        return None

    user_info, owner_id = _verify_and_fetch_user(access_token)

    if user_info:
        save_render_token(access_token, refresh_token, expires_in, user_info, owner_id)
        console.print()
        console.print(f"[bold green]✅ Connected to Render as: {user_info.get('name', 'Unknown')}[/bold green]")
        console.print("[dim]Token saved securely for future use.[/dim]")
    else:
        save_render_token(access_token, refresh_token, expires_in, {"name": "Unknown"}, owner_id)
        console.print("[yellow]Connected, but couldn't load your profile details.[/yellow]")

    return access_token


# ──────────────────────────────────────────────────────────────
# PUBLIC FUNCTIONS
# ──────────────────────────────────────────────────────────────

def is_render_authenticated() -> bool:
    """Check if the user is authenticated with Render."""
    return get_render_token() is not None


def logout_render() -> None:
    """Logout from Render."""
    try:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
            console.print("[green]✅ Logged out of Render.[/green]")
        else:
            console.print("[yellow]Not logged in.[/yellow]")
    except Exception as e:
        _show_error(
            "Couldn't log you out on this machine.",
            hint="Please try again.",
            debug_detail=f"Failed to remove token file: {e}",
        )


def switch_render_owner(owner_id: str) -> None:
    """Switch the default owner/workspace for deployments."""
    data = _read_token_file()
    data["owner_id"] = owner_id
    _write_token_file(data)
    console.print(f"[green]✅ Switched to owner: {owner_id}[/green]")


def list_render_owners(token: str) -> Optional[List[Dict[str, Any]]]:
    """
    List all owners/workspaces for the user.

    Args:
        token: The access token

    Returns:
        List of owner dicts (each with at least "id" and usually "name"),
        or None on failure.
    """
    raw = _api_get(RENDER_OWNERS_ENDPOINT, token, timeout=15)
    if raw is None:
        return None
    return _normalize_list_items(raw, "owner")


def prompt_owner_selection(token: str) -> Optional[str]:
    """Prompt the user to select an owner/workspace."""
    owners = list_render_owners(token)

    if not owners:
        console.print("[yellow]No workspaces found. Using personal account.[/yellow]")
        return None

    if len(owners) == 1:
        owner_id = owners[0].get("id")
        owner_name = owners[0].get("name", "Personal Account")
        console.print(f"[green]✅ Using workspace: {owner_name}[/green]")
        return owner_id

    console.print()
    console.print("[bold]Which workspace should Opun8 deploy to?[/bold]")
    console.print()

    for i, owner in enumerate(owners, 1):
        name = owner.get("name", "Unnamed Workspace")
        console.print(f"  [bold cyan]{i}[/] 👤  [white]{name}[/white]")

    console.print()
    console.print("  [bold cyan]0[/] 🔙  [white]Cancel[/white]")
    console.print()

    choice = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=[str(i) for i in range(0, len(owners) + 1)],
        default="0",
        show_choices=False,
    )

    if choice == "0":
        return None

    try:
        idx = int(choice) - 1
        if 0 <= idx < len(owners):
            return owners[idx].get("id")
    except ValueError:
        pass

    console.print("[red]Invalid selection.[/red]")
    return None


def show_render_auth_status() -> None:
    """Show the current Render authentication status."""
    token = get_render_token()
    if not token:
        console.print("[yellow]Not connected to Render.[/yellow]")
        console.print("[dim]Run [cyan]opun8 render[/cyan] to connect.[/dim]")
        return

    data = _read_token_file()
    user = data.get("user")
    owner_id = data.get("owner_id")

    console.print("[green]✅ Connected to Render.[/green]")
    if user:
        console.print(f"[dim]User: {user.get('name', 'Unknown')}[/dim]")
    if owner_id:
        console.print(f"[dim]Workspace: {owner_id}[/dim]")
    else:
        console.print("[dim]Workspace: Personal Account[/dim]")