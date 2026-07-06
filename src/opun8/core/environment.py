"""
Environment detection and validation for Opun8.
"""

import sys
import shutil
import subprocess
import platform
import socket
from pathlib import Path
from typing import Dict, Any, Optional


class EnvironmentChecker:
    """Check system environment for Opun8 requirements."""

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()

    def check_all(self) -> Dict[str, Any]:
        """Run all environment checks."""
        return {
            "system": self.check_system(),
            "python": self.check_python(),
            "git": self.check_git(),
            "node": self.check_node(),
            "npm": self.check_npm(),
            "internet": self.check_internet(),
            "project": self.check_project(),
        }

    def check_system(self) -> Dict[str, Any]:
        """Check operating system information."""
        return {
            "name": "System",
            "passed": True,
            "details": f"{platform.system()} {platform.release()}",
        }

    def check_python(self) -> Dict[str, Any]:
        """Check Python version."""
        version = sys.version.split()[0]
        return {
            "name": "Python",
            "passed": True,
            "details": f"v{version}",
        }

    def check_git(self) -> Dict[str, Any]:
        """Check if Git is installed and get version."""
        git_path = shutil.which("git")
        if git_path:
            try:
                result = subprocess.run(
                    ["git", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip().split()[2]
                    return {
                        "name": "Git",
                        "passed": True,
                        "details": f"v{version}",
                    }
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        return {
            "name": "Git",
            "passed": False,
            "details": "Not found (required for Git operations)",
        }

    def check_node(self) -> Dict[str, Any]:
        """Check if Node.js is installed."""
        node_path = shutil.which("node")
        if node_path:
            try:
                result = subprocess.run(
                    ["node", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    return {
                        "name": "Node.js",
                        "passed": True,
                        "details": f"{version}",
                    }
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        return {
            "name": "Node.js",
            "passed": False,
            "details": "Not found (optional, but needed for JS projects)",
        }

    def check_npm(self) -> Dict[str, Any]:
        """Check if npm is installed."""
        npm_path = shutil.which("npm")
        if npm_path:
            try:
                result = subprocess.run(
                    ["npm", "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    version = result.stdout.strip()
                    return {
                        "name": "npm",
                        "passed": True,
                        "details": f"v{version}",
                    }
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        return {
            "name": "npm",
            "passed": False,
            "details": "Not found (optional, but needed for JS projects)",
        }

    def check_internet(self) -> Dict[str, Any]:
        """Check internet connectivity."""
        try:
            socket.create_connection(("8.8.8.8", 53), timeout=3)
            return {
                "name": "Internet",
                "passed": True,
                "details": "Connected",
            }
        except OSError:
            return {
                "name": "Internet",
                "passed": False,
                "details": "No connection (needed for deployment)",
            }

    def check_project(self) -> Dict[str, Any]:
        """Check project type and structure."""
        result = {
            "name": "Project",
            "passed": False,
            "details": "No project detected",
            "project_type": None,
        }

        # Check for package.json (Node.js projects)
        package_json = self.project_path / "package.json"
        if package_json.exists():
            result["passed"] = True
            result["details"] = "Node.js project detected"
            result["project_type"] = "node"

            # Check for framework-specific dependencies
            try:
                import json
                with open(package_json, "r") as f:
                    data = json.load(f)
                    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                    if "react" in deps:
                        result["details"] = "React project detected"
                        result["project_type"] = "react"
                    elif "next" in deps:
                        result["details"] = "Next.js project detected"
                        result["project_type"] = "next"
                    elif "vue" in deps:
                        result["details"] = "Vue project detected"
                        result["project_type"] = "vue"
            except (json.JSONDecodeError, KeyError):
                pass

            # Check for build script
            try:
                import json
                with open(package_json, "r") as f:
                    data = json.load(f)
                    scripts = data.get("scripts", {})
                    if "build" in scripts:
                        result["details"] += " (build script found)"
            except (json.JSONDecodeError, KeyError):
                pass

        # Check for index.html (static site)
        elif (self.project_path / "index.html").exists():
            result["passed"] = True
            result["details"] = "Static HTML project detected"
            result["project_type"] = "static"

        # Check for requirements.txt (Python project)
        elif (self.project_path / "requirements.txt").exists():
            result["passed"] = True
            result["details"] = "Python project detected"
            result["project_type"] = "python"

        return result