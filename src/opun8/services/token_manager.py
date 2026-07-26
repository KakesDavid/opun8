"""
Token Manager
=============

Handles secure storage and retrieval of JWT authentication tokens.

The token is stored in:
    ~/.opun8/config.json

This file contains ONLY the JWT token — no sensitive user data.
All user data (email, plan, limits) lives on the Render backend.

Security Features:
    - Atomic writes (write to temp file, then rename)
    - Corrupted file recovery (returns empty config instead of crashing)
    - POSIX permission locking (600) on supported platforms

Usage:
    from opun8.services.token_manager import save_token, load_token, delete_token

    # Save token after login
    save_token("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")

    # Load token for API requests
    token = load_token()
    if token:
        headers = {"Authorization": f"Bearer {token}"}

    # Logout
    delete_token()
"""

import json
import os
from pathlib import Path
from typing import Optional

# =============================================================================
# CONSTANTS
# =============================================================================

CONFIG_DIR = Path.home() / ".opun8"
CONFIG_FILE = CONFIG_DIR / "config.json"
TEMP_SUFFIX = ".tmp"


# =============================================================================
# CORE FUNCTIONS
# =============================================================================

def _ensure_config_dir() -> None:
    """Create config directory if it doesn't exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def _load_config() -> dict:
    """
    Load the entire config file with error handling.

    Returns:
        dict: Config data, or empty dict if file is missing or corrupted

    Note:
        Handles JSONDecodeError (malformed JSON) and non-dict payloads
        gracefully to prevent crashes from corrupted files.
    """
    _ensure_config_dir()

    if not CONFIG_FILE.exists():
        return {}

    try:
        with open(CONFIG_FILE, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        # File is corrupted (partial write, manual edit, disk error)
        # Treat as empty config rather than crashing
        return {}


def _save_config(config: dict) -> None:
    """
    Save the entire config file atomically.

    Uses write-to-temp-then-rename pattern to prevent corruption:
    - Writes to a temporary file first
    - Sets secure permissions (600)
    - Atomically renames to final destination

    This prevents partial writes if the process is killed mid-save.
    """
    _ensure_config_dir()

    # Write to temporary file first
    temp_file = CONFIG_FILE.with_suffix(TEMP_SUFFIX)

    with open(temp_file, "w") as f:
        json.dump(config, f, indent=2)

    # Set secure permissions (owner read/write only)
    # Note: On Windows, this only sets the read-only flag,
    # not full Unix-style permissions
    try:
        os.chmod(temp_file, 0o600)
    except OSError:
        # Windows may not support chmod fully; skip gracefully
        pass

    # Atomic rename (POSIX) / replace (Windows)
    temp_file.replace(CONFIG_FILE)


def save_token(token: str) -> None:
    """
    Save JWT token to config file.

    Args:
        token: The JWT token string

    Example:
        >>> save_token("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...")
    """
    config = _load_config()
    config["token"] = token
    _save_config(config)


def load_token() -> Optional[str]:
    """
    Load JWT token from config file.

    Returns:
        Token string if it exists, otherwise None

    Example:
        >>> token = load_token()
        >>> if token:
        ...     print("User is logged in")
    """
    config = _load_config()
    return config.get("token")


def delete_token() -> None:
    """Delete JWT token from config file."""
    config = _load_config()
    if "token" in config:
        del config["token"]
        _save_config(config)


def is_authenticated() -> bool:
    """
    Check if user is currently authenticated.

    Returns:
        True if a valid token exists, False otherwise

    Note:
        This function is safe to call even with corrupted config files.
        It will return False instead of crashing.

    Example:
        >>> if is_authenticated():
        ...     print("Welcome back!")
        ... else:
        ...     print("Please login: opun8 login")
    """
    token = load_token()
    return token is not None and len(token) > 0


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "save_token",
    "load_token",
    "delete_token",
    "is_authenticated",
]