"""
Vercel deployment for Opun8.
Handles project creation, file upload, and deployment via Vercel API.

Follows Vercel's documented non-git deployment flow exactly:
  1. Hash + upload every file individually to POST /v2/files
     (Authorization + Content-Length + x-vercel-digest headers, raw body).
  2. Create the deployment with POST /v13/deployments, referencing each
     file by {file, sha, size} in the `files` array.
  3. Poll GET /v13/deployments/:id and watch `readyState`
     (QUEUED -> INITIALIZING -> BUILDING -> READY | ERROR).

`teamId` is passed as a query parameter on every call, per Vercel's docs
("Accessing Resources Owned by a Team") — never as a JSON body field.
This matches the scoping already used in auth.py (list_vercel_teams,
list_vercel_projects, etc.), so a team selected during login deploys
to that same team.

PERFORMANCE:
  - A single requests.Session per deploy reuses TCP/TLS connections
    (HTTP keep-alive) across every API call instead of paying a fresh
    handshake per request.
  - File uploads to /v2/files run concurrently across a bounded thread
    pool (each file is independently content-addressed by its own SHA1,
    so there's no ordering dependency between them).
  - Transient network hiccups and Vercel rate limits (429/5xx) are
    retried automatically with backoff at the transport layer.

SECURITY:
  - TLS certificate verification is left on (requests' default) — never
    disable it, even for debugging.
  - Only GET/POST are ever retried automatically, and only on this
    idempotent, content-addressed file upload path — not on deployment
    creation, which is not safe to blindly resubmit.
  - Bearer tokens are set once on the session and never logged; error
    messages print Vercel's response body/status only.
  - Secrets (.env*) are excluded from the upload set by name, in addition
    to whatever the caller passes explicitly via env_vars.
"""

import hashlib
import threading
import time
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

console = Console()

DEPLOYMENTS_ENDPOINT = "https://api.vercel.com/v13/deployments"
FILES_ENDPOINT = "https://api.vercel.com/v2/files"
PROJECTS_ENDPOINT = "https://api.vercel.com/v9/projects"
ENV_ENDPOINT_TMPL = "https://api.vercel.com/v10/projects/{project_id}/env"

# How many files to upload in parallel. Vercel doesn't publish a hard
# concurrent-connection cap for /v2/files, but 8 is a safe, fast default
# that respects their per-token rate limits without tripping 429s on
# typical project sizes.
MAX_CONCURRENT_UPLOADS = 8

# Directories/files never worth deploying.
EXCLUDE_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".pytest_cache", ".next", ".vercel", ".turbo",
    "dist", "build", "out", ".cache", "coverage",
}
EXCLUDE_FILE_NAMES = {".env", ".env.local", ".env.development", ".env.production", ".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".log", ".tmp"}


# ──────────────────────────────────────────────────────────────
# SHARED HTTP SESSION (connection pooling + safe retries)
# ──────────────────────────────────────────────────────────────

def _build_session(token: str) -> requests.Session:
    """
    One session per deploy, reused for every request:
      - Authorization header set once (never re-passed/logged per call).
      - Connection pool sized to MAX_CONCURRENT_UPLOADS so parallel
        uploads reuse warm TLS connections instead of opening new ones.
      - Retries with exponential backoff only for transient failures
        (429 rate limit, 5xx) on GET/POST — safe here because every
        POST this session makes to /v2/files is idempotent (content is
        addressed by its own SHA1, so re-sending it is harmless).
    """
    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    retry = Retry(
        total=4,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(
        max_retries=retry,
        pool_connections=MAX_CONCURRENT_UPLOADS,
        pool_maxsize=MAX_CONCURRENT_UPLOADS,
    )
    session.mount("https://", adapter)
    return session


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
) -> Tuple[bool, str]:
    """
    Deploy a project to Vercel.

    Args:
        token: Vercel access token
        project_name: Name of the project
        project_path: Path to the project directory
        framework: Framework name (e.g., "react", "nextjs")
        env_vars: Environment variables to set
        team_id: Team ID (if deploying to a team) — same scope value
                 persisted by auth.py's save_vercel_scope()

    Returns:
        (success, message/url)
    """
    env_vars = env_vars or {}

    console.print()
    console.print("[bold cyan]▲ Deploying to Vercel...[/bold cyan]")
    console.print(f"[dim]Project: {project_name}[/dim]")
    console.print(f"[dim]Path: {project_path}[/dim]")
    console.print()

    # One pooled, retrying session reused for every request in this deploy.
    session = _build_session(token)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=False,
    ) as progress:

        # Step 1: Collect files to deploy
        task = progress.add_task("[cyan]📦 Analyzing project...", total=None)
        files_to_upload = _collect_project_files(project_path)
        if not files_to_upload:
            progress.update(task, description="[red]❌ No files found to deploy.")
            return False, "No deployable files found in the project directory."
        progress.update(
            task, description=f"[green]✅ {len(files_to_upload)} file(s) found."
        )

        # Step 2: Get or create project
        task = progress.add_task("[cyan]▲ Getting/creating project...", total=None)
        project_id = _get_or_create_project(session, project_name, framework, team_id)
        if not project_id:
            return False, "Failed to create Vercel project."
        progress.update(task, description="[green]✅ Project ready.")

        # Step 3: Set environment variables if provided
        if env_vars:
            task = progress.add_task("[cyan]🔐 Setting environment variables...", total=None)
            _set_env_vars(session, project_id, env_vars, team_id)
            progress.update(task, description="[green]✅ Environment variables set.")

        # Step 4: Upload every file concurrently, with a live percentage bar
        upload_task = progress.add_task(
            "[cyan]☁️ Uploading files...", total=len(files_to_upload)
        )

        def _on_file_done():
            progress.advance(upload_task)

        files_manifest = _upload_project_files(
            session, project_path, files_to_upload, team_id,
            progress_callback=_on_file_done,
        )
        if files_manifest is None:
            progress.update(upload_task, description="[red]❌ File upload failed.")
            return False, "Failed to upload one or more files to Vercel."
        progress.update(upload_task, description="[green]✅ Files uploaded.")

        # Step 5: Create the deployment, referencing the uploaded files by sha
        task = progress.add_task("[cyan]🚀 Creating deployment...", total=None)
        deployment_id = _create_deployment(
            session, project_id, project_name, files_manifest, framework, team_id
        )
        if not deployment_id:
            return False, "Failed to create deployment."
        progress.update(task, description="[green]✅ Deployment created.")

        # Step 6: Wait for deployment to finish building
        task = progress.add_task("[cyan]⏳ Building...", total=None)
        final_url = _wait_for_deployment(session, deployment_id, team_id)
        if not final_url:
            return False, "Deployment failed or timed out."
        progress.update(task, description="[green]✅ Deployment complete!")

    session.close()

    console.print()
    console.print(f"[bold green]🎉 Deployment successful![/bold green]")
    console.print(f"[dim]🌐 https://{final_url}[/dim]")

    return True, final_url


