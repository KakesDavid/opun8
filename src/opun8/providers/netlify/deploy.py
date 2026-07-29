"""
Netlify deployment for Opun8.
Handles site creation, file upload, and deployment via Netlify API.

Error handling philosophy (matches Vercel):
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
from typing import Optional, Dict, Tuple, List, Callable

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
    """Thread-safe console printing."""
    with _console_lock:
        console.print(*args, **kwargs)


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
        _safe_print(f"[dim]debug: {message}[/dim]")


def _show_error(message: str, hint: Optional[str] = None, debug_detail: Optional[str] = None) -> None:
    """Single place non-threaded code prints an error to the terminal UI."""
    with _console_lock:
        console.print(f"[red]❌ {message}[/red]")
        if hint:
            console.print(f"[dim]{hint}[/dim]")
    if debug_detail:
        _debug_log(debug_detail)


def _safe_show_error(message: str, hint: Optional[str] = None, debug_detail: Optional[str] = None) -> None:
    """Thread-safe version of _show_error."""
    with _console_lock:
        console.print(f"[red]❌ {message}[/red]")
        if hint:
            console.print(f"[dim]{hint}[/dim]")
    if debug_detail:
        _debug_log(debug_detail)


# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

NETLIFY_API_BASE = "https://api.netlify.com/api/v1"
SITES_ENDPOINT = f"{NETLIFY_API_BASE}/sites"
DEPLOYS_ENDPOINT = f"{NETLIFY_API_BASE}/deploys"
ENV_ENDPOINT_TMPL = f"{NETLIFY_API_BASE}/sites/{{site_id}}/env"

MAX_CONCURRENT_UPLOADS = 8

EXCLUDE_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".pytest_cache", ".next", ".netlify", ".turbo",
    "dist", "build", "out", ".cache", "coverage",
    ".idea", ".vscode",
}
EXCLUDE_FILE_NAMES = {".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".log", ".tmp"}


def _is_env_file(name: str) -> bool:
    """Matches .env and any variant (.env.local, .env.production, etc.)"""
    return name == ".env" or name.startswith(".env.")


def prompt_for_env_vars(
    project_path: Path,
    env_targets: Optional[List[str]] = None,
) -> Tuple[Dict[str, str], List[str]]:
    """
    Scan the project for .env files and interactively ask the user which
    variables, if any, should be uploaded to Netlify as environment
    variables.
    """
    from opun8.services.env_service import detect_env_files, parse_env_file, merge_env_vars

    if env_targets is None:
        return prompt_env_files_selection(project_path)
    else:
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
        retry = Retry(allowed_methods=frozenset(["GET", "POST", "PUT", "PATCH"]), **retry_kwargs)
    except TypeError:
        retry = Retry(method_whitelist=frozenset(["GET", "POST", "PUT", "PATCH"]), **retry_kwargs)

    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=MAX_CONCURRENT_UPLOADS,
        pool_maxsize=MAX_CONCURRENT_UPLOADS,
    )
    session.mount("https://", adapter)
    return session


def _coerce_session(session_or_token) -> Tuple[requests.Session, bool]:
    """Accept either a shared Session or a raw token."""
    if isinstance(session_or_token, requests.Session):
        return session_or_token, False
    return _build_session(session_or_token), True


# ──────────────────────────────────────────────────────────────
# PROJECT NAME SANITIZATION
# ──────────────────────────────────────────────────────────────

def _sanitize_project_name(name: str) -> str:
    """Sanitize project name for Netlify."""
    name = name.lower()
    name = name.replace(" ", "-")
    name = re.sub(r'[^a-z0-9._-]', '-', name)
    name = re.sub(r'-{2,}', '-', name)
    name = name.strip('-')
    if len(name) > 100:
        name = name[:100]
    return name


# ──────────────────────────────────────────────────────────────
# SITE LOOKUP
# ──────────────────────────────────────────────────────────────

def _list_all_sites(
    session: requests.Session,
    per_page: int = 100,
) -> List[Dict]:
    """Fetch all sites visible to this token, following Netlify's pagination."""
    sites: List[Dict] = []
    page = 1

    while True:
        try:
            response = session.get(
                SITES_ENDPOINT,
                params={"per_page": per_page, "page": page},
                timeout=30,
            )
        except Exception as e:
            _debug_log(f"_list_all_sites network error: {e}")
            break

        if response.status_code != 200:
            _debug_log(f"_list_all_sites HTTP {response.status_code}: {response.text}")
            break

        data = response.json()
        if not data:
            break

        sites.extend(data)
        if len(data) < per_page:
            break

        page += 1

    return sites


def _find_site_by_name(
    session: requests.Session,
    site_name: str,
) -> Optional[str]:
    """Find a site by name."""
    for site in _list_all_sites(session):
        if site.get("name") == site_name:
            return site.get("id")
    return None


