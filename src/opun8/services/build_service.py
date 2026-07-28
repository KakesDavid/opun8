"""
Build Service
=============

Handles building projects before deployment.

This service:
    1. Detects the project type
    2. Checks if the build folder exists
    3. Runs the build command if needed
    4. Reports progress to the user

Usage:
    from opun8.services.build_service import BuildService

    service = BuildService()
    result = service.ensure_build(".")
    print(result["built"])  # True or False

Author: OPUN8 Team
Version: 0.1.4
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from opun8.core.detector import detect_project, ProjectInfo

console = Console()


# =============================================================================
# BUILD SERVICE
# =============================================================================

class BuildService:
    """
    Service for building projects before deployment.
    """

    def __init__(self, project_path: str = "."):
        """
        Initialize the build service.

        Args:
            project_path: Path to the project directory
        """
        self.project_path = Path(project_path)
        self.project_info: Optional[ProjectInfo] = None
        self._detected = False

    def detect(self) -> ProjectInfo:
        """
        Detect the project type.

        Returns:
            ProjectInfo object
        """
        if not self._detected:
            self.project_info = detect_project(str(self.project_path))
            self._detected = True
        return self.project_info

    def needs_build(self) -> bool:
        """
        Check if the project needs to be built.

        Returns:
            True if the project needs to be built
        """
        project = self.detect()
        return project.needs_build

    def build_folder_exists(self) -> bool:
        """
        Check if the build output folder exists.

        Returns:
            True if the build folder exists
        """
        project = self.detect()
        output_dir = project.output_dir
        if output_dir == ".":
            return True  # Static or Python projects don't need a build folder
        return (self.project_path / output_dir).exists()

    def ensure_build(self, force: bool = False) -> Dict[str, Any]:
        """
        Ensure the project is built.

        Args:
            force: Force a rebuild even if build folder exists

        Returns:
            Dictionary with build result

        Example:
            >>> service = BuildService()
            >>> result = service.ensure_build()
            >>> print(result["built"])
            True
        """
        result = {
            "built": False,
            "message": "",
            "output_dir": ".",
            "framework": "unknown",
            "build_command": None,
        }

        project = self.detect()
        result["framework"] = project.framework
        result["output_dir"] = project.output_dir
        # ✅ FIX: Populate build_command from detected project
        result["build_command"] = project.build_command

        # Static projects don't need building
        if not project.needs_build or project.is_static:
            result["built"] = True
            result["message"] = "No build needed (static project)"
            return result

        # Check if build folder exists
        if not force and self.build_folder_exists():
            result["built"] = True
            result["message"] = f"Build folder '{project.output_dir}' already exists"
            return result

        # Run the build command
        if not project.build_command:
            result["message"] = "No build command defined"
            return result

        console.print()
        console.print(f"[yellow]⚠️ Build folder '{project.output_dir}' not found.[/yellow]")
        console.print(f"[cyan]🔨 Running: {project.build_command}[/cyan]")
        console.print()

        # Run the build command with progress
        success, output = self._run_build_command(project.build_command)

        if success:
            result["built"] = True
            result["message"] = "Build completed successfully"
            console.print("[green]✅ Build complete![/green]")
        else:
            result["built"] = False
            result["message"] = f"Build failed: {output}"
            console.print(f"[red]❌ Build failed: {output}[/red]")

        return result

    def _run_build_command(self, command: str) -> Tuple[bool, str]:
        """
        Run a build command with progress display.

        Args:
            command: The build command to run

        Returns:
            Tuple of (success, output)
        """
        try:
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                console=console,
            ) as progress:
                task = progress.add_task("[cyan]Building project...", total=None)

                process = subprocess.Popen(
                    command,
                    shell=True,
                    cwd=str(self.project_path),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                stdout, stderr = process.communicate()

                progress.update(task, description="[green]Build complete!")

                if process.returncode == 0:
                    return True, stdout
                else:
                    return False, stderr or stdout

        except Exception as e:
            return False, str(e)

    def get_build_info(self) -> Dict[str, Any]:
        """
        Get build information for the project.

        Returns:
            Dictionary with build information

        Example:
            >>> service = BuildService()
            >>> info = service.get_build_info()
            >>> print(info["needs_build"])
            True
        """
        project = self.detect()
        return {
            "framework": project.framework,
            "needs_build": project.needs_build,
            "output_dir": project.output_dir,
            "build_command": project.build_command,
            "build_exists": self.build_folder_exists(),
            "package_manager": project.package_manager,
        }


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_build_service: Optional[BuildService] = None


def get_build_service(project_path: str = ".") -> BuildService:
    """
    Get or create the global build service instance.

    Args:
        project_path: Path to the project directory

    Returns:
        BuildService singleton instance
    """
    global _build_service
    if _build_service is None or _build_service.project_path != Path(project_path):
        _build_service = BuildService(project_path)
    return _build_service


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "BuildService",
    "get_build_service",
]