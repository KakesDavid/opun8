"""
Project Detector
================

Detects the framework and build configuration of a project.

Supports:
    - React (Create React App)
    - Next.js
    - Vite (React, Vue, Vanilla)
    - Vue CLI
    - Angular
    - SvelteKit
    - Python (Flask, Django, FastAPI)
    - Static HTML
    - Node.js

Usage:
    from opun8.core.detector import detect_project

    project = detect_project(".")
    print(project.framework)
    print(project.build_command)
    print(project.output_dir)

Author: OPUN8 Team
Version: 0.1.4
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class ProjectInfo:
    """
    Information about a detected project.

    Attributes:
        framework: The detected framework name (react, nextjs, vite, etc.)
        build_command: The command to run for building the project
        output_dir: The directory where build output is placed
        install_command: The command to install dependencies
        dev_command: The command to run the development server
        package_manager: Detected package manager (npm, yarn, pnpm)
        is_static: Whether the project is static HTML
        needs_build: Whether the project needs to be built
        metadata: Additional metadata for extensibility
    """
    framework: str = "unknown"
    build_command: Optional[str] = None
    output_dir: Optional[str] = None
    install_command: Optional[str] = None
    dev_command: Optional[str] = None
    package_manager: str = "npm"
    is_static: bool = False
    needs_build: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Set defaults based on framework."""
        self._apply_framework_defaults()

        # Ensure output_dir is never None (fallback to ".")
        if self.output_dir is None:
            self.output_dir = "."

    def _apply_framework_defaults(self):
        """Apply framework-specific defaults."""
        framework = self.framework.lower()

        # React (Create React App)
        if framework == "react":
            self.needs_build = True
            self.output_dir = self.output_dir or "build"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} start"

        # Next.js
        elif framework == "nextjs":
            self.needs_build = True
            self.output_dir = self.output_dir or ".next"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run dev"

        # Vite
        elif framework == "vite":
            self.needs_build = True
            self.output_dir = self.output_dir or "dist"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run dev"

        # Vue CLI
        elif framework == "vue":
            self.needs_build = True
            self.output_dir = self.output_dir or "dist"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run serve"

        # Angular
        elif framework == "angular":
            self.needs_build = True
            self.output_dir = self.output_dir or "dist"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run start"

        # SvelteKit
        elif framework == "sveltekit":
            self.needs_build = True
            self.output_dir = self.output_dir or "build"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run dev"

        # Node.js (Express, Fastify, Koa, etc.)
        elif framework == "nodejs":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.dev_command = self.dev_command or f"{self.package_manager} run dev"

        # Django
        elif framework == "django":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = False

        # Flask
        elif framework == "flask":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = False

        # FastAPI
        elif framework == "fastapi":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = False

        # Python (generic fallback)
        elif framework == "python":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = False

        # Static HTML
        elif framework == "static":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = True

        # Unknown — treat as static
        else:
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = True


# =============================================================================
# FRAMEWORK DETECTION
# =============================================================================

def detect_project(project_path: str = ".") -> ProjectInfo:
    """
    Detect the project type and framework.

    Args:
        project_path: Path to the project directory

    Returns:
        ProjectInfo object with detected configuration

    Example:
        >>> project = detect_project(".")
        >>> print(project.framework)
        "react"
        >>> print(project.build_command)
        "npm run build"
    """
    path = Path(project_path)

    # Check for package.json
    package_json_path = path / "package.json"
    if package_json_path.exists():
        try:
            with open(package_json_path) as f:
                package_data = json.load(f)
            return _detect_from_package_json(package_data, path)
        except json.JSONDecodeError:
            pass

    # Check for Python files
    if _has_python_project(path):
        return _detect_python_project(path)

    # Check for static HTML
    if _has_static_html(path):
        return ProjectInfo(framework="static", is_static=True, needs_build=False, output_dir=".")

    # Unknown project
    return ProjectInfo(framework="unknown", needs_build=False, output_dir=".")