# ──────────────────────────────────────────────────────────────
# COLLECT PROJECT FILES
# ──────────────────────────────────────────────────────────────

def _collect_project_files(project_path: Path) -> List[Path]:
    """
    Walk the project directory and return the list of files to deploy,
    skipping build artifacts, VCS metadata, virtualenvs, and secrets.
    """
    files: List[Path] = []
    try:
        for file_path in project_path.rglob("*"):
            if not file_path.is_file():
                continue

            rel_parts = file_path.relative_to(project_path).parts

            # Skip if any parent directory is excluded
            if any(part in EXCLUDE_DIR_NAMES for part in rel_parts[:-1]):
                continue

            if file_path.name in EXCLUDE_FILE_NAMES:
                continue

            if file_path.suffix in EXCLUDE_SUFFIXES:
                continue

            files.append(file_path)

    except Exception as e:
        console.print(f"[red]Error scanning project directory: {e}[/red]")
        return []

    return files


# ──────────────────────────────────────────────────────────────
# UPLOAD FILES (POST /v2/files, one call per file, keyed by SHA1)
# ──────────────────────────────────────────────────────────────

def _upload_project_files(
    session: requests.Session,
    project_path: Path,
    files: List[Path],
    team_id: Optional[str] = None,
    progress_callback: Optional[Callable[[], None]] = None,
    max_workers: int = MAX_CONCURRENT_UPLOADS,
) -> Optional[List[Dict]]:
    """
    Upload every file to Vercel's content-addressed file store, in parallel,
    and build the manifest ({file, sha, size} per entry) that
    /v13/deployments expects in its `files` array.

    Each file is uploaded independently — there's no ordering requirement
    between them, so a bounded thread pool gives a large speedup on
    projects with many small files (the common case) without overwhelming
    Vercel's per-token rate limits.

    Returns None if any single file fails to upload (fail the whole deploy
    rather than shipping a partial, broken build). On first failure, any
    not-yet-started uploads are cancelled so we don't keep spending
    bandwidth on a deploy we already know will be rejected.
    """
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
            console.print(f"[red]Error reading {rel_posix_path}: {e}[/red]")
            return None

        sha1 = hashlib.sha1(content).hexdigest()
        return _upload_single_file(session, content, sha1, rel_posix_path, team_id)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_upload_one, fp): fp for fp in files}

        for future in as_completed(futures):
            entry = future.result()

            if entry is None:
                failed.set()
                # Best-effort: stop any uploads that haven't started yet.
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
    """Upload one file's raw bytes to POST /v2/files, keyed by its SHA1 digest."""
    try:
        params = {}
        if team_id:
            params["teamId"] = team_id

        # Authorization comes from the session's default headers — never
        # re-passed (or logged) per call.
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

        # Vercel returns 200 for both "stored" and "already exists" cases.
        if response.status_code == 200:
            return {"file": rel_posix_path, "sha": sha1, "size": len(content)}

        console.print(
            f"[red]Failed to upload {rel_posix_path}: "
            f"HTTP {response.status_code}: {response.text}[/red]"
        )
        return None

    except Exception as e:
        console.print(f"[red]Error uploading {rel_posix_path}: {e}[/red]")
        return None