# ──────────────────────────────────────────────────────────────
# COLLECT PROJECT FILES
# ──────────────────────────────────────────────────────────────

def _collect_project_files(project_path: Path) -> List[Dict]:
    """
    Collect all files to upload, returning a list of dicts with path and SHA1.
    """
    files: List[Dict] = []
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

            # Compute SHA1 of file
            try:
                content = file_path.read_bytes()
                sha1 = hashlib.sha1(content).hexdigest()
                size = len(content)
            except Exception as e:
                _debug_log(f"Could not read {file_path}: {e}")
                continue

            rel_posix_path = file_path.relative_to(project_path).as_posix()
            files.append({
                "path": rel_posix_path,
                "sha1": sha1,
                "size": size,
            })

    except Exception as e:
        _show_error(
            "We couldn't read your project files.",
            hint="Check that the project folder is readable, then try again.",
            debug_detail=f"_collect_project_files error: {e}",
        )
        return []

    return files


# ──────────────────────────────────────────────────────────────
# ENVIRONMENT VARIABLES
# ──────────────────────────────────────────────────────────────

def _get_existing_env_vars(
    session: requests.Session,
    site_id: str,
) -> Dict[str, Dict]:
    """
    Map of env var key -> its full env record.
    Netlify uses a 'values' array with context/scope.
    """
    try:
        response = session.get(
            ENV_ENDPOINT_TMPL.format(site_id=site_id),
            timeout=30,
        )
        if response.status_code == 200:
            env_list = response.json()
            return {item["key"]: item for item in env_list if "key" in item}
        _debug_log(f"_get_existing_env_vars HTTP {response.status_code}: {response.text}")
    except Exception as e:
        _debug_log(f"_get_existing_env_vars error: {e}")
    return {}


def _set_env_vars(
    session: requests.Session,
    site_id: str,
    env_vars: Dict[str, str],
    context: str = "production",
) -> None:
    """
    Create or update environment variables on Netlify.

    Netlify env vars use a 'values' array with context/scope.
    """
    if not env_vars:
        return

    base_url = ENV_ENDPOINT_TMPL.format(site_id=site_id)
    existing = _get_existing_env_vars(session, site_id)
    failed_keys: List[str] = []

    for key, value in env_vars.items():
        # Netlify uses a 'values' array with context
        payload = {
            "key": key,
            "values": [
                {
                    "value": value,
                    "context": context,
                }
            ],
        }

        try:
            if key in existing:
                # Update existing env var
                response = session.patch(
                    f"{base_url}/{key}",
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=30,
                )
            else:
                response = session.post(
                    base_url,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                    timeout=30,
                )

            if response.status_code not in (200, 201):
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
# GET OR CREATE SITE
# ──────────────────────────────────────────────────────────────

def _get_or_create_site(
    session: requests.Session,
    site_name: str,
) -> Optional[str]:
    """Get existing site by name or create a new one."""
    try:
        # Try to find existing site
        site_id = _find_site_by_name(session, site_name)
        if site_id:
            _debug_log(f"_get_or_create_site: found existing site '{site_name}' -> {site_id}")
            return site_id

        # Create new site
        payload = {"name": site_name}
        response = session.post(
            SITES_ENDPOINT,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )

        if response.status_code in (200, 201):
            site_id = response.json().get("id")
            _debug_log(f"_get_or_create_site: created new site '{site_name}' -> {site_id}")
            return site_id

        if response.status_code == 409:
            site_id = _find_site_by_name(session, site_name)
            if site_id:
                return site_id

        _show_error(
            "We couldn't set up the Netlify site.",
            hint="Please try again in a moment.",
            debug_detail=f"_get_or_create_site HTTP {response.status_code}: {response.text}",
        )
        return None

    except Exception as e:
        _show_error(
            "We couldn't reach Netlify to set up the site.",
            hint="Check your internet connection and try again.",
            debug_detail=f"_get_or_create_site error: {e}",
        )
        return None


# ──────────────────────────────────────────────────────────────
# CREATE DEPLOYMENT WITH MANIFEST
# ──────────────────────────────────────────────────────────────

