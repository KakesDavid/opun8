"""
Vercel OAuth authentication for Opun8.

Error handling philosophy used throughout this file:
  - Anything the END USER of Opun8 sees on screen is short, plain-English,
    and either self-resolving ("try again") or points at something they can
    actually do. It never contains raw HTTP bodies, stack traces, or env
    var names — those aren't things a user of the CLI can fix.
  - Anything TECHNICAL (HTTP status/response bodies, exception text,
    missing configuration) is written to a local debug log instead
    (~/.opun8/debug.log) via _debug_log(), so the person operating/building
    Opun8 can diagnose it without it ever being shown as a scary error to
    an end user. Set OPUN8_DEBUG=1 to also echo these to the terminal live.
  - No code path here should be able to crash the process. Every network
    call and every bit of file I/O is wrapped so failures degrade to a
    friendly message instead of a traceback.
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
from typing import Optional, Dict, Callable
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from dotenv import load_dotenv

load_dotenv()

console = Console()

# ------------------------------------------------------------------------------
# OAuth Configuration — READ FROM .env ONLY — NO HARDCODED VALUES
# ------------------------------------------------------------------------------

CLIENT_ID = os.environ.get("VERCEL_CLIENT_ID")
# No VERCEL_CLIENT_SECRET: this app is registered with Vercel as a
# public client using PKCE. Public clients authenticate the token
# exchange with a code_verifier, not a client secret — sending one
# (even a real, valid one) makes Vercel reject the request with
# "invalid_client: Unsupported client authentication method", because
# it looks like an attempt to authenticate as a confidential client.

CALLBACK_HOST = "localhost"
CALLBACK_PORT = 8080
CALLBACK_PATH = "/vercel/callback"
REDIRECT_URI = f"http://{CALLBACK_HOST}:{CALLBACK_PORT}{CALLBACK_PATH}"

AUTHORIZATION_ENDPOINT = "https://vercel.com/oauth/authorize"
TOKEN_ENDPOINT = "https://api.vercel.com/login/oauth/token"
USERINFO_ENDPOINT = "https://api.vercel.com/login/oauth/userinfo"

SCOPES = "openid email profile offline_access"

# How long before an access token's real expiry we proactively refresh it.
# Vercel access tokens last exactly 1 hour; refreshing a couple of minutes
# early avoids racing a live request against the token dying mid-flight.
TOKEN_REFRESH_SKEW_SECONDS = 120

TOKEN_FILE = Path.home() / ".opun8" / "vercel_token.json"
DEBUG_LOG_FILE = Path.home() / ".opun8" / "debug.log"

_DIR_MODE = stat.S_IRWXU
_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR

# NOTE: CLIENT_ID is intentionally NOT validated here at
# import time. This module gets imported by every Opun8 command, including
# ones that never touch Vercel login at all (e.g. reusing an already-saved
# token) — printing a warning on every single command regardless of what
# the user is doing is exactly the kind of noisy, irrelevant error this
# file is trying to avoid. The check happens once, right where it matters:
# inside login_to_vercel(), the moment someone actually starts a fresh login.


# ------------------------------------------------------------------------------
# DEBUG LOGGING — technical detail for the developer, never for the end user
# ------------------------------------------------------------------------------

def _debug_log(message: str) -> None:
    """
    Record technical detail (raw HTTP bodies, exception text, missing
    config, etc.) for later troubleshooting. Never shown in normal command
    output. Best-effort only — logging must never be able to crash a
    command in its own right.
    """
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
    """
    The single place that prints an error to the terminal UI. Keeps what
    the user sees short, plain-English, and actionable; routes anything
    technical to the debug log instead of the screen.
    """
    console.print(f"[red]❌ {message}[/red]")
    if hint:
        console.print(f"[dim]{hint}[/dim]")
    if debug_detail:
        _debug_log(debug_detail)


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


def _decode_jwt_payload(token: str) -> Optional[Dict]:
    """
    Decode (NOT cryptographically verify) the payload segment of a JWT.
    Used only to read the 'nonce' claim off the id_token as a
    defense-in-depth replay check.

    This is deliberately not full signature verification — doing that
    properly means fetching and caching Vercel's JWKS and pulling in a JWT
    library, which is a meaningfully bigger dependency and surface area.
    We trust the id_token's origin because it comes back directly from
    Vercel's token endpoint over the same authenticated HTTPS backchannel
    request that just exchanged our authorization code — not because we've
    verified its signature. The nonce check below still catches replay of
    a stale/mismatched id_token, which is the main thing nonce is for.
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(payload_bytes)
    except Exception:
        return None


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
                        b"<html><body><h2>Vercel authorization complete.</h2>"
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
        _debug_log(
            f"Couldn't bind local OAuth callback server on "
            f"{CALLBACK_HOST}:{CALLBACK_PORT}: {e}"
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
        result.error = "timed out waiting for Vercel to redirect back"
    return result


def _read_token_file() -> Dict:
    try:
        if TOKEN_FILE.exists():
            with open(TOKEN_FILE, "r") as f:
                return json.load(f)
    except Exception as e:
        _debug_log(f"Failed to read token file: {e}")
    return {}


def _write_token_file(data: Dict) -> bool:
    """
    Persist the token file. Crash-proof by design: if this fails for any
    reason (disk full, permissions, locked file, etc.) the detail goes to
    the debug log and the caller gets a friendly message instead of the
    whole command dying.
    """
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
            "Couldn't save your Vercel login on this machine.",
            hint="Check that this app can write to your home folder, then try again.",
        )
        return False


