"""
Vercel deployment for Opun8.
Handles project creation, file upload, and deployment via Vercel API.

Error handling philosophy (matches auth.py):
  - What the END USER sees on screen is short, plain-English, and
    actionable. It never contains raw HTTP response bodies or Python
    exception text.
  - Technical detail goes to _debug_log() (~/.opun8/debug.log) instead,
    for whoever is building/operating Opun8 to diagnose. Set
    OPUN8_DEBUG=1 to also echo these live in the terminal.
  - Every network call and file operation is wrapped so failures degrade
    to a friendly message instead of a crash.
"""

import os
import hashlib
import threading
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Optional, Dict, Tuple, List, Callable, Union

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    MofNCompleteColumn,
)

from opun8.services.env_service import prompt_env_files_selection

console = Console()
_console_lock = threading.Lock()

DEBUG_LOG_FILE = Path.home() / ".opun8" / "debug.log"


def _safe_print(*args, **kwargs) -> None:
    """Thread-safe console printing (multiple upload workers print concurrently)."""
    with _console_lock:
        console.print(*args, **kwargs)


def _debug_log(message: str) -> None:
    """
    Record technical detail (raw HTTP bodies, exception text, etc.) for
    later troubleshooting. Never shown in normal command output.
    Best-effort only — logging must never be able to crash a deploy.
    """
    try:
        DEBUG_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(DEBUG_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass
    if os.environ.get("OPUN8_DEBUG"):
        _safe_print(f"[dim]debug: {message}[/dim]")


def _show_error(message: str, hint: Optional[str] = None, debug_detail: Optional[str] = None) -> None:
    """
    The single place non-threaded code prints an error to the terminal UI.
    Short, plain-English, actionable; technical detail goes to the debug
    log instead of the screen.
    """
    with _console_lock:
        console.print(f"[red]❌ {message}[/red]")
        if hint:
            console.print(f"[dim]{hint}[/dim]")
    if debug_detail:
        _debug_log(debug_detail)


def _safe_show_error(message: str, hint: Optional[str] = None, debug_detail: Optional[str] = None) -> None:
    """Thread-safe version of _show_error, for the concurrent upload workers."""
    with _console_lock:
        console.print(f"[red]❌ {message}[/red]")
        if hint:
            console.print(f"[dim]{hint}[/dim]")
    if debug_detail:
        _debug_log(debug_detail)


DEPLOYMENTS_ENDPOINT = "https://api.vercel.com/v13/deployments"
FILES_ENDPOINT = "https://api.vercel.com/v2/files"
PROJECTS_ENDPOINT = "https://api.vercel.com/v9/projects"
ENV_ENDPOINT_TMPL = "https://api.vercel.com/v10/projects/{project_id}/env"
TEAMS_ENDPOINT = "https://api.vercel.com/v2/teams"
DOMAINS_ENDPOINT_TMPL = "https://api.vercel.com/v10/projects/{project_id}/domains"

MAX_CONCURRENT_UPLOADS = 8
PROJECT_LIST_PAGE_SIZE = 100

EXCLUDE_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".pytest_cache", ".next", ".vercel", ".turbo",
    "dist", "build", "out", ".cache", "coverage",
    ".idea", ".vscode",
}
EXCLUDE_FILE_NAMES = {".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".log", ".tmp"}


def _is_env_file(name: str) -> bool:
    """
    Matches .env and any variant (.env.local, .env.production, .env.test,
    .env.anything) so secrets never get swept into a deployment upload.
    """
    return name == ".env" or name.startswith(".env.")


def prompt_for_env_vars(
    project_path: Path,
    env_targets: Optional[List[str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Scan the project for .env files and interactively ask the user which
    variables, if any, should be uploaded to Vercel as encrypted
    environment variables.

    Uses the centralized env_service for detection and prompting.

    Args:
        project_path: Path to the project root
        env_targets: Optional list of target environments to use.
                     If not provided, user will be prompted.

    Returns:
        Tuple of (selected_env_vars, target_environments)
    """
    if env_targets is None:
        return prompt_env_files_selection(project_path)
    else:
        # Use the provided targets, but still detect env vars
        from opun8.services.env_service import detect_env_files, parse_env_file, merge_env_vars

        env_files = detect_env_files(project_path)
        all_vars: Dict[str, str] = {}
        for env_file in env_files:
            vars_from_file = parse_env_file(env_file)
            if vars_from_file:
                all_vars = merge_env_vars(all_vars, vars_from_file, prefer="new")

        return all_vars, env_targets


# ──────────────────────────────────────────────────────────────
# SHARED HTTP SESSION
# ──────────────────────────────────────────────────────────────

def _build_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    retry_kwargs = dict(
        total=4,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        respect_retry_after_header=True,
    )
    try:
        # urllib3 >= 1.26
        retry = Retry(allowed_methods=frozenset(["GET", "POST"]), **retry_kwargs)
    except TypeError:
        # urllib3 < 1.26 uses the old kwarg name
        retry = Retry(method_whitelist=frozenset(["GET", "POST"]), **retry_kwargs)

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=MAX_CONCURRENT_UPLOADS,
        pool_maxsize=MAX_CONCURRENT_UPLOADS,
    )
    session.mount("https://", adapter)
    return session


# ──────────────────────────────────────────────────────────────
# PROJECT NAME SANITIZATION
# ──────────────────────────────────────────────────────────────

def _sanitize_project_name(name: str) -> str:
    """Sanitize project name for Vercel."""
    name = name.lower()
    name = name.replace(" ", "-")
    name = re.sub(r'[^a-z0-9._-]', '-', name)
    name = re.sub(r'-{2,}', '-', name)
    name = name.strip('-')
    if len(name) > 100:
        name = name[:100]
    return name


def get_team_name(session_or_token, team_id: str) -> Optional[str]:
    """Get the team name from team ID. Accepts a Session or a raw token."""
    session, owns_session = _coerce_session(session_or_token)
    try:
        response = session.get(f"{TEAMS_ENDPOINT}/{team_id}", timeout=10)
        if response.status_code == 200:
            return response.json().get("name")
        _debug_log(f"get_team_name HTTP {response.status_code}: {response.text}")
        return None
    except Exception as e:
        _debug_log(f"get_team_name error: {e}")
        return None
    finally:
        if owns_session:
            session.close()


def _coerce_session(session_or_token) -> Tuple[requests.Session, bool]:
    """Allow helper functions to accept either a shared Session or a raw token."""
    if isinstance(session_or_token, requests.Session):
        return session_or_token, False
    return _build_session(session_or_token), True


def _list_all_projects(
    session: requests.Session,
    team_id: Optional[str] = None,
) -> List[Dict]:
    """
    Fetch every project visible to this token/team, following Vercel's
    cursor-based pagination instead of assuming everything fits on one page.
    """
    projects: List[Dict] = []
    params: Dict[str, object] = {"limit": PROJECT_LIST_PAGE_SIZE}
    if team_id:
        params["teamId"] = team_id

    next_cursor: Optional[int] = None
    while True:
        page_params = dict(params)
        if next_cursor is not None:
            page_params["until"] = next_cursor

        try:
            response = session.get(PROJECTS_ENDPOINT, params=page_params, timeout=30)
        except Exception as e:
            _debug_log(f"_list_all_projects network error: {e}")
            break

        if response.status_code != 200:
            _debug_log(f"_list_all_projects HTTP {response.status_code}: {response.text}")
            break

        data = response.json()
        projects.extend(data.get("projects", []))

        pagination = data.get("pagination") or {}
        next_cursor = pagination.get("next")
        if not next_cursor:
            break

    return projects


def _find_project_by_name(
    session: requests.Session,
    project_name: str,
    team_id: Optional[str] = None,
) -> Optional[str]:
    """
    Direct name lookup — GET /v9/projects/{idOrName} also accepts a name.
    Used as a fallback when the paginated project list misses a project
    that (per Vercel) already exists under this name/scope.
    """
    try:
        params = {}
        if team_id:
            params["teamId"] = team_id
        response = session.get(f"{PROJECTS_ENDPOINT}/{project_name}", params=params, timeout=15)
        if response.status_code == 200:
            return response.json().get("id")
        _debug_log(f"_find_project_by_name HTTP {response.status_code}: {response.text}")
    except Exception as e:
        _debug_log(f"_find_project_by_name error: {e}")
    return None


# ──────────────────────────────────────────────────────────────
# RESOLVE THE CLEAN PRODUCTION DOMAIN
# ──────────────────────────────────────────────────────────────

def _resolve_production_domain(
    session: requests.Session,
    project_id: str,
    project_name: str,
    team_id: Optional[str],
    deployment_data: Optional[Dict] = None,
) -> str:
    """
    Vercel's raw deployment 'url' field (e.g. from GET /v13/deployments/:id)
    always looks like '<name>-<random-hash>-<scope-slug>.vercel.app' — every
    account, personal or team, has an implicit scope slug, and that slug
    leaks into the raw url. That's not a domain anyone should have to share.

    Prefer, in order:
      1. An alias already returned on the deployment payload itself.
      2. The project's current production alias (same clean value the
         project list/dashboard shows).
      3. The predictable default '<project-name>.vercel.app'.
      4. The raw deployment url, only as an absolute last resort.
    """
    deployment_data = deployment_data or {}

    aliases = deployment_data.get("alias") or []
    for alias in aliases:
        if isinstance(alias, str) and alias:
            return alias

    try:
        params: Dict[str, str] = {}
        if team_id:
            params["teamId"] = team_id
        response = session.get(f"{PROJECTS_ENDPOINT}/{project_id}", params=params, timeout=15)
        if response.status_code == 200:
            production = (response.json().get("targets") or {}).get("production") or {}
            prod_aliases = production.get("alias") or []
            if prod_aliases:
                return prod_aliases[0]
        else:
            _debug_log(f"_resolve_production_domain HTTP {response.status_code}: {response.text}")
    except Exception as e:
        _debug_log(f"_resolve_production_domain error: {e}")

    return f"{project_name}.vercel.app" if project_name else (deployment_data.get("url") or "")


# ──────────────────────────────────────────────────────────────
# RENAME VERCEL PROJECT
# ──────────────────────────────────────────────────────────────

def _add_vercel_app_domain(
    session: requests.Session,
    project_id: str,
    domain_name: str,
    team_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Claim `domain_name` (a full '<name>.vercel.app' string) as a domain
    on this project, via POST /v10/projects/{id}/domains.

    This is the piece a plain project rename is missing. Renaming a
    project (PATCH /v9/projects) only changes the project's `name`
    field — it is metadata-only and does not create, move, or reassign
    any '<name>.vercel.app' domain. Without this call, the project ends
    up "renamed" while still only resolving under its old URL.

    '<name>.vercel.app' domains are unique across ALL of Vercel, not
    just this account, and can't be reserved ahead of time — so this
    can legitimately fail with 409 if someone else already has it.

    Returns:
        (True, domain_name) once the domain is confirmed live on this
        project.
        (False, message) otherwise — message is plain-English and safe
        to show directly.
    """
    params: Dict[str, str] = {}
    if team_id:
        params["teamId"] = team_id
    try:
        response = session.post(
            DOMAINS_ENDPOINT_TMPL.format(project_id=project_id),
            headers={"Content-Type": "application/json"},
            params=params,
            json={"name": domain_name},
            timeout=30,
        )
    except Exception as e:
        _debug_log(f"_add_vercel_app_domain error for {domain_name}: {e}")
        return False, "Couldn't reach Vercel to claim that URL. Please try again."

    if response.status_code in (200, 201):
        try:
            verified = response.json().get("verified", True)
        except Exception:
            verified = True
        if not verified:
            _debug_log(f"_add_vercel_app_domain: {domain_name} added but verified=False")
        return True, domain_name

    if response.status_code == 409:
        return False, f"'{domain_name}' is already taken by someone else on Vercel — try a different name."

    try:
        api_error = response.json().get("error", {}).get("message", response.text)
    except Exception:
        api_error = response.text
    _debug_log(f"_add_vercel_app_domain HTTP {response.status_code} for {domain_name}: {api_error}")
    return False, "Couldn't claim that URL on Vercel. Please try again."


def rename_vercel_project(
    token: str,
    project_id: str,
    new_name: str,
    team_id: Optional[str] = None,
) -> Tuple[bool, str]:
    """
    Rename a Vercel project AND claim the matching
    '<new_name>.vercel.app' domain, so the URL this function reports
    back is one that actually resolves.

    Order matters: the domain is claimed FIRST, before the project's
    name is touched. A '<name>.vercel.app' domain can legitimately
    already belong to someone else and can't be reserved in advance —
    claiming it before renaming anything means a failure here leaves
    the project completely untouched, so the caller can just ask for a
    different name and retry, with nothing to roll back.

    Returns: (success, message/new_url) — the message is always
    plain-English and safe to show directly to whoever ran the command.
    """
    session = _build_session(token)
    try:
        new_name = _sanitize_project_name(new_name)
        if not new_name:
            return False, "That name isn't usable as a Vercel project name — try letters, numbers, and dashes."

        # Check if the name is available across ALL pages of YOUR
        # projects. This is a narrower, separate check from the domain
        # claim below — project names only need to be unique within
        # your own account, not across all of Vercel.
        for project in _list_all_projects(session, team_id):
            if project.get("name") == new_name and project.get("id") != project_id:
                return False, f"The name '{new_name}' is already in use by another project."

        # '<name>.vercel.app' is unique across ALL of Vercel — claim it
        # before touching the project's own name at all.
        new_domain = f"{new_name}.vercel.app"
        claimed, domain_message = _add_vercel_app_domain(session, project_id, new_domain, team_id)
        if not claimed:
            return False, domain_message

        # The domain is live. Now update the project's own name to
        # match, so the dashboard and the URL agree.
        rename_params: Dict[str, str] = {}
        if team_id:
            rename_params["teamId"] = team_id
        response = session.patch(
            f"{PROJECTS_ENDPOINT}/{project_id}",
            headers={"Content-Type": "application/json"},
            params=rename_params,
            json={"name": new_name},
            timeout=30,
        )
        if response.status_code != 200:
            # The domain was claimed but the PATCH failed. This leaves the
            # project's stored name out of sync with the new domain. On a
            # future deploy, name-based lookup won't find this project
            # under the intended name, so it'll try to create a new project
            # with that name — which will fail to claim the domain since
            # the old project already has it. Log it so the user knows.
            _debug_log(
                f"rename_vercel_project: domain claimed but project name PATCH failed "
                f"HTTP {response.status_code}: {response.text}"
            )
            # Return True anyway since the URL works, but warn the user.
            _show_error(
                "Domain claimed but project name update failed.",
                hint="The new URL works, but the dashboard may show the old name. "
                     "You can rename it manually in the Vercel dashboard.",
                debug_detail=f"PATCH failed with {response.status_code}: {response.text}",
            )

        return True, new_domain

    except Exception as e:
        _debug_log(f"rename_vercel_project unexpected error: {e}")
        return False, "Something went wrong renaming the project. Please try again."
    finally:
        session.close()


# ──────────────────────────────────────────────────────────────
# VERIFY PROJECT EXISTS
# ──────────────────────────────────────────────────────────────

def _verify_project_exists(
    session: requests.Session,
    project_id: str,
    team_id: Optional[str] = None,
) -> Optional[str]:
    """
    Verify that a project exists on Vercel.
    Returns the project ID if it exists, None otherwise.
    """
    try:
        params = {}
        if team_id:
            params["teamId"] = team_id
        response = session.get(
            f"{PROJECTS_ENDPOINT}/{project_id}",
            params=params,
            timeout=30,
        )
        if response.status_code == 200:
            return response.json().get("id")
        if response.status_code == 404:
            _debug_log(f"_verify_project_exists: project {project_id} not found (404)")
            return None
        _debug_log(f"_verify_project_exists HTTP {response.status_code}: {response.text}")
        return None
    except Exception as e:
        _debug_log(f"_verify_project_exists error: {e}")
        return None


# ──────────────────────────────────────────────────────────────
# MAIN DEPLOY FUNCTION
# ──────────────────────────────────────────────────────────────

def deploy_to_vercel(
    token: str,
    project_name: str,
    project_path: Path,
    framework: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
    team_id: Optional[str] = None,
    existing_project_id: Optional[str] = None,
    env_targets: Optional[List[str]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Deploy a project to Vercel.

    If env_vars is left as None, the project directory is scanned for
    .env-style files and the user is interactively prompted about which
    variables (if any) to upload. Pass env_vars={} explicitly to skip
    detection entirely (e.g. non-interactive/CI use).

    Args:
        token: Vercel API token
        project_name: Name of the project
        project_path: Local project path
        framework: Optional framework name
        env_vars: Optional environment variables dict
        team_id: Optional team ID
        existing_project_id: Optional existing project ID for redeploys
        env_targets: Optional list of target environments for env vars.
                     Only used if env_vars is provided.

    Returns:
        (success, url_or_message, project_id)
    """
    project_path = Path(project_path)
    if not project_path.exists() or not project_path.is_dir():
        _debug_log(f"deploy_to_vercel: project path not found or not a directory: {project_path}")
        return False, f"We couldn't find the project folder: {project_path}", None

    # Detect env vars using the centralized service
    if env_vars is None:
        env_vars, env_targets = prompt_for_env_vars(project_path)
    else:
        if env_targets is None:
            env_targets = ["production", "preview", "development"]

    original_name = project_name
    project_name = _sanitize_project_name(project_name)
    if not project_name:
        return False, "That project name isn't usable — try letters, numbers, and dashes.", None
    if original_name != project_name:
        console.print(f"[dim]ℹ️  Using project name: [cyan]{project_name}[/cyan][/dim]")

    console.print()
    console.print("[bold cyan]▲ Deploying to Vercel...[/bold cyan]")
    console.print(f"[dim]Project: {project_name}[/dim]")
    console.print(f"[dim]Path: {project_path}[/dim]")
    console.print()

    session = _build_session(token)
    project_id: Optional[str] = existing_project_id

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            MofNCompleteColumn(),
            console=console,
            transient=False,
        ) as progress:

            task = progress.add_task("[cyan]📦 Analyzing project...", total=None)
            files_to_upload = _collect_project_files(project_path)
            if not files_to_upload:
                progress.update(task, description="[red]❌ No files found to deploy.")
                return False, "No deployable files found in the project directory.", None
            progress.update(task, description=f"[green]✅ {len(files_to_upload)} file(s) found.")

            task = progress.add_task("[cyan]▲ Getting/creating project...", total=None)
            
            # If we have an existing project ID, use it directly
            if existing_project_id:
                # Verify the project exists
                verified_id = _verify_project_exists(session, existing_project_id, team_id)
                if verified_id:
                    project_id = verified_id
                    progress.update(task, description=f"[green]✅ Using existing project: {project_name}")
                else:
                    # If project doesn't exist, fall back to creating it
                    console.print("[yellow]⚠️ Existing project not found. Creating new project...[/yellow]")
                    project_id = _get_or_create_project(session, project_name, framework, team_id)
            else:
                # Normal flow: get or create
                project_id = _get_or_create_project(session, project_name, framework, team_id)
            
            if not project_id:
                return False, "Couldn't set up the project on Vercel. Please try again.", None
            progress.update(task, description="[green]✅ Project ready.")

            if env_vars:
                task = progress.add_task("[cyan]🔐 Setting environment variables...", total=None)
                _set_env_vars(session, project_id, env_vars, team_id, env_targets)
                progress.update(task, description="[green]✅ Environment variables set.")

            upload_task = progress.add_task(
                "[cyan]☁️ Uploading files...", total=len(files_to_upload)
            )
            progress_lock = threading.Lock()

            def _on_file_done():
                with progress_lock:
                    progress.advance(upload_task)

            files_manifest = _upload_project_files(
                session, project_path, files_to_upload, team_id,
                progress_callback=_on_file_done,
            )
            if files_manifest is None:
                progress.update(upload_task, description="[red]❌ File upload failed.")
                return False, "Couldn't upload one or more files to Vercel. Please try again.", project_id
            progress.update(upload_task, description="[green]✅ Files uploaded.")

            task = progress.add_task("[cyan]🚀 Creating deployment...", total=None)
            deployment_id = _create_deployment(
                session, project_id, project_name, files_manifest, framework, team_id
            )
            if not deployment_id:
                return False, "Couldn't create the deployment on Vercel. Please try again.", project_id
            progress.update(task, description="[green]✅ Deployment created.")

            task = progress.add_task("[cyan]⏳ Building...", total=None)
            final_url = _wait_for_deployment(
                session, deployment_id, project_id, project_name, team_id
            )
            if not final_url:
                return False, "The deployment failed or timed out. Please try again.", project_id
            progress.update(task, description="[green]✅ Deployment complete!")

        console.print()
        console.print("[bold green]🎉 Deployment successful![/bold green]")
        console.print(f"[dim]🌐 https://{final_url}[/dim]")

        return True, final_url, project_id

    except Exception as e:
        _debug_log(f"deploy_to_vercel unexpected error: {e}")
        return False, "Something went wrong during the deployment. Please try again.", project_id

    finally:
        session.close()


# ──────────────────────────────────────────────────────────────
# COLLECT PROJECT FILES
# ──────────────────────────────────────────────────────────────

def _collect_project_files(project_path: Path) -> List[Path]:
    files: List[Path] = []
    if not project_path.exists() or not project_path.is_dir():
        _show_error(
            "We couldn't find the project folder to deploy.",
            hint=f"Check that this path exists: {project_path}",
        )
        return []
    try:
        for file_path in project_path.rglob("*"):
            if not file_path.is_file():
                continue
            rel_parts = file_path.relative_to(project_path).parts
            if any(part in EXCLUDE_DIR_NAMES for part in rel_parts[:-1]):
                continue
            if file_path.name in EXCLUDE_FILE_NAMES:
                continue
            if _is_env_file(file_path.name):
                continue
            if file_path.suffix in EXCLUDE_SUFFIXES:
                continue
            files.append(file_path)
    except Exception as e:
        _show_error(
            "We couldn't read your project files.",
            hint="Check that the project folder is readable, then try again.",
            debug_detail=f"_collect_project_files error: {e}",
        )
        return []
    return files


# ──────────────────────────────────────────────────────────────
# UPLOAD FILES
# ──────────────────────────────────────────────────────────────

def _upload_project_files(
    session: requests.Session,
    project_path: Path,
    files: List[Path],
    team_id: Optional[str] = None,
    progress_callback: Optional[Callable[[], None]] = None,
    max_workers: int = MAX_CONCURRENT_UPLOADS,
) -> Optional[List[Dict]]:
    manifest: List[Dict] = []
    manifest_lock = threading.Lock()
    failed = threading.Event()

    def _upload_one(file_path: Path) -> Optional[Dict]:
        if failed.is_set():
            return None
        rel_posix_path = file_path.relative_to(project_path).as_posix()
        try:
            content = file_path.read_bytes()
        except Exception as e:
            _safe_show_error(
                f"Couldn't read {rel_posix_path}.",
                debug_detail=f"_upload_one read error for {rel_posix_path}: {e}",
            )
            return None
        sha1 = hashlib.sha1(content).hexdigest()
        return _upload_single_file(session, content, sha1, rel_posix_path, team_id)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_upload_one, fp): fp for fp in files}
        for future in as_completed(futures):
            try:
                entry = future.result()
            except Exception as e:
                _debug_log(f"_upload_project_files worker raised: {e}")
                entry = None
            if entry is None:
                failed.set()
                # Cancel pending futures (already-running ones will complete,
                # but their results will be ignored since failed is set)
                for f in futures:
                    f.cancel()
                continue
            with manifest_lock:
                manifest.append(entry)
            if progress_callback:
                progress_callback()

    if failed.is_set():
        return None
    return manifest


def _upload_single_file(
    session: requests.Session,
    content: bytes,
    sha1: str,
    rel_posix_path: str,
    team_id: Optional[str] = None,
) -> Optional[Dict]:
    try:
        params = {}
        if team_id:
            params["teamId"] = team_id
        response = session.post(
            FILES_ENDPOINT,
            headers={
                "Content-Length": str(len(content)),
                "x-vercel-digest": sha1,
            },
            params=params,
            data=content,
            timeout=60,
        )
        if response.status_code == 200:
            return {"file": rel_posix_path, "sha": sha1, "size": len(content)}
        _safe_show_error(
            f"Couldn't upload {rel_posix_path}.",
            debug_detail=f"_upload_single_file HTTP {response.status_code} for {rel_posix_path}: {response.text}",
        )
        return None
    except Exception as e:
        _safe_show_error(
            f"Couldn't upload {rel_posix_path}.",
            debug_detail=f"_upload_single_file error for {rel_posix_path}: {e}",
        )
        return None


# ──────────────────────────────────────────────────────────────
# GET OR CREATE PROJECT (with direct name lookup fallback)
# ──────────────────────────────────────────────────────────────

def _get_or_create_project(
    session: requests.Session,
    project_name: str,
    framework: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Optional[str]:
    try:
        # First: try to find it via paginated list
        for project in _list_all_projects(session, team_id):
            if project.get("name") == project_name:
                return project.get("id")

        # Second: try to create it
        payload: Dict[str, Union[str, Dict]] = {"name": project_name}
        if framework is not None:
            mapped = _map_framework(framework)
            if mapped:
                payload["framework"] = mapped

        create_params = {}
        if team_id:
            create_params["teamId"] = team_id

        response = session.post(
            PROJECTS_ENDPOINT,
            headers={"Content-Type": "application/json"},
            params=create_params,
            json=payload,
            timeout=30,
        )

        if response.status_code in (200, 201):
            return response.json().get("id")

        # Third: if create failed with 400/409 (project exists but list missed it),
        # try direct name lookup as fallback
        if response.status_code in (400, 409):
            existing_id = _find_project_by_name(session, project_name, team_id)
            if existing_id:
                _debug_log(
                    f"_get_or_create_project: create conflicted "
                    f"(HTTP {response.status_code}) but direct lookup found "
                    f"existing project '{project_name}' -> {existing_id}; using it."
                )
                return existing_id

        _show_error(
            "We couldn't set up the Vercel project.",
            hint="Please try again in a moment.",
            debug_detail=f"_get_or_create_project HTTP {response.status_code}: {response.text}",
        )
        return None

    except Exception as e:
        _show_error(
            "We couldn't reach Vercel to set up the project.",
            hint="Check your internet connection and try again.",
            debug_detail=f"_get_or_create_project error: {e}",
        )
        return None


# ──────────────────────────────────────────────────────────────
# MAP FRAMEWORK
# ──────────────────────────────────────────────────────────────

_FRAMEWORK_MAP = {
    "react": "create-react-app",
    "next": "nextjs",
    "nextjs": "nextjs",
    "vue": "vue",
    "angular": "angular",
    "svelte": "svelte",
    "sveltekit": "sveltekit",
    "node": "node",
    "nodejs": "node",
    "python": "python",
    "django": "django",
    "flask": "flask",
    "static": None,
    "html": None,
    "vite": "vite",
    "astro": "astro",
}


def _map_framework(framework: Optional[str]) -> Optional[str]:
    if not framework:
        return None
    return _FRAMEWORK_MAP.get(framework.lower(), None)


# ──────────────────────────────────────────────────────────────
# SET ENVIRONMENT VARIABLES (create-or-update)
# ──────────────────────────────────────────────────────────────

def _get_existing_env_vars(
    session: requests.Session,
    project_id: str,
    team_id: Optional[str] = None,
) -> Dict[str, str]:
    """Map of env var key -> its Vercel env-record id, for upsert logic."""
    params = {}
    if team_id:
        params["teamId"] = team_id
    try:
        response = session.get(
            ENV_ENDPOINT_TMPL.format(project_id=project_id),
            params=params,
            timeout=30,
        )
        if response.status_code == 200:
            return {
                item["key"]: item["id"]
                for item in response.json().get("envs", [])
                if "key" in item and "id" in item
            }
        _debug_log(f"_get_existing_env_vars HTTP {response.status_code}: {response.text}")
    except Exception as e:
        _debug_log(f"_get_existing_env_vars error: {e}")
    return {}


def _set_env_vars(
    session: requests.Session,
    project_id: str,
    env_vars: Dict[str, str],
    team_id: Optional[str] = None,
    targets: Optional[List[str]] = None,
) -> None:
    """
    Create or update each environment variable. A plain POST fails with a
    conflict if the key already exists (e.g. on redeploy), so existing keys
    are looked up first and updated in place via PATCH.

    Args:
        session: Requests session
        project_id: Vercel project ID
        env_vars: Environment variables to set
        team_id: Optional team ID
        targets: Target environments (production, preview, development)
    """
    if not env_vars:
        return

    if targets is None:
        targets = ["production", "preview", "development"]

    params = {}
    if team_id:
        params["teamId"] = team_id
    base_url = ENV_ENDPOINT_TMPL.format(project_id=project_id)
    existing = _get_existing_env_vars(session, project_id, team_id)
    failed_keys: List[str] = []

    for key, value in env_vars.items():
        payload = {
            "key": key,
            "value": value,
            "target": targets,
            "type": "encrypted",
        }
        try:
            if key in existing:
                response = session.patch(
                    f"{base_url}/{existing[key]}",
                    headers={"Content-Type": "application/json"},
                    params=params,
                    json={"value": value, "target": targets},
                    timeout=30,
                )
            else:
                response = session.post(
                    base_url,
                    headers={"Content-Type": "application/json"},
                    params=params,
                    json=payload,
                    timeout=30,
                )
            if response.status_code not in (200, 201):
                # If we got a 409, the key might have been created by a
                # previous retry. Try to look it up again.
                if response.status_code == 409:
                    _debug_log(f"_set_env_vars: key '{key}' returned 409, checking if it exists...")
                    existing = _get_existing_env_vars(session, project_id, team_id)
                    if key in existing:
                        _debug_log(f"_set_env_vars: key '{key}' found after 409, updating instead.")
                        response = session.patch(
                            f"{base_url}/{existing[key]}",
                            headers={"Content-Type": "application/json"},
                            params=params,
                            json={"value": value, "target": targets},
                            timeout=30,
                        )
                        if response.status_code in (200, 201):
                            continue
                failed_keys.append(key)
                _debug_log(f"_set_env_vars HTTP {response.status_code} for key={key}: {response.text}")
        except Exception as e:
            failed_keys.append(key)
            _debug_log(f"_set_env_vars error for key={key}: {e}")

    if failed_keys:
        console.print(
            f"[yellow]⚠️ Couldn't set {len(failed_keys)} environment variable(s) "
            f"({', '.join(failed_keys)}) — deployment will continue without them.[/yellow]"
        )


# ──────────────────────────────────────────────────────────────
# CREATE DEPLOYMENT
# ──────────────────────────────────────────────────────────────

def _create_deployment(
    session: requests.Session,
    project_id: str,
    project_name: str,
    files_manifest: List[Dict],
    framework: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Optional[str]:
    try:
        payload: Dict[str, Union[str, Dict]] = {
            "name": project_name,
            "project": project_id,
            "target": "production",
            "files": files_manifest,
        }
        if framework is not None:
            mapped = _map_framework(framework)
            if mapped:
                payload["projectSettings"] = {"framework": mapped}

        params = {"skipAutoDetectionConfirmation": "1"}
        if team_id:
            params["teamId"] = team_id

        response = session.post(
            DEPLOYMENTS_ENDPOINT,
            headers={"Content-Type": "application/json"},
            params=params,
            json=payload,
            timeout=60,
        )

        if response.status_code in (200, 201):
            return response.json().get("id")
        _show_error(
            "Vercel rejected the deployment.",
            hint="Please try again in a moment.",
            debug_detail=f"_create_deployment HTTP {response.status_code}: {response.text}",
        )
        return None

    except Exception as e:
        _show_error(
            "We couldn't reach Vercel to create the deployment.",
            hint="Check your internet connection and try again.",
            debug_detail=f"_create_deployment error: {e}",
        )
        return None


# ──────────────────────────────────────────────────────────────
# WAIT FOR DEPLOYMENT
# ──────────────────────────────────────────────────────────────

def _wait_for_deployment(
    session: requests.Session,
    deployment_id: str,
    project_id: str,
    project_name: str,
    team_id: Optional[str] = None,
    timeout: int = 180,
) -> Optional[str]:
    try:
        params = {}
        if team_id:
            params["teamId"] = team_id
        start_time = time.time()
        interval = 3

        while time.time() - start_time < timeout:
            response = session.get(
                f"{DEPLOYMENTS_ENDPOINT}/{deployment_id}",
                params=params,
                timeout=30,
            )
            if response.status_code == 200:
                data = response.json()
                ready_state = data.get("readyState", "QUEUED")
                if ready_state == "READY":
                    return _resolve_production_domain(
                        session, project_id, project_name, team_id, data
                    )
                elif ready_state in ("ERROR", "CANCELED"):
                    # This is about the user's own build/code, not our API
                    # plumbing, so it's genuinely actionable — show it.
                    error_msg = (
                        data.get("errorMessage")
                        or (data.get("aliasError") or {}).get("message")
                        or f"deployment ended with state {ready_state}"
                    )
                    console.print(f"[red]❌ Deployment failed: {error_msg}[/red]")
                    _debug_log(f"_wait_for_deployment ended in {ready_state}: {error_msg}")
                    return None
            else:
                _debug_log(f"_wait_for_deployment status check HTTP {response.status_code}: {response.text}")
            time.sleep(interval)

        _show_error("The deployment took too long and timed out.", hint="Please try again.")
        return None

    except Exception as e:
        _show_error(
            "We couldn't check on the deployment's progress.",
            hint="Check your internet connection and try again.",
            debug_detail=f"_wait_for_deployment error: {e}",
        )
        return None