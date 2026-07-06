"""
Application settings for Opun8.
"""

from __future__ import annotations

from pathlib import Path

APP_NAME: str = "Opun8"
APP_VERSION: str = "0.1.0"

HOME_DIR: Path = Path.home()
CONFIG_DIR: Path = HOME_DIR / ".opun8"

TOKEN_FILE: Path = CONFIG_DIR / "tokens.json"
USER_FILE: Path = CONFIG_DIR / "user.json"

CONFIG_DIR.mkdir(parents=True, exist_ok=True)