def _create_deploy_with_manifest(
    session: requests.Session,
    site_id: str,
    file_manifest: List[Dict],
) -> Optional[Dict]:
    """
    Create a deploy with a file manifest.

    Netlify expects a list of files with their SHA1 hashes.
    It returns which files it already has, so you only upload what's missing.

    Returns:
        Dict with deploy_id, required_files (list of files to upload), and deploy data.
        None on failure.
    """
    try:
        # Build the manifest format Netlify expects
        # Each file: {"path": "path/to/file", "sha1": "hash"}
        manifest = [
            {"path": f["path"], "sha1": f["sha1"]}
            for f in file_manifest
        ]

        payload = {
            "site_id": site_id,
            "files": manifest,
        }

        # ✅ Correct endpoint: /sites/{site_id}/deploys
        response = session.post(
            f"{SITES_ENDPOINT}/{site_id}/deploys",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=60,
        )

        if response.status_code in (200, 201):
            data = response.json()
            deploy_id = data.get("id")
            if not deploy_id:
                _debug_log(f"_create_deploy_with_manifest: response missing id: {data}")
                return None

            # Check which files are required (not already on Netlify)
            required_files = data.get("required", [])
            _debug_log(f"Deploy {deploy_id}: {len(required_files)} files required to upload")

            return {
                "deploy_id": deploy_id,
                "required_files": required_files,  # List of file paths to upload
                "deploy_data": data,
            }

        _show_error(
            "Netlify rejected the deployment.",
            hint="Please try again in a moment.",
            debug_detail=f"_create_deploy_with_manifest HTTP {response.status_code}: {response.text}",
        )
        return None

    except Exception as e:
        _show_error(
            "We couldn't reach Netlify to create the deployment.",
            hint="Check your internet connection and try again.",
            debug_detail=f"_create_deploy_with_manifest error: {e}",
        )
        return None


# ──────────────────────────────────────────────────────────────
# UPLOAD FILES TO DEPLOY
# ──────────────────────────────────────────────────────────────

def _upload_files_to_deploy(
    session: requests.Session,
    deploy_id: str,
    project_path: Path,
    file_manifest: List[Dict],
    required_files: List[str],
    progress_callback: Optional[Callable[[], None]] = None,
    max_workers: int = MAX_CONCURRENT_UPLOADS,
) -> bool:
    """
    Upload files to a Netlify deploy.

    ✅ Correct API: PUT /deploys/{deploy_id}/files/{file_path}
    With raw file content as body, Content-Type: application/octet-stream
    """
    if not required_files:
        return True

    # Create a lookup for file paths to their SHA1
    file_map = {f["path"]: f for f in file_manifest}
    # Filter to only required files
    upload_files = [file_map[f] for f in required_files if f in file_map]

    if not upload_files:
        return True

    failed = threading.Event()

    def _upload_one(file_info: Dict) -> bool:
        if failed.is_set():
            return False

        file_path = file_info["path"]
        abs_path = project_path / file_path

        try:
            content = abs_path.read_bytes()
        except Exception as e:
            _safe_show_error(
                f"Couldn't read {file_path}.",
                debug_detail=f"_upload_one read error for {file_path}: {e}",
            )
            return False

        try:
            # ✅ Correct: PUT to /deploys/{deploy_id}/files/{file_path}
            response = session.put(
                f"{DEPLOYS_ENDPOINT}/{deploy_id}/files/{file_path}",
                headers={"Content-Type": "application/octet-stream"},
                data=content,
                timeout=60,
            )

            if response.status_code in (200, 201):
                return True

            _safe_show_error(
                f"Couldn't upload {file_path}.",
                debug_detail=f"_upload_one HTTP {response.status_code} for {file_path}: {response.text}",
            )
            return False

        except Exception as e:
            _safe_show_error(
                f"Couldn't upload {file_path}.",
                debug_detail=f"_upload_one error for {file_path}: {e}",
            )
            return False

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_upload_one, f): f for f in upload_files}

        for future in as_completed(futures):
            if failed.is_set():
                # Cancel remaining futures
                for f in futures:
                    f.cancel()
                break

            try:
                success = future.result()
            except Exception as e:
                _debug_log(f"_upload_files_to_deploy worker raised: {e}")
                success = False

            if not success:
                failed.set()
                # ✅ Fail fast: break out of the loop
                break

            if progress_callback:
                progress_callback()

    return not failed.is_set()


# ──────────────────────────────────────────────────────────────
# WAIT FOR DEPLOYMENT
# ──────────────────────────────────────────────────────────────

def _wait_for_deploy(
    session: requests.Session,
    deploy_id: str,
    timeout: int = 300,
) -> Optional[str]:
    """
    Poll Netlify until deployment is ready.
    Returns the URL on success, None on failure.
    """
    try:
        start_time = time.time()
        interval = 3

        while time.time() - start_time < timeout:
            response = session.get(
                f"{DEPLOYS_ENDPOINT}/{deploy_id}",
                timeout=30,
            )

            if response.status_code == 200:
                data = response.json()
                state = data.get("state", "enqueued")

                if state == "ready":
                    url = data.get("url")
                    if url:
                        return url.replace("https://", "").replace("http://", "")
                    return None

                if state in ("error", "failed"):
                    error_msg = data.get("error_message") or f"deployment ended with state {state}"
                    console.print(f"[red]❌ Deployment failed: {error_msg}[/red]")
                    _debug_log(f"_wait_for_deploy ended in {state}: {error_msg}")
                    return None

                _debug_log(f"_wait_for_deploy: state={state}, progress={data.get('progress', 0)}")
            else:
                _debug_log(f"_wait_for_deploy status check HTTP {response.status_code}: {response.text}")

            time.sleep(interval)

        _show_error("The deployment took too long and timed out.", hint="Please try again.")
        return None

    except Exception as e:
        _show_error(
            "We couldn't check on the deployment's progress.",
            hint="Check your internet connection and try again.",
            debug_detail=f"_wait_for_deploy error: {e}",
        )
        return None


