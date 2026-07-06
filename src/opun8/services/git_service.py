"""
Git service for Opun8.
"""

from __future__ import annotations

import subprocess


class GitService:
    """Handles interactions with Git."""

    @staticmethod
    def is_installed() -> bool:
        """Return True if Git is installed."""
        try:
            subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except (FileNotFoundError, subprocess.CalledProcessError):
            return False

    @staticmethod
    def is_repository() -> bool:
        """Return True if the current directory is a Git repository."""
        try:
            subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    @staticmethod
    def initialize() -> bool:
        """Initialize a new Git repository."""
        try:
            subprocess.run(
                ["git", "init"],
                check=True,
            )
            return True
        except subprocess.CalledProcessError:
            return False