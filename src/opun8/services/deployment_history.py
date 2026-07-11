"""
Deployment history service for Opun8.
Stores and retrieves deployment history locally.
Cross-platform file locking support (Unix fcntl + Windows msvcrt).
"""

import json
import os
import tempfile
import uuid
import contextlib
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from rich.console import Console

console = Console()

# ──────────────────────────────────────────────────────────────
# FILE LOCATION
# ──────────────────────────────────────────────────────────────

HISTORY_DIR = Path.home() / ".opun8"
HISTORY_FILE = HISTORY_DIR / "deployment_history.json"
LOCK_FILE = HISTORY_DIR / "deployment_history.lock"


# ──────────────────────────────────────────────────────────────
# CROSS-PLATFORM FILE LOCKING
# ──────────────────────────────────────────────────────────────

try:
    import fcntl
    HAS_FCNTL = True
except ImportError:
    HAS_FCNTL = False

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False


@contextlib.contextmanager
def _locked():
    """
    Hold an exclusive advisory lock across the read-modify-write cycle so
    two concurrent invocations of opun8 can't clobber each other's writes.

    Supports:
        - Unix/Linux: fcntl.flock()
        - Windows: msvcrt.locking()
        - Fallback: no locking (warning printed once)
    """
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)

    # Check if locking is available
    if not HAS_FCNTL and not HAS_MSVCRT:
        console.print("[yellow]⚠️  No file locking available. Concurrent writes may cause issues.[/yellow]")
        yield
        return

    lock_fd = open(LOCK_FILE, "w")
    try:
        if HAS_FCNTL:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
        elif HAS_MSVCRT:
            msvcrt.locking(lock_fd.fileno(), msvcrt.LK_LOCK, 1)
        yield
    finally:
        try:
            if HAS_FCNTL:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            elif HAS_MSVCRT:
                msvcrt.locking(lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
        except Exception:
            pass  # Best effort
        lock_fd.close()


# ──────────────────────────────────────────────────────────────
# DATA STRUCTURES
# ──────────────────────────────────────────────────────────────

def _get_default_history() -> Dict[str, Any]:
    """Return the default history structure."""
    return {
        "deployments": [],
        "total_count": 0,
        "badges": {
            "unlocked": [],
            "current_level": 0,
        },
    }


class HistoryReadError(Exception):
    """Raised when the history file cannot be read and it is not safe to
    silently fall back to a fresh/default history (data would be lost)."""


# ──────────────────────────────────────────────────────────────
# FILE I/O
# ──────────────────────────────────────────────────────────────

def _ensure_history_file() -> None:
    """Ensure the history file exists with proper structure."""
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    if not HISTORY_FILE.exists():
        _write_history(_get_default_history())


def _new_deployment_id(existing_ids: set) -> str:
    """Generate a short deployment ID that doesn't collide with existing ones."""
    for _ in range(10):
        candidate = uuid.uuid4().hex[:12]
        if candidate not in existing_ids:
            return candidate
    # Exceedingly unlikely fallback: use the full UUID.
    return str(uuid.uuid4())


def _heal_missing_ids(data: Dict[str, Any]) -> bool:
    """
    Assign an id to any deployment record that doesn't have one.

    History entries created before the "id" field existed (or written by
    some future/older version of opun8) have no "id" key at all. Every
    lookup used by delete/update/redeploy matches on
    ``deployment.get("id")``, so a record with a falsy id can never be
    matched — delete in particular fails silently and permanently for
    that entry. This repairs such records in place the first time they're
    read.

    Returns:
        True if any record was modified (caller should persist the file).
    """
    existing_ids = {d.get("id") for d in data["deployments"] if d.get("id")}
    healed = False
    for deployment in data["deployments"]:
        if not deployment.get("id"):
            new_id = _new_deployment_id(existing_ids)
            deployment["id"] = new_id
            existing_ids.add(new_id)
            healed = True
    return healed


def _read_history() -> Dict[str, Any]:
    """
    Read the history file and return the data.

    Only a genuinely corrupt/malformed file is treated as "start fresh".
    Any other error (permissions, transient I/O issues, etc.) is raised
    rather than silently swallowed, since swallowing it would cause the
    next write to overwrite real history with an empty default.
    """
    _ensure_history_file()

    try:
        with open(HISTORY_FILE, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        console.print(
            "[yellow]⚠️  History file was corrupted (invalid JSON). "
            "Backing up and resetting...[/yellow]"
        )
        _backup_corrupted_file()
        default = _get_default_history()
        _write_history(default)
        return default
    except OSError as e:
        # Permissions, disk, or other I/O problems: do NOT reset history.
        raise HistoryReadError(f"Could not read history file: {e}") from e

    if not isinstance(data, dict) or "deployments" not in data:
        console.print(
            "[yellow]⚠️  History file had an unexpected structure. "
            "Backing up and resetting...[/yellow]"
        )
        _backup_corrupted_file()
        default = _get_default_history()
        _write_history(default)
        return default

    # Fill in any missing keys from older versions of the file rather than
    # discarding existing data.
    default = _get_default_history()
    data.setdefault("deployments", default["deployments"])
    data.setdefault("total_count", len(data["deployments"]))
    data.setdefault("badges", default["badges"])
    data["badges"].setdefault("unlocked", [])
    data["badges"].setdefault("current_level", 0)

    # Repair any legacy per-record fields (currently: missing "id").
    if _heal_missing_ids(data):
        _write_history(data)

    return data


def _backup_corrupted_file() -> None:
    """Copy an unreadable/corrupt history file aside instead of losing it."""
    if not HISTORY_FILE.exists():
        return
    backup_path = HISTORY_FILE.with_suffix(
        f".corrupted.{datetime.now().strftime('%Y%m%d%H%M%S')}.json"
    )
    try:
        backup_path.write_bytes(HISTORY_FILE.read_bytes())
        console.print(f"[yellow]   Backed up to {backup_path}[/yellow]")
    except OSError as e:
        console.print(f"[red]   Could not back up corrupted file: {e}[/red]")


def _write_history(data: Dict[str, Any]) -> None:
    """
    Atomically write data to the history file.

    Writes to a temp file in the same directory, then uses os.replace()
    so a crash or interrupt mid-write can never leave a truncated/corrupt
    history file on disk.
    """
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    try:
        fd, tmp_path = tempfile.mkstemp(
            dir=HISTORY_DIR, prefix=".deployment_history_", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, HISTORY_FILE)
        except BaseException:
            # Clean up the temp file if something went wrong before replace.
            with contextlib.suppress(OSError):
                os.remove(tmp_path)
            raise
    except OSError as e:
        console.print(f"[red]Error writing history file: {e}[/red]")


# ──────────────────────────────────────────────────────────────
# PUBLIC FUNCTIONS
# ──────────────────────────────────────────────────────────────

def get_deployment_history() -> List[Dict[str, Any]]:
    """
    Get all deployments from history.

    Returns:
        List of deployment records, newest first.
    """
    with _locked():
        data = _read_history()
    return data.get("deployments", [])


def add_deployment(
    project_name: str,
    url: str,
    platform: str,
    project_id: Optional[str] = None,
    team_id: Optional[str] = None,
    env_vars: Optional[List[str]] = None,
    project_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Add a new deployment to history.

    Args:
        project_name: Name of the project
        url: Deployment URL
        platform: Platform name (vercel, netlify, render)
        project_id: Platform project ID
        team_id: Team ID (if applicable)
        env_vars: List of environment variable names
        project_path: Absolute path to the local project folder this
            deployment was created from. Recorded so that a later
            "redeploy" can offer to reuse this exact folder instead of
            silently assuming the current working directory.

    Returns:
        The created deployment record, with a "badge_unlocked" key set to
        the newly unlocked badge info (or None if no new badge).
    """
    if not project_name or not project_name.strip():
        raise ValueError("project_name must be a non-empty string")
    if not url or not url.strip():
        raise ValueError("url must be a non-empty string")
    if not platform or not platform.strip():
        raise ValueError("platform must be a non-empty string")

    with _locked():
        data = _read_history()
        existing_ids = {d.get("id") for d in data["deployments"]}

        deployment_id = _new_deployment_id(existing_ids)
        old_count = data["total_count"]

        deployment = {
            "id": deployment_id,
            "project_name": project_name,
            "url": url,
            "platform": platform,
            "project_id": project_id,
            "team_id": team_id,
            "project_path": project_path,
            "env_vars": env_vars or [],
            "timestamp": datetime.now().isoformat(),
            "status": "success",
        }

        data["deployments"].insert(0, deployment)  # Newest first
        new_count = len(data["deployments"])
        data["total_count"] = new_count

        new_level = _calculate_badge_level(new_count)
        old_level = data["badges"].get("current_level", 0)
        if new_level > old_level:
            data["badges"]["current_level"] = new_level
            badge_name = get_badge_info(new_count)["name"]
            if badge_name not in data["badges"]["unlocked"]:
                data["badges"]["unlocked"].append(badge_name)

        _write_history(data)

    badge_unlocked = check_badge_progress(old_count, new_count)
    result = dict(deployment)
    result["badge_unlocked"] = badge_unlocked
    return result


def get_deployment(deployment_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific deployment by ID.

    Args:
        deployment_id: The deployment ID

    Returns:
        The deployment record, or None if not found.
    """
    if not deployment_id:
        return None
    for deployment in get_deployment_history():
        if deployment.get("id") == deployment_id:
            return deployment
    return None


def delete_deployment(deployment_id: str) -> bool:
    """
    Delete a deployment from history.

    Args:
        deployment_id: The deployment ID

    Returns:
        True if deleted, False if not found.
    """
    if not deployment_id:
        return False

    with _locked():
        data = _read_history()
        original_count = len(data["deployments"])
        data["deployments"] = [
            d for d in data["deployments"] if d.get("id") != deployment_id
        ]

        if len(data["deployments"]) == original_count:
            return False

        data["total_count"] = len(data["deployments"])
        data["badges"]["current_level"] = _calculate_badge_level(data["total_count"])
        _write_history(data)
        return True


def update_deployment(deployment_id: str, updates: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Update a deployment record.

    Args:
        deployment_id: The deployment ID
        updates: Dictionary of fields to update

    Returns:
        The updated deployment record, or None if not found.
    """
    if not deployment_id:
        return None

    with _locked():
        data = _read_history()
        for deployment in data["deployments"]:
            if deployment.get("id") == deployment_id:
                deployment.update(updates)
                _write_history(data)
                return deployment
    return None


def get_deployment_count() -> int:
    """
    Get the total number of deployments.

    Returns:
        Total deployment count.
    """
    with _locked():
        data = _read_history()
    return data.get("total_count", 0)


def get_latest_deployment() -> Optional[Dict[str, Any]]:
    """
    Get the most recent deployment.

    Returns:
        The latest deployment record, or None if none exist.
    """
    deployments = get_deployment_history()
    return deployments[0] if deployments else None


def get_deployments_by_platform(platform: str) -> List[Dict[str, Any]]:
    """
    Get deployments filtered by platform.

    Args:
        platform: Platform name (vercel, netlify, render)

    Returns:
        List of deployments on that platform.
    """
    return [d for d in get_deployment_history() if d.get("platform") == platform]


def clear_history() -> None:
    """Clear all deployment history."""
    with _locked():
        _write_history(_get_default_history())
    console.print("[green]✅ History cleared.[/green]")


def get_unlocked_badges() -> List[str]:
    """
    Get the list of unlocked badge names.

    Returns:
        List of unlocked badge names.
    """
    with _locked():
        data = _read_history()
    return data.get("badges", {}).get("unlocked", [])


# ──────────────────────────────────────────────────────────────
# BADGE HELPERS
# ──────────────────────────────────────────────────────────────

def _calculate_badge_level(count: int) -> int:
    """Calculate badge level based on deployment count."""
    if count >= 100:
        return 7
    elif count >= 50:
        return 6
    elif count >= 25:
        return 5
    elif count >= 10:
        return 4
    elif count >= 5:
        return 3
    elif count >= 3:
        return 2
    elif count >= 1:
        return 1
    return 0


_BADGES = {
    0: {"emoji": "⬜", "name": "No Badge", "next": 1},
    1: {"emoji": "🥉", "name": "First Launch", "next": 3},
    2: {"emoji": "🥉", "name": "Apprentice", "next": 5},
    3: {"emoji": "🥈", "name": "Builder", "next": 10},
    4: {"emoji": "🥈", "name": "Ship Captain", "next": 25},
    5: {"emoji": "🥇", "name": "Deployment Master", "next": 50},
    6: {"emoji": "🥇", "name": "Shipping Machine", "next": 100},
    7: {"emoji": "🏆", "name": "Opun8 Legend", "next": None},
}


def get_badge_info(count: int) -> Dict[str, Any]:
    """
    Get badge information for a given deployment count.

    Returns:
        Dict with badge level, emoji, name, and next level info.
    """
    level = _calculate_badge_level(count)
    badge = _BADGES.get(level, _BADGES[0])

    return {
        "level": level,
        "emoji": badge["emoji"],
        "name": badge["name"],
        "next": badge["next"],
        "progress": count,
    }


def check_badge_progress(old_count: int, new_count: int) -> Optional[Dict[str, Any]]:
    """
    Check if a new badge was unlocked between two deployment counts.

    Args:
        old_count: Previous deployment count
        new_count: New deployment count

    Returns:
        Dict with badge info if a new badge was unlocked, else None.
    """
    old_level = _calculate_badge_level(old_count)
    new_level = _calculate_badge_level(new_count)

    if new_level > old_level:
        return get_badge_info(new_count)
    return None