"""
Render deployment for Opun8.

Handles:
    - Creating web services on Render
    - Deploying from GitHub repositories
    - Environment variable management
    - Deployment status polling
    - URL resolution
    - Interactive service name conflict resolution

NOTE: Render's public API has no endpoint for deploying from local files.
Every service must be backed by a connected Git repo or a prebuilt Docker
image. deploy_to_render() requires repo_url for this reason; the tarball
helpers below are unused dead code kept only for reference.

Error handling philosophy (matches vercel/deploy.py):
    - What the end user sees on screen is short, plain-English, and actionable
    - Technical detail goes to debug log (~/.opun8/debug.log)
    - Set OPUN8_DEBUG=1 to echo debug logs to terminal
"""

import os
import time
import tarfile
import tempfile
import threading
from pathlib import Path
from urllib.parse import quote
from typing import Optional, Dict, Any, List, Tuple, Union

import requests
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
    TimeElapsedColumn,
)

# ✅ FIX: Use the new env_service module instead of old functions
from opun8.services import env_service

from opun8.providers.render.models import (
    ServiceType,
    EnvType,
    Region,
    AutoDeploy,
    ServiceDetails,
    CreateServiceRequest,
    map_framework_to_render_env,
    get_default_build_command,
    get_default_start_command,
)

console = Console()
_console_lock = threading.Lock()

DEBUG_LOG_FILE = Path.home() / ".opun8" / "debug.log"

# API endpoints
RENDER_API_BASE = "https://api.render.com/v1"
RENDER_SERVICES_ENDPOINT = f"{RENDER_API_BASE}/services"
RENDER_ENV_VARS_ENDPOINT = f"{RENDER_API_BASE}/services/{{service_id}}/env-vars"

# Approximate stage weights (0-100) for the progress bar. Render doesn't
# expose a numeric build percentage, so this approximates progress based on
# which lifecycle stage the deploy is currently in.
DEPLOY_STAGE_WEIGHT = {
    "created": 5,
    "queued": 5,
    "pre_deploy_in_progress": 20,
    "build_in_progress": 55,
    "update_in_progress": 85,
    "live": 100,
}
DEPLOY_STAGE_LABEL = {
    "created": "🕐 Queued",
    "queued": "🕐 Queued",
    "pre_deploy_in_progress": "🔧 Running pre-deploy",
    "build_in_progress": "🔨 Building",
    "update_in_progress": "🚀 Starting service",
    "live": "✅ Live",
    "build_failed": "❌ Build failed",
    "update_failed": "❌ Start failed",
    "pre_deploy_failed": "❌ Pre-deploy failed",
    "canceled": "⏹️ Canceled",
    "deactivated": "⏹️ Deactivated",
}
DEPLOY_FAILURE_STATUSES = {
    "build_failed", "update_failed", "pre_deploy_failed", "canceled", "deactivated",
}