def get_vercel_token() -> Optional[str]:
    """
    Return a usable Vercel access token, transparently refreshing it first
    if needed.

    - A saved PAT always wins and is returned as-is (PATs are long-lived
      and managed manually on vercel.com/account/tokens — they aren't
      part of this expiry/refresh cycle).
    - An OAuth access token is checked against its stored `expires_at`.
      Vercel access tokens are only valid for 1 hour, so without this a
      user would have to re-run the login flow every hour. If it's
      expired or about to expire, this automatically exchanges the saved
      refresh token for a new access/refresh token pair before returning
      — callers never need to know this happened.
    - Token files saved before this existed won't have `expires_at` yet;
      those are returned as-is (same as before) until the next login
      populates it, after which refreshing is automatic from then on.
    """
    data = _read_token_file()

    pat = data.get("pat_token")
    if pat:
        return pat

    access_token = data.get("access_token")
    if not access_token:
        return None

    expires_at = data.get("expires_at")
    if expires_at is not None:
        now = time.time()
        if now >= expires_at - TOKEN_REFRESH_SKEW_SECONDS:
            refreshed = refresh_vercel_token()
            if refreshed:
                return refreshed
            if now >= expires_at:
                # Definitely expired (not just "about to") and refreshing
                # didn't work — most likely the 30-day-old refresh token
                # itself is gone too. Return None so callers show a clear
                # "reconnect to Vercel" message instead of trying this
                # access token and getting a confusing failure from
                # whatever Vercel API they actually wanted to call.
                return None
            # Still technically valid for a few more seconds and the
            # refresh attempt just failed early (e.g. a transient network
            # blip) — use it rather than forcing a reconnect for nothing.

    return access_token


