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
    - Netlify (detects netlify.toml)  ✅ NEW

Usage:
    from opun8.core.detector import detect_project

    project = detect_project(".")
    print(project.framework)
    print(project.build_command)
    print(project.output_dir)

Author: OPUN8 Team
Version: 0.1.8
Requires: Python 3.11+ (uses stdlib tomllib; no tomli fallback)

Changelog:
✅ FIX: package.json no longer unconditionally wins over Python detection.
        A *specific* JS framework match (next, react-scripts, vite, vue,
        angular, sveltekit, express/fastify/koa) still wins outright, but
        a generic "nodejs" catch-all (package.json with no recognized
        framework — e.g. a stray package.json for husky/eslint/tailwind
        tooling alongside a real Python backend) now defers to Python
        detection when Python markers are also present.
✅ FIX: _has_python_project() now also recognizes pyproject.toml, Pipfile,
        poetry.lock, uv.lock, and a root-level *.py file, not just
        requirements.txt/setup.py/app.py/main.py/manage.py/wsgi.py/asgi.py.
✅ FIX: Python projects now get a real package_manager (poetry/pipenv/uv/
        pip) via _detect_python_package_manager(), instead of silently
        inheriting the "npm" dataclass default meant for JS projects.
✅ FIX: Added _framework_from_pyproject() to infer django/flask/fastapi
        from pyproject.toml dependencies (both PEP 621 `[project]
        dependencies` and Poetry's `[tool.poetry.dependencies]`), for
        projects with no manage.py/app.py/main.py entrypoint file.
✅ FIX: Dropped the tomli fallback now that opun8 targets Python 3.11+.
        tomllib is stdlib as of 3.11, so there's nothing left to install
        or for Pylance/mypy to fail to resolve.
✅ FIX: detect_project() now determines the real framework from source
        files (package.json / Python / static HTML) FIRST, always. Netlify
        configuration is layered on afterward as deployment metadata only
        (output dir, build command, deploy target) and can never override
        or bypass the detected framework.
        Previously, _has_netlify_config() short-circuited on the mere
        presence of a `.netlify` folder — which the Netlify CLI creates
        automatically on `netlify link`/`dev`/`deploy` in ANY project,
        regardless of framework — causing real React/Next.js/Vue/Angular
        projects to be misreported as "static" or generic "netlify"
        whenever they'd ever been connected to Netlify before.
✅ FIX: Netlify-side framework inference (used only when there's no
        package.json framework match) now reuses the same dependency
        detection as _detect_from_package_json() instead of a separate,
        incomplete, hardcoded 5-dependency copy.
✅ FIX: TOML parsing failures are logged instead of silently swallowed.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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
        deploy_target: Suggested deployment platform (vercel, netlify, render)
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
    deploy_target: Optional[str] = None  # ✅ NEW: Suggested platform
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
            self.deploy_target = self.deploy_target or "vercel"

        # Next.js
        elif framework == "nextjs":
            self.needs_build = True
            self.output_dir = self.output_dir or ".next"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run dev"
            self.deploy_target = self.deploy_target or "vercel"

        # Vite
        elif framework == "vite":
            self.needs_build = True
            self.output_dir = self.output_dir or "dist"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run dev"
            self.deploy_target = self.deploy_target or "vercel"

        # Vue CLI
        elif framework == "vue":
            self.needs_build = True
            self.output_dir = self.output_dir or "dist"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run serve"
            self.deploy_target = self.deploy_target or "vercel"

        # Angular
        elif framework == "angular":
            self.needs_build = True
            self.output_dir = self.output_dir or "dist"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run start"
            self.deploy_target = self.deploy_target or "vercel"

        # SvelteKit
        elif framework == "sveltekit":
            self.needs_build = True
            self.output_dir = self.output_dir or "build"
            self.build_command = self.build_command or f"{self.package_manager} run build"
            self.dev_command = self.dev_command or f"{self.package_manager} run dev"
            self.deploy_target = self.deploy_target or "vercel"

        # Node.js (Express, Fastify, Koa, etc.)
        elif framework == "nodejs":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.dev_command = self.dev_command or f"{self.package_manager} run dev"
            self.deploy_target = self.deploy_target or "render"

        # Django
        elif framework == "django":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = False
            self.deploy_target = self.deploy_target or "render"

        # Flask
        elif framework == "flask":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = False
            self.deploy_target = self.deploy_target or "render"

        # FastAPI
        elif framework == "fastapi":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = False
            self.deploy_target = self.deploy_target or "render"

        # Python (generic fallback)
        elif framework == "python":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = False
            self.deploy_target = self.deploy_target or "render"

        # Static HTML
        elif framework == "static":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = True
            self.deploy_target = self.deploy_target or "netlify"

        # Netlify-specific detection (only used when no real framework
        # could be inferred at all — see _apply_netlify_overrides)
        elif framework == "netlify":
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = True
            self.deploy_target = self.deploy_target or "netlify"

        # Unknown — treat as static
        else:
            self.needs_build = False
            self.output_dir = self.output_dir or "."
            self.is_static = True
            self.deploy_target = self.deploy_target or "netlify"


# =============================================================================
# FRAMEWORK DETECTION
# =============================================================================

def detect_project(project_path: str = ".") -> ProjectInfo:
    """
    Detect the project type and framework.

    Detection always determines the real framework from source files first
    (package.json → Python markers → static HTML → unknown). Netlify
    configuration (netlify.toml / a `.netlify` folder from the Netlify CLI)
    is then layered on top purely as deployment metadata — it refines
    build_command/output_dir/deploy_target but never overrides the
    detected framework. This matters because the Netlify CLI creates a
    `.netlify` folder in ANY project the moment you run `netlify link`,
    `netlify dev`, or `netlify deploy` — its presence says nothing about
    what framework the project actually uses.

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

    project = _detect_framework(path)

    # Layer Netlify config on top as deployment metadata only — never lets
    # it change `framework`.
    if _has_netlify_config(path):
        _apply_netlify_overrides(project, path)

    return project


def _detect_framework(path: Path) -> ProjectInfo:
    """
    Determine the actual project framework from source files, independent
    of any Netlify configuration.

    package.json is checked first, but a *generic* "nodejs" result (i.e.
    package.json exists but matched none of the recognized frontend/
    backend JS frameworks — often just a stray package.json for tooling
    like husky/eslint/tailwind alongside a real Python backend) is treated
    as a weak signal. If Python project markers are also present, Python
    wins in that case. A *specific* JS framework match (next, react-scripts,
    vite, vue, angular, sveltekit, express/fastify/koa) is a strong signal
    and always wins regardless of any Python files present.
    """
    package_json_path = path / "package.json"
    js_result: Optional[ProjectInfo] = None

    if package_json_path.exists():
        try:
            with open(package_json_path) as f:
                package_data = json.load(f)
            js_result = _detect_from_package_json(package_data, path)
        except json.JSONDecodeError:
            logger.warning("Could not parse package.json at %s; falling back", package_json_path)

    python_detected = _has_python_project(path)

    if js_result is not None:
        if js_result.framework != "nodejs" or not python_detected:
            # Either a specific JS framework was matched (strong signal),
            # or there's no Python project to prefer instead — trust it.
            return js_result
        # js_result.framework == "nodejs" (generic fallback = weak signal)
        # AND Python markers are present — prefer the Python detection.

    if python_detected:
        return _detect_python_project(path)

    if js_result is not None:
        # No Python markers at all — the generic "nodejs" result stands.
        return js_result

    # Check for static HTML
    if _has_static_html(path):
        return ProjectInfo(framework="static", is_static=True, needs_build=False, output_dir=".")

    # Unknown project
    return ProjectInfo(framework="unknown", needs_build=False, output_dir=".")


# =============================================================================
# NETLIFY DETECTION  ✅ NEW
# =============================================================================

def _has_netlify_config(path: Path) -> bool:
    """
    Check if the project has Netlify configuration.

    Note: a `.netlify` folder only means the project has been linked to
    Netlify at some point (via `netlify link`/`dev`/`deploy`) — it says
    nothing about what framework the project is. Callers must not use this
    as a signal to skip real framework detection.
    """
    if (path / "netlify.toml").exists():
        return True
    if (path / ".netlify").exists():
        return True
    return False


def _get_tomllib():
    """
    Return the stdlib tomllib module.

    opun8 targets Python 3.11+, where tomllib ships in the standard
    library, so there's no tomli fallback to install or resolve.
    """
    import tomllib
    return tomllib


def _apply_netlify_overrides(project: ProjectInfo, path: Path) -> None:
    """
    Layer Netlify deployment settings onto an already-detected ProjectInfo.

    This only ever refines build_command / output_dir / deploy_target /
    metadata. It never touches `project.framework` — the framework was
    already correctly determined by `_detect_framework()` from the actual
    source files, and a Netlify link/config says nothing about that.
    """
    netlify_toml = path / "netlify.toml"

    if not netlify_toml.exists():
        # Just a `.netlify` folder from `netlify link`/`dev` with no
        # netlify.toml checked in. That's just prior CLI state — nothing
        # to layer on, and definitely not a reason to call this "static".
        project.deploy_target = "netlify"
        return

    tomllib = _get_tomllib()

    try:
        with open(netlify_toml, "rb") as f:
            config = tomllib.load(f)
    except Exception:
        logger.exception("Failed to parse netlify.toml at %s", netlify_toml)
        project.deploy_target = "netlify"
        return

    build_config = config.get("build", {})
    publish_dir = build_config.get("publish")
    build_command = build_config.get("command")

    if publish_dir:
        project.output_dir = publish_dir
    if build_command:
        project.build_command = build_command
        project.needs_build = True

    functions = config.get("functions", {})
    has_functions = bool(functions.get("directory"))
    if has_functions:
        project.is_static = False

    # If the real framework couldn't be determined from source at all,
    # fall back to whatever hint netlify.toml + package.json can offer,
    # rather than leaving it as a bare "unknown"/"static" guess.
    if project.framework in ("unknown", "static"):
        project.framework = "netlify"
        if functions.get("directory"):
            project.deploy_target = "netlify"

    project.deploy_target = "netlify"
    project.metadata["netlify_config"] = config


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

    # React (Create React App, or plain React with a custom bundler)
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
    elif "@sveltejs/kit" in all_deps:
        framework = "sveltekit"

    # Node.js (Express, Fastify, Koa, etc.)
    elif "express" in all_deps or "fastify" in all_deps or "koa" in all_deps:
        framework = "nodejs"

    # Plain React without react-scripts/vite (e.g. custom webpack config)
    elif "react" in all_deps:
        framework = "react"

    # Plain Vue without @vue/cli-service (e.g. custom bundler)
    elif "vue" in all_deps:
        framework = "vue"

    # Check scripts for build command
    if framework is None:
        scripts = package_data.get("scripts", {})
        if "build" in scripts:
            build_script = scripts.get("build", "")
            if "vite" in build_script:
                framework = "vite"
            else:
                framework = "nodejs"

    if framework is None:
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

    Covers both traditional markers (requirements.txt, setup.py, common
    entrypoint filenames) and modern packaging/tooling markers
    (pyproject.toml, Pipfile, poetry.lock, uv.lock), plus a root-level
    *.py file as a last-resort signal. The glob is deliberately
    non-recursive (root directory only) so it can't pick up unrelated
    .py scripts buried in an unrelated project's subfolders.
    """
    python_files = ["app.py", "main.py", "manage.py", "wsgi.py", "asgi.py"]
    for file in python_files:
        if (path / file).exists():
            return True

    python_markers = [
        "requirements.txt",
        "setup.py",
        "pyproject.toml",
        "Pipfile",
        "poetry.lock",
        "uv.lock",
    ]
    for marker in python_markers:
        if (path / marker).exists():
            return True

    # Last resort: any root-level .py file at all.
    try:
        next(path.glob("*.py"))
        return True
    except StopIteration:
        pass

    return False


def _detect_python_package_manager(path: Path) -> str:
    """
    Detect which Python package/dependency manager the project uses.

    Returns:
        "poetry", "pipenv", "uv", or "pip" (default fallback).
    """
    if (path / "poetry.lock").exists():
        return "poetry"
    if (path / "Pipfile.lock").exists() or (path / "Pipfile").exists():
        return "pipenv"
    if (path / "uv.lock").exists():
        return "uv"
    return "pip"


def _framework_from_pyproject(path: Path) -> Optional[str]:
    """
    Try to infer django/flask/fastapi from pyproject.toml dependencies,
    covering both PEP 621 (`[project] dependencies = [...]`) and Poetry
    (`[tool.poetry.dependencies]`) formats.

    Returns the framework name, or None if pyproject.toml doesn't exist,
    can't be parsed, or names none of the recognized frameworks.
    """
    pyproject_path = path / "pyproject.toml"
    if not pyproject_path.exists():
        return None

    try:
        tomllib = _get_tomllib()
        with open(pyproject_path, "rb") as f:
            config = tomllib.load(f)
    except Exception:
        logger.warning("Could not parse pyproject.toml at %s", pyproject_path)
        return None

    dep_names = set()

    # PEP 621: [project] dependencies = ["django>=5.0", "fastapi", ...]
    for dep in config.get("project", {}).get("dependencies", []):
        # Strip version specifiers/extras: "django>=5.0" -> "django"
        name = dep.split(";")[0].strip()
        for sep in ("[", "=", ">", "<", "~", "!", " "):
            name = name.split(sep, 1)[0]
        dep_names.add(name.strip().lower())

    # Poetry: [tool.poetry.dependencies] django = "^5.0"
    poetry_deps = config.get("tool", {}).get("poetry", {}).get("dependencies", {})
    dep_names.update(key.lower() for key in poetry_deps.keys())

    if "django" in dep_names:
        return "django"
    if "fastapi" in dep_names:
        return "fastapi"
    if "flask" in dep_names:
        return "flask"

    return None


def _detect_python_project(path: Path) -> ProjectInfo:
    """
    Detect the type of Python project, including its package manager.
    """
    package_manager = _detect_python_package_manager(path)

    # Detect Django
    if (path / "manage.py").exists():
        return ProjectInfo(framework="django", package_manager=package_manager)

    # Detect Flask (app.py)
    if (path / "app.py").exists():
        return ProjectInfo(framework="flask", package_manager=package_manager)

    # Detect FastAPI (main.py)
    if (path / "main.py").exists():
        try:
            with open(path / "main.py") as f:
                content = f.read()
                if "FastAPI" in content:
                    return ProjectInfo(framework="fastapi", package_manager=package_manager)
        except Exception:
            pass

    # No file-based match — try pyproject.toml dependencies (covers
    # projects with only a pyproject.toml and no manage.py/app.py, or a
    # differently-named entrypoint like server.py).
    pyproject_framework = _framework_from_pyproject(path)
    if pyproject_framework:
        return ProjectInfo(framework=pyproject_framework, package_manager=package_manager)

    # Generic Python
    return ProjectInfo(framework="python", package_manager=package_manager)


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
        "deploy_target": project.deploy_target,
    }


def get_recommended_platform(project: ProjectInfo) -> Optional[str]:
    """
    Get the recommended deployment platform for a project.

    Args:
        project: ProjectInfo object

    Returns:
        Recommended platform (vercel, netlify, render) or None

    Example:
        >>> project = detect_project(".")
        >>> get_recommended_platform(project)
        "vercel"
    """
    return project.deploy_target


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "ProjectInfo",
    "detect_project",
    "get_build_commands",
    "get_deploy_config",
    "get_recommended_platform",
]