# File exclusions (same as Vercel)
EXCLUDE_DIR_NAMES = {
    "node_modules", ".git", "__pycache__", ".venv", "venv",
    ".pytest_cache", ".next", ".vercel", ".turbo",
    "dist", "build", "out", ".cache", "coverage",
    ".idea", ".vscode",
}
EXCLUDE_FILE_NAMES = {".DS_Store"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo", ".pyd", ".log", ".tmp"}

# Polling settings
DEPLOYMENT_POLL_INTERVAL = 3  # seconds
DEPLOYMENT_POLL_TIMEOUT = 300  # 5 minutes

# Maximum attempts for service name resolution
MAX_SERVICE_NAME_ATTEMPTS = 5


# ──────────────────────────────────────────────────────────────
# DEBUG LOGGING
# ──────────────────────────────────────────────────────────────

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


def _show_error(message: str, hint: Optional[str] = None, debug_detail: Optional[str] = None) -> None:
    """Show user-friendly error message (thread-safe)."""
    with _console_lock:
        console.print(f"[red]❌ {message}[/red]")
        if hint:
            console.print(f"[dim]{hint}[/dim]")
    if debug_detail:
        _debug_log(debug_detail)


def _console_print(*args, **kwargs) -> None:
    """Thread-safe console printing."""
    with _console_lock:
        console.print(*args, **kwargs)


# ──────────────────────────────────────────────────────────────
# HTTP HELPERS
# ──────────────────────────────────────────────────────────────

def _api_get(url: str, token: str, timeout: int = 30) -> Optional[Any]:
    """GET an authenticated Render API endpoint."""
    try:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        _debug_log(f"GET {url} network error: {e}")
        return None

    if response.status_code != 200:
        _debug_log(f"GET {url} HTTP {response.status_code}: {response.text[:500]}")
        return None

    try:
        return response.json()
    except ValueError as e:
        _debug_log(f"GET {url} response wasn't valid JSON: {e}")
        return None


def _api_post(
    url: str,
    token: str,
    data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Optional[Any]:
    """POST to an authenticated Render API endpoint."""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        if files:
            response = requests.post(
                url,
                headers=headers,
                files=files,
                data=data,
                timeout=timeout,
            )
        else:
            headers["Content-Type"] = "application/json"
            response = requests.post(
                url,
                headers=headers,
                json=data or {},
                timeout=timeout,
            )
    except requests.RequestException as e:
        _debug_log(f"POST {url} network error: {e}")
        return None

    if response.status_code not in (200, 201, 202):
        _debug_log(f"POST {url} HTTP {response.status_code}: {response.text[:500]}")
        return None

    try:
        return response.json()
    except ValueError as e:
        _debug_log(f"POST {url} response wasn't valid JSON: {e}")
        return None


def _api_post_raw(
    url: str,
    token: str,
    data: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Tuple[Optional[int], Optional[Any], str]:
    """
    POST to an authenticated Render API endpoint, surfacing the raw status
    code and body instead of collapsing every failure into None.

    Returns (status_code, parsed_json_or_None, raw_text). status_code is
    None only on a network-level failure (no response received at all).
    """
    try:
        response = requests.post(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=data or {},
            timeout=timeout,
        )
    except requests.RequestException as e:
        _debug_log(f"POST {url} network error: {e}")
        return None, None, ""

    if response.status_code not in (200, 201, 202):
        _debug_log(f"POST {url} HTTP {response.status_code}: {response.text[:500]}")

    try:
        return response.status_code, response.json(), response.text
    except ValueError:
        return response.status_code, None, response.text


def _api_patch(url: str, token: str, data: Dict[str, Any], timeout: int = 30) -> Optional[Any]:
    """PATCH an authenticated Render API endpoint."""
    try:
        response = requests.patch(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=data,
            timeout=timeout,
        )
    except requests.RequestException as e:
        _debug_log(f"PATCH {url} network error: {e}")
        return None

    if response.status_code != 200:
        _debug_log(f"PATCH {url} HTTP {response.status_code}: {response.text[:500]}")
        return None

    try:
        return response.json()
    except ValueError as e:
        _debug_log(f"PATCH {url} response wasn't valid JSON: {e}")
        return None


def _api_delete(url: str, token: str, timeout: int = 30) -> bool:
    """DELETE an authenticated Render API endpoint."""
    try:
        response = requests.delete(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
    except requests.RequestException as e:
        _debug_log(f"DELETE {url} network error: {e}")
        return False

    if response.status_code not in (200, 204):
        _debug_log(f"DELETE {url} HTTP {response.status_code}: {response.text[:500]}")
        return False

    return True


# ──────────────────────────────────────────────────────────────
# ENVIRONMENT VARIABLES  ✅ FIXED
# ──────────────────────────────────────────────────────────────

def _set_env_vars(
    token: str,
    service_id: str,
    env_vars: Dict[str, str],
) -> bool:
    """
    Set environment variables on a Render service.
    
    Args:
        token: Render API token
        service_id: Service ID
        env_vars: Dictionary of environment variables
        
    Returns:
        True if successful, False otherwise.
    """
    if not env_vars:
        return True
    
    url = RENDER_ENV_VARS_ENDPOINT.format(service_id=service_id)
    
    payload = {
        "envVars": [
            {"key": key, "value": value}
            for key, value in env_vars.items()
        ]
    }
    
    result = _api_post(url, token, payload)
    if result is None:
        _debug_log(f"_set_env_vars: API call failed")
        return False
    
    _console_print(f"[dim]✅ Set {len(env_vars)} environment variable(s) on Render[/dim]")
    return True


# ──────────────────────────────────────────────────────────────
# PROMPT FOR ENV VARS  ✅ FIXED
# ──────────────────────────────────────────────────────────────

def _prompt_for_env_vars(project_path: Path) -> Dict[str, str]:
    """
    Prompt the user for environment variables using the centralized service.
    
    ✅ FIX: Uses the new env_service.prompt_for_env_vars() which includes:
        - Source code scanning for env var usage
        - Framework-specific detection
        - Interactive selection with checkbox UI
        - Sensitive value redaction

    Args:
        project_path: Path to the project root
        
    Returns:
        Dictionary of selected environment variables
    """
    env_vars, _ = env_service.prompt_for_env_vars(project_path)
    return env_vars


# ──────────────────────────────────────────────────────────────
# GET DEFAULT PUBLISH PATH
# ──────────────────────────────────────────────────────────────

def _get_default_publish_path(framework: Optional[str]) -> Optional[str]:
    """
    Get the default publish directory for a static site based on framework.
    """
    if not framework:
        return None

    framework_lower = framework.lower()
    
    mapping = {
        "react": "build",
        "next": "out",
        "nextjs": "out",
        "vue": "dist",
        "vite": "dist",
        "angular": "dist",
        "svelte": "public",
        "sveltekit": "build",
        "astro": "dist",
        "static": ".",
        "html": ".",
    }
    
    return mapping.get(framework_lower)


# ──────────────────────────────────────────────────────────────
# SERVICE NAME CONFLICT RESOLUTION
# ──────────────────────────────────────────────────────────────

def _list_all_services(
    token: str,
    owner_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Fetch all services visible to this token, following Render's pagination.
    """
    services: List[Dict[str, Any]] = []
    page = 1
    per_page = 100

    while True:
        url = f"{RENDER_SERVICES_ENDPOINT}?limit={per_page}&page={page}"
        if owner_id:
            url += f"&ownerId={owner_id}"

        result = _api_get(url, token)
        if result is None:
            break

        items = result if isinstance(result, list) else (result or {}).get("items") or (result or {}).get("services") or []
        if not items:
            break

        for item in items:
            if isinstance(item, dict):
                service = item.get("service", item)
                if isinstance(service, dict) and service.get("id"):
                    services.append(service)

        if len(items) < per_page:
            break

        page += 1

    return services


def _find_service_by_name(
    token: str,
    name: str,
    owner_id: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Look up a Render service by exact name, optionally scoped to an owner/workspace.
    """
    services = _list_all_services(token, owner_id)
    for service in services:
        if service.get("name") == name:
            return service
    return None


def _resolve_service_name_conflict(
    session_token: str,
    original_name: str,
    owner_id: Optional[str] = None,
    original_base: Optional[str] = None,
    attempt: int = 1,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Interactive service name conflict resolution for Render.

    Returns:
        (service_id, resolved_name) on success
        (None, None) on cancellation
        (None, resolved_name) if name is available
    """
    if original_base is None:
        original_base = original_name

    if attempt > MAX_SERVICE_NAME_ATTEMPTS:
        _show_error(
            f"Could not find an available service name after {MAX_SERVICE_NAME_ATTEMPTS} attempts.",
            hint="Please choose a different name and try again.",
        )
        return None, None

    existing = _find_service_by_name(session_token, original_name, owner_id)

    if existing:
        service_id = existing.get("id")
        service_name = existing.get("name", original_name)
        service_url = existing.get("url") or f"https://{service_name}.onrender.com"
        service_status = existing.get("status", "unknown")

        _debug_log(f"Service name '{original_name}' already exists. Prompting user...")

        console.print()
        console.print(Panel(
            f"[bold yellow]⚠️ Service Name Conflict[/bold yellow]\n\n"
            f"The service name [cyan]{original_name}[/cyan] already exists on Render.\n"
            f"This could be your own service or someone else's.\n\n"
            f"[dim]Existing service:[/dim]\n"
            f"  • Name: [white]{service_name}[/white]\n"
            f"  • URL: [cyan]{service_url}[/cyan]\n"
            f"  • Status: [dim]{service_status}[/dim]",
            border_style="yellow",
            padding=(1, 2),
        ))
        console.print()

        services = _list_all_services(session_token, owner_id)
        if services:
            console.print("[dim]Here are the services in your Render account:[/dim]")
            console.print()
            for i, svc in enumerate(services[:10], 1):
                name = svc.get("name", "Unnamed")
                url = svc.get("url") or f"https://{name}.onrender.com"
                status = svc.get("status", "unknown")
                console.print(f"  [bold cyan]{i}[/]  [white]{name}[/white]  [dim]{url} ({status})[/dim]")
            if len(services) > 10:
                console.print(f"  [dim]... and {len(services) - 10} more[/dim]")
        else:
            console.print("[dim]No other services found in your account.[/dim]")

        console.print()
        console.print("[bold]What would you like to do?[/bold]")
        console.print()
        console.print("  [bold cyan]1[/]  [white]Use the existing service[/white]  [dim](redeploy to it)[/dim]")
        console.print("  [bold cyan]2[/]  [white]Enter a new service name[/white]")
        console.print("  [bold cyan]3[/]  [yellow]Cancel deployment[/yellow]")
        console.print()

        choice = Prompt.ask(
            "[bold cyan]➜[/] Select an option",
            choices=["1", "2", "3"],
            default="1",
            show_choices=False,
        )

        if choice == "3":
            return None, None

        if choice == "1":
            console.print(f"[green]✅ Using existing service: {service_name}[/green]")
            return service_id, service_name

        if choice == "2":
            console.print()
            new_name = Prompt.ask(
                "[bold cyan]➜[/] Enter a new service name",
                default=f"{original_base}-{attempt + 1}",
                show_default=True,
            )

            if not new_name or new_name.strip() == "":
                console.print("[yellow]No name provided. Cancelling.[/yellow]")
                return None, None

            new_name = new_name.lower().replace(" ", "-")
            new_name = ''.join(c for c in new_name if c.isalnum() or c in '-_')
            new_name = new_name.strip('-')

            if not new_name:
                console.print("[yellow]Invalid name. Cancelling.[/yellow]")
                return None, None

            console.print(f"[dim]Trying: {new_name}[/dim]")

            return _resolve_service_name_conflict(
                session_token,
                new_name,
                owner_id,
                original_base,
                attempt + 1
            )

        return None, None

    # No conflict - name is available
    return None, original_name


# ──────────────────────────────────────────────────────────────
# MAIN DEPLOY FUNCTION
# ──────────────────────────────────────────────────────────────

def deploy_to_render(
    token: str,
    project_name: str,
    project_path: Path,
    framework: Optional[str] = None,
    env_vars: Optional[Dict[str, str]] = None,
    owner_id: Optional[str] = None,
    repo_url: Optional[str] = None,
    region: str = "oregon",
    output_dir: str = ".",
) -> Tuple[bool, str, Optional[str]]:
    """
    Deploy a project to Render.

    ✅ FIX: Uses new env_service for interactive env var prompting.

    Args:
        token: Render API token or API key
        project_name: Name of the project/service
        project_path: Local project path
        framework: Optional framework name for detection
        env_vars: Optional environment variables dict
        owner_id: Optional owner/workspace ID (defaults to personal account)
        repo_url: Optional GitHub repository URL (if deploying from GitHub)
        region: Render region (oregon, frankfurt, singapore, ohio, virginia)
        output_dir: Optional output directory for local file deployment

    Returns:
        (success, url_or_message, service_id)
    """
    project_path = Path(project_path)
    if not project_path.exists() or not project_path.is_dir():
        return False, f"We couldn't find the project folder: {project_path}", None

    # Render requires a GitHub repo
    if not repo_url:
        return (
            False,
            "Render doesn't support deploying from local files. It only deploys from a "
            "connected GitHub, GitLab, or Bitbucket repository (or a prebuilt Docker image). "
            "Push this project to GitHub, then run 'opun8 deploy' again and choose "
            "'Deploy this project (with GitHub)'.",
            None,
        )

    # Validate region
    region_enum = None
    for r in Region:
        if r.value == region.lower():
            region_enum = r
            break
    
    if region_enum is None:
        _console_print(f"[yellow]⚠️ Unknown region '{region}', using default: oregon[/yellow]")
        region_enum = Region.OREGON

    # ✅ FIX: Detect env vars using the new env_service
    if env_vars is None:
        env_vars = _prompt_for_env_vars(project_path)

    _console_print()
    _console_print("[bold cyan]☁️ Deploying to Render...[/bold cyan]")
    _console_print(f"[dim]Project: {project_name}[/dim]")
    _console_print(f"[dim]Path: {project_path}[/dim]")
    _console_print(f"[dim]Region: {region_enum.value}[/dim]")
    if repo_url:
        _console_print(f"[dim]Repo: {repo_url}[/dim]")
    _console_print()

    # Map framework
    env_type = map_framework_to_render_env(framework)
    if env_type is None:
        env_type = EnvType.NODE
        _console_print(f"[dim]ℹ️  Using default environment: {env_type.value}[/dim]")

    is_static = env_type == EnvType.STATIC
    service_type = ServiceType.STATIC_SITE if is_static else ServiceType.WEB_SERVICE

    # Build commands
    build_command = get_default_build_command(env_type, framework)
    start_command = get_default_start_command(env_type, framework)
    publish_path = _get_default_publish_path(framework) if is_static else None

    service_details = ServiceDetails(
        build_command=build_command,
        start_command=start_command,
        publish_path=publish_path,
    )

    # Determine owner_id
    final_owner_id = owner_id
    if not final_owner_id:
        from opun8.providers.render.auth import get_render_owner_id
        final_owner_id = get_render_owner_id()
        if not final_owner_id:
            _console_print("[yellow]⚠️ No owner/workspace specified. Using personal account.[/yellow]")
            final_owner_id = None

    # Check for service name conflict BEFORE creating
    _console_print("[dim]🔍 Checking for existing service...[/dim]")
    
    resolved_id, resolved_name = _resolve_service_name_conflict(
        token,
        project_name,
        final_owner_id,
        project_name,
        1
    )

    # Handle different resolution outcomes
    if resolved_id is not None:
        # User chose to use existing service
        project_name = resolved_name or project_name
        _console_print(f"[green]✅ Using existing service: {project_name}[/green]")
        return _update_and_redeploy_existing(
            token,
            resolved_id,
            project_name,
            final_owner_id
        )

    # Name is available or user provided a new one
    if resolved_name is not None and resolved_name != project_name:
        project_name = resolved_name
        _console_print(f"[dim]Using service name: [cyan]{project_name}[/dim]")

    # Create the service
    create_request = CreateServiceRequest(
        name=project_name,
        owner_id=final_owner_id or "",
        type=service_type,
        env=env_type,
        repo=repo_url,
        branch="main",
        auto_deploy=AutoDeploy.YES if repo_url else AutoDeploy.NO,
        service_details=service_details,
    )

    payload = create_request.to_api_payload()
    
    if region_enum and not is_static:
        payload["region"] = region_enum.value

    # Deploy
    success, url, service_id = _deploy_from_github(
        token, payload, project_name, project_path, final_owner_id
    )
    
    # ✅ FIX: Check env var result
    if success and service_id and env_vars:
        if not _set_env_vars(token, service_id, env_vars):
            console.print("[yellow]⚠️ Some environment variables couldn't be set. "
                          "Check the Render dashboard to verify.[/yellow]")
    
    return success, url, service_id


def _is_name_conflict(result: Optional[Any], raw_text: str) -> bool:
    """Detect Render's 'name: (x) already in use' error."""
    message = ""
    if isinstance(result, dict):
        message = str(result.get("message", ""))
    if not message:
        message = raw_text or ""
    message = message.lower()
    return "already in use" in message and "name" in message


def _trigger_redeploy(token: str, service_id: str) -> Optional[str]:
    """Trigger a fresh deploy on an existing service. Returns the new deploy ID."""
    result = _api_post(f"{RENDER_SERVICES_ENDPOINT}/{service_id}/deploys", token, data={})
    if result is None:
        return None
    deploy_data = result.get("deploy", result) if isinstance(result, dict) else None
    return deploy_data.get("id") if isinstance(deploy_data, dict) else None


def _update_and_redeploy_existing(
    token: str,
    service_id: str,
    service_name: str,
    owner_id: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Update and redeploy an existing service.
    
    ✅ FIX: service_id is the actual Render service ID.
    
    Args:
        token: Render API token
        service_id: Existing service ID (real ID, not name)
        service_name: Service name
        owner_id: Optional owner ID
        
    Returns:
        (success, url_or_message, service_id)
    """
    _console_print(f"[dim]🔄 Redeploying existing service: {service_name}[/dim]")
    _console_print(f"[dim]Service ID: {service_id}[/dim]")

    deploy_id = _trigger_redeploy(token, service_id)
    if deploy_id is None:
        return (
            False,
            f"Found the existing '{service_name}' service but couldn't start a new deploy. "
            "Try again, or trigger a manual deploy from the Render dashboard.",
            service_id,
        )

    return _wait_for_deployment(token, service_id, service_name, deploy_id=deploy_id)


def _deploy_from_github(
    token: str,
    payload: Dict[str, Any],
    project_name: str,
    project_path: Path,
    owner_id: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Deploy a project from a GitHub repository.

    If a service with this name already exists, we look it up and redeploy
    instead of failing.
    """
    _console_print("[dim]📦 Deploying from GitHub repository...[/dim]")

    # Create the service
    status_code, result, raw_text = _api_post_raw(RENDER_SERVICES_ENDPOINT, token, data=payload)

    if status_code == 400 and _is_name_conflict(result, raw_text):
        # ✅ FIX: Look up the actual service ID by name
        service_name = payload.get("name")
        existing = _find_service_by_name(token, service_name, owner_id)
        
        if existing and existing.get("id"):
            _console_print(
                f"[yellow]ℹ️  A service named '{service_name}' already exists on Render "
                f"-- redeploying to it instead of creating a new one.[/yellow]"
            )
            return _update_and_redeploy_existing(
                token,
                existing["id"],
                service_name,
                owner_id
            )
        else:
            _console_print(
                f"[red]❌ A service named '{service_name}' already exists but we "
                f"couldn't find it to redeploy. Please use the Render dashboard.[/red]"
            )
            return False, f"Service '{service_name}' already exists and couldn't be located.", None

    if status_code is None or status_code not in (200, 201, 202) or result is None:
        return False, "Failed to create Render service. Please try again.", None

    try:
        service_data = result.get("service", result)
        service_id = service_data.get("id")

        deploy_data = result.get("deploy") or {}
        deploy_id = deploy_data.get("id")

        if not service_id:
            _debug_log(f"Service creation response missing ID: {result}")
            return False, "Couldn't get service ID from Render.", None

        service_name = service_data.get("name", project_name)

        _console_print(f"[green]✅ Service created: {service_name}[/green]")
        _console_print(f"[dim]Service ID: {service_id}[/dim]")

        return _wait_for_deployment(token, service_id, service_name, deploy_id=deploy_id)

    except Exception as e:
        _debug_log(f"Service creation error: {e}")
        return False, f"Service creation error: {e}", None


def _deploy_from_local(
    token: str,
    payload: Dict[str, Any],
    project_name: str,
    project_path: Path,
    env_vars: Optional[Dict[str, str]] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Deploy a project from local files (tarball upload).
    """
    _console_print("[dim]📦 Preparing local files for deployment...[/dim]")

    tarball_path = None
    
    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=False,
        ) as progress:
            task = progress.add_task("[cyan]📦 Creating deployment package...", total=None)
            tarball_path = _create_tarball(project_path)
            progress.update(task, description="[green]✅ Package created")

        result = _api_post(RENDER_SERVICES_ENDPOINT, token, data=payload)
        if result is None:
            return False, "Failed to create Render service. Please try again.", None

        service_data = result.get("service", result)
        service_id = service_data.get("id")

        if not service_id:
            _debug_log(f"Service creation response missing ID: {result}")
            return False, "Couldn't get service ID from Render.", None

        service_name = service_data.get("name", project_name)

        _console_print(f"[green]✅ Service created: {service_name}[/green]")
        _console_print(f"[dim]Service ID: {service_id}[/dim]")

        _console_print("[dim]📤 Uploading project files...[/dim]")

        upload_url = f"{RENDER_SERVICES_ENDPOINT}/{service_id}/deploy"
        
        with open(tarball_path, "rb") as f:
            files = {"file": (f"{project_name}.tar.gz", f, "application/gzip")}
            upload_result = _api_post(
                upload_url,
                token,
                files=files,
                data={"branch": "main"},
            )

        if upload_result is None:
            return False, "Failed to upload project files. Please try again.", service_id

        return _wait_for_deployment(token, service_id, service_name)

    except Exception as e:
        _debug_log(f"Local deployment error: {e}")
        return False, f"Deployment error: {e}", None
    finally:
        if tarball_path and os.path.exists(tarball_path):
            try:
                os.unlink(tarball_path)
            except Exception:
                pass


def _create_tarball(project_path: Path) -> str:
    """Create a tarball of the project for upload to Render."""
    temp_file = tempfile.NamedTemporaryFile(
        suffix=".tar.gz",
        prefix="opun8_render_",
        delete=False,
    )
    tarball_path = temp_file.name
    temp_file.close()

    def should_exclude(path: str) -> bool:
        parts = Path(path).parts
        for part in parts:
            if part in EXCLUDE_DIR_NAMES:
                return True
        name = Path(path).name
        if name in EXCLUDE_FILE_NAMES:
            return True
        if Path(path).suffix in EXCLUDE_SUFFIXES:
            return True
        return False

    with tarfile.open(tarball_path, "w:gz") as tar:
        for file_path in project_path.rglob("*"):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(project_path)
            if should_exclude(str(rel_path)):
                continue
            tar.add(file_path, arcname=rel_path)

    return tarball_path


def _wait_for_deployment(
    token: str,
    service_id: str,
    service_name: str,
    deploy_id: Optional[str] = None,
) -> Tuple[bool, str, Optional[str]]:
    """
    Wait for a deployment to complete and return the URL.

    Polls GET /services/{serviceId}/deploys/{deployId} directly when
    deploy_id is available. As a fallback, lists deploys and takes the
    most recent.
    """
    _console_print()
    _console_print("[dim]⏳ Waiting for deployment to complete...[/dim]")
    _console_print(f"[dim]Timeout: {DEPLOYMENT_POLL_TIMEOUT}s[/dim]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=30),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
        transient=False,
    ) as progress:
        task = progress.add_task("[cyan]🕐 Queued[/cyan]", total=100, completed=2)

        start_time = time.time()
        last_status = None
        consecutive_lookup_failures = 0

        while time.time() - start_time < DEPLOYMENT_POLL_TIMEOUT:
            if deploy_id:
                deploy_data = _api_get(
                    f"{RENDER_SERVICES_ENDPOINT}/{service_id}/deploys/{deploy_id}",
                    token,
                )
            else:
                deploys = _api_get(f"{RENDER_SERVICES_ENDPOINT}/{service_id}/deploys", token)
                deploy_list = deploys if isinstance(deploys, list) else (deploys or {}).get("deploys", [])
                deploy_list = [d.get("deploy", d) if isinstance(d, dict) else d for d in deploy_list]
                deploy_data = deploy_list[0] if deploy_list else None
                if deploy_data:
                    deploy_id = deploy_data.get("id")

            if deploy_data is None:
                consecutive_lookup_failures += 1
                if consecutive_lookup_failures >= 5:
                    progress.update(task, description="[red]❌ Failed to check deployment status[/red]")
                    return False, "Failed to check deployment status. Please check Render dashboard.", service_id
                time.sleep(DEPLOYMENT_POLL_INTERVAL)
                continue
            consecutive_lookup_failures = 0

            deploy_status = deploy_data.get("status", "unknown")

            if deploy_status != last_status:
                last_status = deploy_status
                label = DEPLOY_STAGE_LABEL.get(deploy_status, f"📊 {deploy_status}")
                weight = DEPLOY_STAGE_WEIGHT.get(deploy_status, progress.tasks[task].completed)
                progress.update(task, completed=weight, description=f"[cyan]{label}[/cyan]")

            if deploy_status == "live":
                service_data = _api_get(f"{RENDER_SERVICES_ENDPOINT}/{service_id}", token)
                
                url = None
                if service_data:
                    service_details = service_data.get("serviceDetails") or {}
                    url = service_details.get("url")
                if not url and deploy_data:
                    deploy_details = deploy_data.get("serviceDetails") or {}
                    url = deploy_details.get("url") or deploy_data.get("url")
                if not url and service_data and service_data.get("slug"):
                    url = f"https://{service_data['slug']}.onrender.com"
                    _debug_log(f"Using slug-based URL: {url}")
                if not url:
                    url = f"https://{service_name}.onrender.com"
                    _debug_log(
                        f"Couldn't find URL in serviceDetails/slug for {service_id}; "
                        f"using name-based fallback: {url}"
                    )

                progress.update(task, completed=100, description="[green]✅ Live![/green]")
                _console_print()
                _console_print("[bold green]✅ Deployment successful![/bold green]")
                if url:
                    _console_print(f"[dim]🌐 {url}[/dim]")
                return True, url, service_id

            if deploy_status in DEPLOY_FAILURE_STATUSES or "fail" in deploy_status:
                label = DEPLOY_STAGE_LABEL.get(deploy_status, deploy_status)
                progress.update(task, description=f"[red]{label}[/red]")
                return (
                    False,
                    f"Deployment failed ({deploy_status}). Check the Render dashboard's "
                    "deploy logs for the exact build error.",
                    service_id,
                )

            time.sleep(DEPLOYMENT_POLL_INTERVAL)

        progress.update(task, description="[red]❌ Deployment timed out[/red]")
        return False, "Deployment timed out. Please check Render dashboard.", service_id


# ──────────────────────────────────────────────────────────────
# PUBLIC API FUNCTIONS
# ──────────────────────────────────────────────────────────────

def get_render_service_status(
    token: str,
    service_id: str,
) -> Optional[Dict[str, Any]]:
    """Get the status of a Render service."""
    return _api_get(f"{RENDER_SERVICES_ENDPOINT}/{service_id}", token)


def delete_render_service(
    token: str,
    service_id: str,
) -> bool:
    """Delete a Render service."""
    return _api_delete(f"{RENDER_SERVICES_ENDPOINT}/{service_id}", token)


def list_render_services(
    token: str,
    owner_id: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    List all Render services for the user with pagination.
    
    ✅ FIX: Unwraps item["service"] correctly.
    ✅ FIX: Uses camelCase keys (createdAt, updatedAt, ownerId).
    ✅ FIX: Paginates through all services.
    """
    all_services: List[Dict[str, Any]] = []
    page = 1
    per_page = 100

    while True:
        url = RENDER_SERVICES_ENDPOINT
        if owner_id:
            url = f"{url}?ownerId={owner_id}"
        url += f"&limit={per_page}&page={page}"

        raw = _api_get(url, token)
        if raw is None:
            break

        # Handle different response formats
        items = raw if isinstance(raw, list) else (raw or {}).get("items") or (raw or {}).get("services") or []
        if not items:
            break

        for item in items:
            if isinstance(item, dict):
                # ✅ FIX: Unwrap the service from the wrapper
                service = item.get("service", item)
                if isinstance(service, dict) and service.get("id"):
                    # ✅ FIX: Use camelCase keys
                    all_services.append({
                        "id": service.get("id", "Unknown"),
                        "name": service.get("name", "Unknown"),
                        "type": service.get("type", "unknown"),
                        "status": service.get("status", "unknown"),
                        "url": service.get("url", None),
                        "repo": service.get("repo", None),
                        "env": service.get("env", None),
                        "region": service.get("region", None),
                        "created_at": service.get("createdAt", None),
                        "updated_at": service.get("updatedAt", None),
                        "owner_id": service.get("ownerId", None),
                    })

        if len(items) < per_page:
            break
        page += 1

    return all_services if all_services else None


def get_render_deployment_logs(
    token: str,
    service_id: str,
    deployment_id: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Get deployment logs from Render."""
    if deployment_id:
        url = f"{RENDER_SERVICES_ENDPOINT}/{service_id}/deployments/{deployment_id}/logs"
    else:
        url = f"{RENDER_SERVICES_ENDPOINT}/{service_id}/logs"

    return _api_get(url, token)