def refresh_vercel_token() -> Optional[str]:
    """
    Exchange the saved refresh token for a new access/refresh token pair.

    Per Vercel's OAuth docs, Refresh Tokens are single-use and rotate on
    every exchange — the token used here is invalidated the moment this
    call succeeds, so the new refresh token from the response is always
    saved too. Reusing an old refresh token after this runs would just
    fail on the next attempt.

    Returns the new access token on success. Returns None if there's no
    refresh token on file, the app isn't configured (no CLIENT_ID), or
    the refresh itself fails (offline, or the refresh token has expired/
    been revoked — e.g. after Vercel's 30-day refresh token lifetime).
    In every None case, the caller should fall back to a fresh
    interactive login rather than retrying with a token we know is dead.
    """
    if not CLIENT_ID:
        return None

    data = _read_token_file()
    refresh_token = data.get("refresh_token")
    if not refresh_token:
        return None

    try:
        response = requests.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "refresh_token",
                "client_id": CLIENT_ID,
                # No client_secret — same public/PKCE client used for the
                # authorization_code exchange (see the note next to
                # CLIENT_ID above).
                "refresh_token": refresh_token,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=30,
        )
    except requests.RequestException as e:
        _debug_log(f"refresh_vercel_token network error: {e}")
        return None

    if response.status_code != 200:
        _debug_log(f"refresh_vercel_token HTTP {response.status_code}: {response.text}")
        return None

    try:
        payload = response.json()
    except ValueError as e:
        _debug_log(f"refresh_vercel_token: response wasn't valid JSON: {e}")
        return None

    new_access_token = payload.get("access_token")
    if not new_access_token:
        _debug_log(f"refresh_vercel_token: response missing access_token: {payload}")
        return None

    new_refresh_token = payload.get("refresh_token")
    expires_in = payload.get("expires_in")
    existing_user = data.get("user", {"name": "Unknown"})

    save_vercel_token(new_access_token, existing_user, new_refresh_token, expires_in)
    _debug_log("refresh_vercel_token: access token refreshed successfully")
    return new_access_token


def get_vercel_user() -> Optional[Dict]:
    return _read_token_file().get("user")


def save_vercel_token(
    token: str,
    user_info: Dict,
    refresh_token: Optional[str] = None,
    expires_in: Optional[int] = None,
) -> None:
    """
    Persist an OAuth access token.

    `expires_in` (seconds, straight from Vercel's token endpoint response)
    is converted to an absolute `expires_at` timestamp so get_vercel_token()
    can tell later whether the token needs refreshing without having to
    know when it was originally saved.

    `refresh_token` only overwrites the stored value when a new one is
    actually provided. Vercel rotates refresh tokens on every use, but if
    a caller ever saves an access token without one, we don't want to
    silently wipe out the last good refresh token.
    """
    data = _read_token_file()
    data["access_token"] = token
    data["user"] = user_info
    if refresh_token:
        data["refresh_token"] = refresh_token
    if expires_in is not None:
        data["expires_at"] = time.time() + expires_in
    _write_token_file(data)


def get_vercel_scope() -> Dict:
    """
    Returns the current scope.
    For personal accounts, team_id is always None.
    """
    data = _read_token_file()
    scope = data.get("scope", {})

    # Ensure personal account always has team_id: None
    if scope.get("team_name") == "Personal Account" or not scope.get("team_id"):
        return {"team_id": None, "team_name": "Personal Account"}

    return scope


def save_vercel_scope(team_id: Optional[str], team_name: str) -> None:
    data = _read_token_file()
    data["scope"] = {"team_id": team_id, "team_name": team_name}
    _write_token_file(data)


def save_pat_token(token: str) -> None:
    data = _read_token_file()
    data["pat_token"] = token
    _write_token_file(data)


def get_pat_token() -> Optional[str]:
    return _read_token_file().get("pat_token")


def clear_pat_token() -> None:
    """Remove a saved PAT so get_vercel_token() falls back to the OAuth token."""
    data = _read_token_file()
    if "pat_token" in data:
        del data["pat_token"]
        _write_token_file(data)


