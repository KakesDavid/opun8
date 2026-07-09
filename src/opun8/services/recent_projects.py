"""
Recent projects tracking for Opun8.
"""

import json
from pathlib import Path
from typing import List, Dict, Optional

RECENT_FILE = Path.home() / ".opun8" / "recent_projects.json"


def get_recent_projects() -> List[Dict[str, str]]:
    """Get list of recent projects."""
    if not RECENT_FILE.exists():
        return []
    
    try:
        with open(RECENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("projects", [])
    except Exception:
        return []


def add_recent_project(path: str) -> None:
    """Add a project to recent projects list."""
    projects = get_recent_projects()
    
    # Remove if already exists
    projects = [p for p in projects if p["path"] != path]
    
    # Add to front
    projects.insert(0, {"path": path, "name": Path(path).name})
    
    # Keep only last 10
    projects = projects[:10]
    
    # Save
    RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RECENT_FILE, "w", encoding="utf-8") as f:
        json.dump({"projects": projects}, f, indent=2)


def remove_recent_project(path: str) -> None:
    """Remove a project from recent projects."""
    projects = get_recent_projects()
    projects = [p for p in projects if p["path"] != path]
    
    RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(RECENT_FILE, "w", encoding="utf-8") as f:
        json.dump({"projects": projects}, f, indent=2)