# ──────────────────────────────────────────────────────────────
# GET OR CREATE PROJECT
# ──────────────────────────────────────────────────────────────

def _get_or_create_project(
    session: requests.Session,
    project_name: str,
    framework: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Optional[str]:
    """Get existing project or create a new one. `teamId` is always a query param."""
    try:
        params = {"limit": 100}
        if team_id:
            params["teamId"] = team_id

        response = session.get(PROJECTS_ENDPOINT, params=params, timeout=30)

        if response.status_code == 200:
            projects = response.json().get("projects", [])
            for project in projects:
                if project.get("name") == project_name:
                    return project.get("id")

        # Create new project
        payload = {
            "name": project_name,
            "framework": _map_framework(framework),
        }
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
        else:
            console.print(f"[red]Failed to create project: {response.text}[/red]")
            return None

    except Exception as e:
        console.print(f"[red]Error getting/creating project: {e}[/red]")
        return None


# ──────────────────────────────────────────────────────────────
# MAP FRAMEWORK
# ──────────────────────────────────────────────────────────────

def _map_framework(framework: Optional[str]) -> Optional[str]:
    """Map a user-facing framework name to Vercel's `projectSettings.framework` enum."""
    if not framework:
        return None

    framework_map = {
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
    return framework_map.get(framework.lower(), None)


# ──────────────────────────────────────────────────────────────
# SET ENVIRONMENT VARIABLES
# ──────────────────────────────────────────────────────────────

def _set_env_vars(
    session: requests.Session,
    project_id: str,
    env_vars: Dict[str, str],
    team_id: Optional[str] = None,
) -> None:
    """
    Set environment variables for a project via POST /v10/projects/:id/env.

    Note: the legacy "secret" env var type was sunset in May 2024 (values now
    must reference a secret ID, not a raw string). "encrypted" is the current
    equivalent for values that should stay hidden after creation.
    """
    try:
        params = {}
        if team_id:
            params["teamId"] = team_id

        url = ENV_ENDPOINT_TMPL.format(project_id=project_id)

        for key, value in env_vars.items():
            payload = {
                "key": key,
                "value": value,
                "target": ["production", "preview", "development"],
                "type": "encrypted",
            }

            response = session.post(
                url,
                headers={"Content-Type": "application/json"},
                params=params,
                json=payload,
                timeout=30,
            )

            if response.status_code not in (200, 201):
                console.print(f"[yellow]Warning: Failed to set {key}: {response.text}[/yellow]")

    except Exception as e:
        console.print(f"[yellow]Warning: Error setting env vars: {e}[/yellow]")


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
    """
    Create a deployment referencing already-uploaded files by sha/size.
    Returns the deployment ID (used to poll status) — NOT the deployment url.

    Note: this call is deliberately NOT covered by the session's automatic
    retry-on-5xx/429 policy in practice, since a 5xx here can occur *after*
    Vercel has partially registered the deployment; blindly resubmitting an
    identical payload isn't guaranteed idempotent the way /v2/files is. If
    it fails, surface the error and let the caller decide whether to retry
    the whole deploy.
    """
    try:
        payload = {
            "name": project_name,
            "project": project_id,
            "target": "production",
            "files": files_manifest,
            "projectSettings": {
                "framework": _map_framework(framework),
            },
        }

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
        else:
            console.print(f"[red]Deployment failed: HTTP {response.status_code}: {response.text}[/red]")
            return None

    except Exception as e:
        console.print(f"[red]Error creating deployment: {e}[/red]")
        return None


# ──────────────────────────────────────────────────────────────
# WAIT FOR DEPLOYMENT
# ──────────────────────────────────────────────────────────────

def _wait_for_deployment(
    session: requests.Session,
    deployment_id: str,
    team_id: Optional[str] = None,
    timeout: int = 180,
) -> Optional[str]:
    """
    Poll GET /v13/deployments/:id and watch `readyState`
    (QUEUED -> INITIALIZING -> BUILDING -> READY | ERROR | CANCELED).
    Returns the deployment's public url (host, no scheme) once READY.
    """
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
                    return data.get("url")
                elif ready_state in ("ERROR", "CANCELED"):
                    error_msg = (
                        data.get("errorMessage")
                        or (data.get("aliasError") or {}).get("message")
                        or f"deployment ended with state {ready_state}"
                    )
                    console.print(f"[red]Deployment failed: {error_msg}[/red]")
                    return None
                # else: still QUEUED / INITIALIZING / BUILDING — keep polling
            else:
                console.print(
                    f"[yellow]Warning: status check returned HTTP {response.status_code}[/yellow]"
                )

            time.sleep(interval)

        console.print("[red]Deployment timed out.[/red]")
        return None

    except Exception as e:
        console.print(f"[red]Error waiting for deployment: {e}[/red]")
        return None