def login_to_vercel() -> Optional[str]:
    console.print()
    console.print(Panel(
        "[bold cyan]▲ Vercel Authentication[/bold cyan]\n\n"
        "Opun8 needs access to Vercel to:\n"
        "  • Create projects\n"
        "  • Deploy your code\n"
        "  • Get deployment URLs\n\n"
        "[dim]Your browser will open for authorization.[/dim]",
        border_style="cyan", padding=(1, 2), width=60,
    ))
    console.print()
    console.print("[bold]1[/] 🔑  [white]Login with Vercel[/white]  [dim](opens browser)[/dim]")
    console.print("[bold]2[/] ⏭️  [white]Skip[/white]  [dim](deploy without Vercel)[/dim]")
    console.print()
    choice = Prompt.ask("[bold cyan]➜[/] Select an option", choices=["1", "2"], default="1", show_choices=False)
    if choice == "2":
        console.print("\n[yellow]Skipping Vercel authentication.[/yellow]")
        return None

    if not CLIENT_ID:
        # This is an app configuration problem, not something an end user
        # of Opun8 can do anything about — never show them env var names.
        _show_error(
            "Vercel login isn't available right now.",
            hint="This is a setup issue on our end, not something you need to fix — please contact support if it keeps happening.",
            debug_detail="Vercel OAuth misconfigured: missing VERCEL_CLIENT_ID in .env",
        )
        return None

    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    authorize_url = _build_authorize_url(state, nonce, code_challenge)
    console.print()
    console.print("[dim]🌐 Opening browser for Vercel authorization...[/dim]")
    webbrowser.open(authorize_url)
    console.print("[bold]Waiting for Vercel to redirect back...[/bold]")
    console.print()

    result = _wait_for_callback()

    if result.error and not result.code:
        _show_error(
            "We couldn't complete the Vercel login.",
            hint="You can try again, or use a Personal Access Token instead.",
            debug_detail=f"OAuth callback error: {result.error}",
        )
        return None

    # Constant-time comparison: the CSRF risk here is low either way (this
    # runs locally against a value we generated), but there's no reason not
    # to use the safer comparison when it's this cheap.
    if not secrets.compare_digest(result.state or "", state):
        _show_error(
            "Something looked wrong with the login response, so we stopped here for your safety.",
            hint="Please try logging in again.",
            debug_detail="OAuth state mismatch on callback — possible CSRF, aborting login.",
        )
        return None

    token = exchange_code_for_token(result.code, code_verifier, nonce)
    if not token:
        _show_error(
            "We couldn't finish connecting your Vercel account.",
            hint="Please try again.",
        )
    else:
        prompt_team_or_pat(token)
        show_vercel_projects()
    return token


