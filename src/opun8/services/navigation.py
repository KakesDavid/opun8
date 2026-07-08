"""
Navigation service for Opun8.
Interactive folder browser.
"""

import os
from pathlib import Path
from typing import Optional, List, Tuple


def get_current_directory() -> str:
    """Get current working directory."""
    return str(Path.cwd())


def change_directory(path: str) -> bool:
    """Change current working directory."""
    try:
        new_path = Path(path).resolve()
        if new_path.exists() and new_path.is_dir():
            os.chdir(new_path)
            return True
        return False
    except Exception:
        return False


def go_up() -> bool:
    """Go up one directory level."""
    current = Path.cwd()
    parent = current.parent
    if parent == current:
        return False
    os.chdir(parent)
    return True


def list_items(path: Optional[str] = None) -> Tuple[List[str], List[str]]:
    """
    List folders and files in the given path.
    Returns: (folders, files)
    """
    target = Path(path) if path else Path.cwd()
    folders = []
    files = []
    
    try:
        for item in target.iterdir():
            if item.name.startswith('.'):
                continue
            if item.is_dir():
                folders.append(item.name)
            else:
                files.append(item.name)
    except Exception:
        pass
    
    return sorted(folders), sorted(files)


def get_drive_list() -> List[str]:
    """Get list of available drives on Windows."""
    drives = []
    try:
        import win32api
        drives = win32api.GetLogicalDriveStrings().split('\000')[:-1]
    except ImportError:
        # Fallback: check common drives
        for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            drive = f"{letter}:\\"
            if Path(drive).exists():
                drives.append(drive)
    return drives


def is_valid_path(path: str) -> bool:
    """Check if a path is valid."""
    try:
        return Path(path).exists() and Path(path).is_dir()
    except Exception:
        return False