# ──────────────────────────────────────────────────────────────
# MAIN DEPLOY FUNCTION
# ──────────────────────────────────────────────────────────────

def deploy_to_netlify(
    token: str,
    site_name: str,
    project_path: Path,
    env_vars: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Deploy a project to Netlify.

    Args:
        token: Netlify API token
        site_name: Name of the site/project
        project_path: Local project path
        env_vars: Optional environment variables dict

    Returns:
        (success, url_or_message, site_id)
    """
    project_path = Path(project_path)
    site_id: Optional[str] = None  # ✅ Initialize before try

    if not project_path.exists() or not project_path.is_dir():
        _debug_log(f"deploy_to_netlify: project path not found: {project_path}")
        return False, f"We couldn't find the project folder: {project_path}", None

    # Detect env vars
    if env_vars is None:
        env_vars, _ = prompt_for_env_vars(project_path)

    original_name = site_name
    site_name = _sanitize_project_name(site_name)
    if not site_name:
        return False, "That site name isn't usable — try letters, numbers, and dashes.", None

    if original_name != site_name:
        console.print(f"[dim]ℹ️  Using site name: [cyan]{site_name}[/cyan][/dim]")

    console.print()
    console.print("[bold cyan]📦 Deploying to Netlify...[/bold cyan]")
    console.print(f"[dim]Site: {site_name}[/dim]")
    console.print(f"[dim]Path: {project_path}[/dim]")
    console.print()

    session = _build_session(token)

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

            # Step 1: Collect files with SHA1
            task = progress.add_task("[cyan]📦 Analyzing project...", total=None)
            file_manifest = _collect_project_files(project_path)
            if not file_manifest:
                progress.update(task, description="[red]❌ No files found to deploy.")
                return False, "No deployable files found in the project directory.", None
            progress.update(task, description=f"[green]✅ {len(file_manifest)} file(s) found.")

            # Step 2: Get or create site
            task = progress.add_task("[cyan]📦 Getting/creating site...", total=None)
            site_id = _get_or_create_site(session, site_name)
            if not site_id:
                return False, "Couldn't set up the site on Netlify. Please try again.", None
            progress.update(task, description="[green]✅ Site ready.")

            # Step 3: Set environment variables
            if env_vars:
                task = progress.add_task("[cyan]🔐 Setting environment variables...", total=None)
                _set_env_vars(session, site_id, env_vars)
                progress.update(task, description="[green]✅ Environment variables set.")

            # Step 4: Create deploy with manifest
            task = progress.add_task("[cyan]☁️ Creating deployment...", total=None)
            deploy_result = _create_deploy_with_manifest(session, site_id, file_manifest)
            if not deploy_result:
                return False, "Couldn't create the deployment on Netlify. Please try again.", site_id

            deploy_id = deploy_result["deploy_id"]
            required_files = deploy_result["required_files"]
            progress.update(task, description="[green]✅ Deployment created.")

            # Step 5: Upload required files
            upload_task = progress.add_task(
                "[cyan]☁️ Uploading files...", total=len(required_files)
            )
            progress_lock = threading.Lock()

            def _on_file_done():
                with progress_lock:
                    progress.advance(upload_task)

            upload_success = _upload_files_to_deploy(
                session, deploy_id, project_path, file_manifest, required_files,
                progress_callback=_on_file_done,
            )

            if not upload_success:
                progress.update(upload_task, description="[red]❌ File upload failed.")
                return False, "Couldn't upload one or more files to Netlify. Please try again.", site_id
            progress.update(upload_task, description="[green]✅ Files uploaded.")

            # Step 6: Wait for deploy
            task = progress.add_task("[cyan]⏳ Building...", total=None)
            final_url = _wait_for_deploy(session, deploy_id)
            if not final_url:
                return False, "The deployment failed or timed out. Please try again.", site_id
            progress.update(task, description="[green]✅ Deployment complete!")

        console.print()
        console.print("[bold green]🎉 Deployment successful![/bold green]")
        console.print(f"[dim]🌐 https://{final_url}[/dim]")

        return True, final_url, site_id

    except Exception as e:
        _debug_log(f"deploy_to_netlify unexpected error: {e}")
        return False, "Something went wrong during the deployment. Please try again.", site_id

    finally:
        session.close()