def _detect_from_package_json(package_data: Dict[str, Any], path: Path) -> ProjectInfo:
    """
    Detect framework from package.json contents.
    """
    dependencies = package_data.get("dependencies", {})
    dev_dependencies = package_data.get("devDependencies", {})
    all_deps = {**dependencies, **dev_dependencies}

    # Detect package manager
    package_manager = _detect_package_manager(path)

    # Detect framework in priority order
    framework = None

    # Next.js (highest priority)
    if "next" in all_deps:
        framework = "nextjs"

    # React (Create React App)
    elif "react-scripts" in all_deps:
        framework = "react"

    # Vite
    elif "vite" in all_deps:
        framework = "vite"

    # Vue CLI
    elif "@vue/cli-service" in all_deps:
        framework = "vue"

    # Angular
    elif "@angular/cli" in all_deps or "@angular/core" in all_deps:
        framework = "angular"

    # SvelteKit
    elif "sveltekit" in all_deps or "@sveltejs/kit" in all_deps:
        framework = "sveltekit"

    # Node.js (Express, Fastify, Koa, etc.)
    elif "express" in all_deps or "fastify" in all_deps or "koa" in all_deps:
        framework = "nodejs"

    # Check scripts for build command
    if framework is None:
        scripts = package_data.get("scripts", {})
        if "build" in scripts:
            # Has a build script but no detected framework
            build_script = scripts.get("build", "")
            if "vite" in build_script:
                framework = "vite"
            else:
                framework = "nodejs"

    if framework is None:
        # Default to Node.js for any package.json project
        framework = "nodejs"

    return ProjectInfo(
        framework=framework,
        package_manager=package_manager,
    )


def _detect_package_manager(path: Path) -> str:
    """
    Detect which package manager is being used.

    Returns:
        npm, yarn, or pnpm
    """
    if (path / "pnpm-lock.yaml").exists():
        return "pnpm"
    if (path / "yarn.lock").exists():
        return "yarn"
    if (path / "package-lock.json").exists():
        return "npm"
    return "npm"  # Default


def _has_python_project(path: Path) -> bool:
    """
    Check if the project is a Python project.
    """
    # Check for common Python files
    python_files = ["app.py", "main.py", "manage.py", "wsgi.py", "asgi.py"]
    for file in python_files:
        if (path / file).exists():
            return True

    # Check for requirements.txt or setup.py
    if (path / "requirements.txt").exists() or (path / "setup.py").exists():
        return True

    return False


def _detect_python_project(path: Path) -> ProjectInfo:
    """
    Detect the type of Python project.
    """
    # Detect Django
    if (path / "manage.py").exists():
        return ProjectInfo(framework="django")

    # Detect Flask (app.py)
    if (path / "app.py").exists():
        return ProjectInfo(framework="flask")

    # Detect FastAPI (main.py)
    if (path / "main.py").exists():
        try:
            with open(path / "main.py") as f:
                content = f.read()
                if "FastAPI" in content:
                    return ProjectInfo(framework="fastapi")
        except Exception:
            pass

    # Generic Python
    return ProjectInfo(framework="python")


def _has_static_html(path: Path) -> bool:
    """
    Check if the project is a static HTML project.
    """
    return (path / "index.html").exists()


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_build_commands(project: ProjectInfo) -> Dict[str, str]:
    """
    Get the build commands for a project.

    Args:
        project: ProjectInfo object

    Returns:
        Dictionary of commands with descriptions

    Example:
        >>> project = detect_project(".")
        >>> commands = get_build_commands(project)
        >>> commands["build"]  # "npm run build"
    """
    commands = {}

    if project.needs_build and project.build_command:
        commands["build"] = project.build_command

    if project.install_command:
        commands["install"] = project.install_command

    if project.dev_command:
        commands["dev"] = project.dev_command

    return commands


def get_deploy_config(project: ProjectInfo) -> Dict[str, Any]:
    """
    Get the deployment configuration for a project.

    Args:
        project: ProjectInfo object

    Returns:
        Dictionary with deployment configuration

    Example:
        >>> project = detect_project(".")
        >>> config = get_deploy_config(project)
        >>> config["output_dir"]  # "build" or "dist" or "."
    """
    return {
        "framework": project.framework,
        "output_dir": project.output_dir,
        "needs_build": project.needs_build,
        "is_static": project.is_static,
        "package_manager": project.package_manager,
        "build_command": project.build_command,
    }


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "ProjectInfo",
    "detect_project",
    "get_build_commands",
    "get_deploy_config",
]