def exchange_code_for_token(code: str, code_verifier: str, nonce: Optional[str] = None) -> Optional[str]:
    try:
        if not code:
            _show_error("We didn't receive an authorization code from Vercel.", hint="Please try logging in again.")
            return None

        response = requests.post(
            TOKEN_ENDPOINT,
            data={
                "grant_type": "authorization_code",
                "client_id": CLIENT_ID,
                # No client_secret — see the note next to CLIENT_ID above.
                # PKCE proves who we are via code_verifier instead.
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": REDIRECT_URI,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
            timeout=30,
        )

        if response.status_code != 200:
            _show_error(
                "Vercel didn't accept the login request.",
                hint="Please try again in a moment.",
                debug_detail=f"Token exchange HTTP {response.status_code}: {response.text}",
            )
            return None

        data = response.json()
        if "access_token" not in data:
            error = data.get("error_description", data.get("error", "Unknown error"))
            _show_error(
                "We couldn't finish connecting your Vercel account.",
                hint="Please try again.",
                debug_detail=f"Token exchange response missing access_token: {error}",
            )
            return None

        # Defense-in-depth: if Vercel returned an id_token, make sure the
        # nonce we sent on the original authorize request comes back
        # unchanged before we trust anything else in this response.
        id_token = data.get("id_token")
        if id_token and nonce:
            claims = _decode_jwt_payload(id_token)
            returned_nonce = (claims or {}).get("nonce")
            if returned_nonce is not None and not secrets.compare_digest(str(returned_nonce), nonce):
                _show_error(
                    "Something looked wrong with the login response, so we didn't save it.",
                    hint="Please try logging in again.",
                    debug_detail="id_token nonce mismatch during token exchange — rejecting token.",
                )
                return None

        token = data["access_token"]
        refresh_token = data.get("refresh_token")
        expires_in = data.get("expires_in")
        user = get_vercel_user_info(token)
        if user:
            save_vercel_token(token, user, refresh_token, expires_in)
            console.print()
            console.print(f"[bold green]✅ Connected to Vercel as: {user.get('name', 'Unknown')}[/bold green]")
        else:
            save_vercel_token(token, {"name": "Unknown"}, refresh_token, expires_in)
            console.print("[yellow]Connected, but couldn't load your profile details.[/yellow]")
        return token

    except requests.RequestException as e:
        _show_error(
            "We couldn't reach Vercel to finish logging in.",
            hint="Check your internet connection and try again.",
            debug_detail=f"Token exchange network error: {e}",
        )
        return None
    except Exception as e:
        _show_error(
            "Something went wrong finishing the Vercel login.",
            hint="Please try again.",
            debug_detail=f"Token exchange unexpected error: {e}",
        )
        return None


def get_vercel_user_info(token: str) -> Optional[Dict]:
    try:
        response = requests.post(USERINFO_ENDPOINT, headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if response.status_code != 200:
            _debug_log(f"get_vercel_user_info HTTP {response.status_code}: {response.text}")
            return None
        data = response.json()
        if "name" not in data and "preferred_username" in data:
            data["name"] = data["preferred_username"]
        return data
    except Exception as e:
        _debug_log(f"get_vercel_user_info error: {e}")
        return None


def is_vercel_authenticated() -> bool:
    return get_vercel_token() is not None


def logout_vercel() -> None:
    try:
        if TOKEN_FILE.exists():
            TOKEN_FILE.unlink()
            console.print("[green]✅ Logged out of Vercel.[/green]")
        else:
            console.print("[yellow]Not logged in.[/yellow]")
    except Exception as e:
        _show_error(
            "Couldn't log you out on this machine.",
            hint="Please try again.",
            debug_detail=f"Failed to remove token file: {e}",
        )


TEAMS_ENDPOINT = "https://api.vercel.com/v2/teams"


def list_vercel_teams(token: str, silent: bool = False) -> Optional[list]:
    try:
        response = requests.get(TEAMS_ENDPOINT, headers={"Authorization": f"Bearer {token}"}, params={"limit": 100}, timeout=15)
        if response.status_code == 200:
            return response.json().get("teams", [])
        if response.status_code == 403:
            if not silent:
                _debug_log("list_vercel_teams: access denied (403) — likely no team/OAuth beta access.")
        else:
            if not silent:
                _show_error(
                    "We couldn't load your Vercel teams.",
                    hint="Please try again in a moment.",
                    debug_detail=f"list_vercel_teams HTTP {response.status_code}: {response.text}",
                )
        return None
    except requests.RequestException as e:
        if not silent:
            _show_error(
                "We couldn't reach Vercel to load your teams.",
                hint="Check your internet connection and try again.",
                debug_detail=f"list_vercel_teams network error: {e}",
            )
        return None
    except Exception as e:
        if not silent:
            _show_error(
                "Something went wrong loading your Vercel teams.",
                debug_detail=f"list_vercel_teams unexpected error: {e}",
            )
        return None


def prompt_team_selection(token: str) -> None:
    teams = list_vercel_teams(token)

    # Always default to Personal Account if no teams or error
    if teams is None or not teams:
        save_vercel_scope(None, "Personal Account")
        console.print("[green]✅ Using Personal Account.[/green]")
        return

    console.print()
    console.print("[bold]Where should Opun8 deploy to?[/bold]")
    console.print("[bold]0[/] 👤  [white]Personal Account[/white]  [dim](recommended)[/dim]")
    for i, team in enumerate(teams, start=1):
        label = team.get("name") or team.get("slug") or "Unnamed team"
        console.print(f"[bold]{i}[/] 👥  [white]{label}[/white]")
    console.print()

    selection = Prompt.ask(
        "[bold cyan]➜[/] Select an option",
        choices=[str(i) for i in range(0, len(teams) + 1)],
        default="0", show_choices=False,
    )

    if selection == "0":
        # A saved PAT is always scoped to a specific team (Vercel doesn't
        # issue "Personal Account" PATs — see the instructions above), so if
        # one is still saved it will keep authenticating as that team even
        # though the scope now says "Personal Account". Drop it and fall
        # back to the OAuth token, which does have personal-account access.
        if get_pat_token():
            if _read_token_file().get("access_token"):
                clear_pat_token()
                console.print(
                    "[dim]Cleared the saved team-scoped access token — "
                    "using your OAuth login for Personal Account access.[/dim]"
                )
            else:
                console.print(
                    "[yellow]⚠️ Your only saved credential is a team-scoped "
                    "Personal Access Token, which Vercel does not grant "
                    "Personal Account access to.[/yellow]"
                )
                console.print(
                    "[dim]Run the Vercel login flow again to get an OAuth "
                    "token with Personal Account access.[/dim]"
                )
        save_vercel_scope(None, "Personal Account")
        console.print("[green]✅ Using Personal Account.[/green]")
    else:
        team = teams[int(selection) - 1]
        label = team.get("name") or team.get("slug") or "Unnamed team"
        save_vercel_scope(team.get("id"), label)
        console.print(f"[green]✅ Using team: {label}[/green]")


def prompt_team_or_pat(token: str) -> None:
    teams = list_vercel_teams(token, silent=True)
    if teams is not None:
        prompt_team_selection(token)
        return

    console.print()
    console.print("[yellow]⚠️ Team access with OAuth is currently in private beta.[/yellow]")
    console.print("[dim]You can still deploy to your Personal Account.[/dim]")
    console.print()
    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    console.print("  [bold cyan]1[/] 👤  [white]Continue with Personal Account[/white]  [dim](recommended)[/dim]")
    console.print("  [bold cyan]2[/] 🔑  [white]Paste Vercel PAT for team access[/white]")
    if get_pat_token():
        console.print("  [bold cyan]3[/] 🗑️  [white]Remove saved PAT[/white]  [dim](go back to OAuth account)[/dim]")
    console.print()

    valid_choices = ["1", "2", "3"] if get_pat_token() else ["1", "2"]
    choice = Prompt.ask("[bold cyan]➜[/] Select an option", choices=valid_choices, default="1", show_choices=False)

    if choice == "3":
        clear_pat_token()
        console.print("[green]✅ Removed saved PAT. Using your OAuth account again.[/green]")
        save_vercel_scope(None, "Personal Account")
        return

    if choice == "2":
        console.print()
        console.print(Panel(
            "[bold]How to get a Vercel Personal Access Token[/bold]\n\n"
            "1. Your browser will open to [cyan]vercel.com/account/tokens[/cyan]\n"
            "   [dim](sign in first if it asks you to)[/dim]\n"
            "2. Click [bold]Create Token[/bold]\n"
            "3. Give it a name, e.g. [dim]\"Opun8 CLI\"[/dim]\n"
            "4. Under [bold]Scope[/bold], select the team you want to deploy to\n"
            "   [dim](not \"Personal Account\" — that won't grant team access)[/dim]\n"
            "5. Click [bold]Create Token[/bold] and copy the value shown\n"
            "   [dim](it's only ever shown once — copy it now)[/dim]\n\n"
            "[dim]Come back here and paste it at the prompt below.[/dim]",
            title="🔑 Vercel Personal Access Token",
            border_style="cyan",
            padding=(1, 2),
            width=64,
        ))
        console.print()
        webbrowser.open("https://vercel.com/account/tokens")

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            pat = Prompt.ask(
                "[bold cyan]➜[/] Paste your Vercel Personal Access Token"
            ).strip()

            if not pat:
                console.print("[yellow]No token provided.[/yellow]")
                break

            console.print("[dim]Verifying token...[/dim]")
            test_teams = list_vercel_teams(pat, silent=True)

            if test_teams is not None:
                save_pat_token(pat)
                console.print("[green]✅ PAT verified! You have team access.[/green]")
                prompt_team_selection(pat)
                return

            console.print(f"[red]❌ Invalid token or no team access. (attempt {attempt} of {max_attempts})[/red]")
            if attempt == max_attempts:
                console.print(
                    "[dim]If you're sure the token is correct, double check its Scope on the "
                    "tokens page includes the team you want — a Personal-Account-only token "
                    "will always fail here.[/dim]"
                )
            if attempt < max_attempts:
                retry = Prompt.ask(
                    "[bold cyan]➜[/] Try again?", choices=["y", "n"], default="y", show_choices=False
                )
                if retry.lower() != "y":
                    break

        console.print("[yellow]Using Personal Account for now.[/yellow]")
        save_vercel_scope(None, "Personal Account")
        return

    save_vercel_scope(None, "Personal Account")
    console.print("[green]✅ Using Personal Account.[/green]")


def switch_vercel_team() -> None:
    token = get_vercel_token()
    if not token:
        console.print("[yellow]Not connected to Vercel yet. Run the login flow first.[/yellow]")
        return
    prompt_team_or_pat(token)


PROJECTS_ENDPOINT = "https://api.vercel.com/v9/projects"


def list_vercel_projects(token: str, team_id: Optional[str] = None) -> Optional[list]:
    try:
        params = {"limit": 100}
        if team_id:
            params["teamId"] = team_id
        response = requests.get(PROJECTS_ENDPOINT, headers={"Authorization": f"Bearer {token}"}, params=params, timeout=15)
        if response.status_code == 200:
            return response.json().get("projects", [])
        if response.status_code == 403:
            _show_error("We don't have permission to see those Vercel projects.")
        elif response.status_code == 401:
            _show_error(
                "Your saved Vercel login has expired.",
                hint="Run `opun8 vercel --switch` to reconnect.",
            )
        else:
            _show_error(
                "We couldn't load your Vercel projects.",
                hint="Please try again in a moment.",
                debug_detail=f"list_vercel_projects HTTP {response.status_code}: {response.text}",
            )
        return None
    except requests.RequestException as e:
        _show_error(
            "We couldn't reach Vercel to load your projects.",
            hint="Check your internet connection and try again.",
            debug_detail=f"list_vercel_projects network error: {e}",
        )
        return None
    except Exception as e:
        _show_error(
            "Something went wrong loading your Vercel projects.",
            debug_detail=f"list_vercel_projects unexpected error: {e}",
        )
        return None


def show_vercel_projects(deploy_callback=None, team_id: Optional[str] = None) -> None:
    token = get_vercel_token()
    if not token:
        console.print("[yellow]Not connected to Vercel yet. Run the login flow first.[/yellow]")
        return
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
        return
    if len(projects) == 0:
        console.print()
        console.print(Panel(
            "[bold]No project yet[/bold]\n\n[dim]You haven't deployed anything to Vercel through Opun8 yet.[/dim]",
            border_style="cyan", padding=(1, 2), width=60,
        ))
        console.print()
        choice = Prompt.ask("[bold cyan]➜[/] Deploy your first project now?", choices=["y", "n"], default="y", show_choices=False)
        if choice.lower() == "y":
            if deploy_callback:
                deploy_callback()
            else:
                console.print("[yellow]No deploy command wired up yet — run your deploy command directly.[/yellow]")
        return
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
            try:
                updated_display = datetime.datetime.fromtimestamp(updated_at / 1000).strftime("%Y-%m-%d")
            except Exception as e:
                _debug_log(f"Failed to format updatedAt={updated_at!r}: {e}")
        table.add_row(name, framework, domain or "—", updated_display)
    console.print()
    console.print(table)
    console.print()