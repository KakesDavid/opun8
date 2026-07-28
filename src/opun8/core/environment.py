"""
Environment detection and validation for Opun8.
"""

import sys
import os
import shutil
import subprocess
import platform
import socket
import urllib.request
from pathlib import Path
from typing import Dict, Any, Optional

from rich.console import Console
from rich.prompt import Confirm

console = Console()


class EnvironmentChecker:
    """Check system environment for Opun8 requirements."""

    def __init__(self, project_path: Optional[Path] = None):
        self.project_path = project_path or Path.cwd()

    def check_all(self, auto_install: bool = True) -> Dict[str, Any]:
        """Run all environment checks."""
        results = {
            "system": self.check_system(),
            "python": self.check_python(),
            "git": self.check_git(),
            "node": self.check_node(auto_install=auto_install),
            "npm": self.check_npm(),
            "internet": self.check_internet(),
            "project": self.check_project(),
        }
        return results

    # ──────────────────────────────────────────────────────────────
    # SYSTEM CHECKS
    # ──────────────────────────────────────────────────────────────

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
        git_path = self._find_executable("git")
        if git_path:
            try:
                result = subprocess.run(
                    [git_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    version = result.stdout.strip().replace("git version ", "")
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

    # ──────────────────────────────────────────────────────────────
    # NODE.JS + NPM CHECKS (WITH AUTO-INSTALL)
    # ──────────────────────────────────────────────────────────────

    def check_node(self, auto_install: bool = True) -> Dict[str, Any]:
        """
        Check if Node.js is installed.
        If not found and auto_install is True, attempt to install it.
        """
        # Check if Node.js is already installed
        node_path = self._find_executable("node")
        if node_path:
            try:
                result = subprocess.run(
                    [node_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
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

        # Not found — try to install if auto_install is True
        if auto_install:
            return self._install_node()

        return {
            "name": "Node.js",
            "passed": False,
            "details": "Not found (optional, but needed for JS projects)",
        }

    def check_npm(self) -> Dict[str, Any]:
        """
        Check if npm is installed.
        Cross-platform detection for Windows, macOS, and Linux.
        """
        npm_path = self._find_executable("npm")
        
        if npm_path:
            try:
                result = subprocess.run(
                    [npm_path, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=5,
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

        # Fallback: try through Node.js
        node_path = self._find_executable("node")
        if node_path:
            try:
                # Try to get npm version via Node.js
                result = subprocess.run(
                    [node_path, "-e", "console.log(require('child_process').execSync('npm --version').toString().trim())"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0 and result.stdout.strip():
                    version = result.stdout.strip()
                    return {
                        "name": "npm",
                        "passed": True,
                        "details": f"v{version}",
                    }
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # On Windows, try additional search paths
        if platform.system() == "Windows":
            npm_paths = [
                r"C:\Program Files\nodejs\npm.cmd",
                r"C:\Program Files\nodejs\npm",
                r"C:\Program Files (x86)\nodejs\npm.cmd",
                r"C:\Program Files (x86)\nodejs\npm",
                os.path.join(os.environ.get("APPDATA", ""), "npm", "npm.cmd"),
                os.path.join(os.environ.get("APPDATA", ""), "npm", "npm"),
            ]
            for path in npm_paths:
                if os.path.exists(path):
                    try:
                        result = subprocess.run(
                            [path, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if result.returncode == 0:
                            version = result.stdout.strip()
                            return {
                                "name": "npm",
                                "passed": True,
                                "details": f"v{version}",
                            }
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        continue

        # On Linux/macOS, check common locations
        elif platform.system() in ["Linux", "Darwin"]:
            npm_paths = [
                "/usr/local/bin/npm",
                "/usr/bin/npm",
                "/opt/homebrew/bin/npm",  # macOS Homebrew (Apple Silicon)
                "/usr/local/bin/npm",      # macOS Homebrew (Intel)
            ]
            for path in npm_paths:
                if os.path.exists(path):
                    try:
                        result = subprocess.run(
                            [path, "--version"],
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        if result.returncode == 0:
                            version = result.stdout.strip()
                            return {
                                "name": "npm",
                                "passed": True,
                                "details": f"v{version}",
                            }
                    except (subprocess.TimeoutExpired, FileNotFoundError):
                        continue

        return {
            "name": "npm",
            "passed": False,
            "details": "Not found (optional, but needed for JS projects)",
        }

    def _find_executable(self, name: str) -> Optional[str]:
        """
        Find an executable across platforms.
        Uses shutil.which() as primary method with fallbacks.
        """
        # Primary: use shutil.which
        path = shutil.which(name)
        if path:
            return path

        # Windows fallback: check common extensions
        if platform.system() == "Windows":
            for ext in [".exe", ".cmd", ".bat"]:
                path = shutil.which(name + ext)
                if path:
                    return path

            # Check Program Files
            program_files = [
                os.environ.get("ProgramFiles", "C:\\Program Files"),
                os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
            ]
            for pf in program_files:
                node_path = os.path.join(pf, "nodejs", name + ".cmd")
                if os.path.exists(node_path):
                    return node_path
                node_path = os.path.join(pf, "nodejs", name + ".exe")
                if os.path.exists(node_path):
                    return node_path

        # Linux/macOS fallback: check common paths
        common_paths = [
            "/usr/local/bin",
            "/usr/bin",
            "/opt/homebrew/bin",  # macOS Apple Silicon
            "/usr/local/bin",     # macOS Intel
        ]
        for base in common_paths:
            path = os.path.join(base, name)
            if os.path.exists(path) and os.access(path, os.X_OK):
                return path

        return None

    # ──────────────────────────────────────────────────────────────
    # NODE.JS AUTO-INSTALL
    # ──────────────────────────────────────────────────────────────

    def _install_node(self) -> Dict[str, Any]:
        """Install Node.js based on the operating system."""
        system = platform.system()

        console.print()
        console.print("[yellow]⚠️ Node.js is not installed on this system.[/yellow]")
        console.print("[dim]Node.js is required for building and deploying JavaScript projects.[/dim]")

        if not Confirm.ask("[bold]Do you want to install Node.js automatically?[/bold]", default=True):
            return {
                "name": "Node.js",
                "passed": False,
                "details": "Installation declined by user",
            }

        console.print()
        console.print("[cyan]📦 Installing Node.js...[/cyan]")
        console.print("[dim]This may take a few minutes.[/dim]")

        try:
            if system == "Windows":
                success = self._install_node_windows()
            elif system == "Darwin":
                success = self._install_node_macos()
            elif system == "Linux":
                success = self._install_node_linux()
            else:
                console.print(f"[red]❌ Unsupported OS: {system}[/red]")
                console.print("[dim]Please install Node.js manually from https://nodejs.org/[/dim]")
                return {
                    "name": "Node.js",
                    "passed": False,
                    "details": f"Manual installation required for {system}",
                }

            if success:
                console.print()
                console.print("[bold green]✅ Node.js installed successfully![/bold green]")
                console.print("[dim]Please restart your terminal for changes to take effect.[/dim]")
                return {
                    "name": "Node.js",
                    "passed": True,
                    "details": "v22.17.1 (installed)",
                }
            else:
                return {
                    "name": "Node.js",
                    "passed": False,
                    "details": "Installation failed",
                }

        except Exception as e:
            console.print(f"[red]❌ Installation error: {e}[/red]")
            console.print("[dim]Please install Node.js manually from https://nodejs.org/[/dim]")
            return {
                "name": "Node.js",
                "passed": False,
                "details": f"Error: {str(e)}",
            }

    def _install_node_windows(self) -> bool:
        """Download and install Node.js on Windows."""
        try:
            console.print("[dim]Downloading Node.js installer...[/dim]")

            # Node.js LTS version
            version = "22.17.1"
            url = f"https://nodejs.org/dist/v{version}/node-v{version}-x64.msi"
            installer_path = os.path.join(os.environ.get('TEMP', '.'), 'node_installer.msi')

            # Download with progress
            def report_progress(block, block_size, total_size):
                downloaded = block * block_size
                if total_size > 0:
                    percent = min(100, int((downloaded / total_size) * 100))
                    sys.stdout.write(f"\r  Downloading: {percent}%")
                    sys.stdout.flush()

            urllib.request.urlretrieve(url, installer_path, report_progress)
            sys.stdout.write("\n")
            sys.stdout.flush()

            console.print("[dim]Installing Node.js (this may take a minute)...[/dim]")

            # Run installer silently
            result = subprocess.run(
                ["msiexec", "/i", installer_path, "/quiet", "/norestart"],
                capture_output=True,
                text=True,
                timeout=120,
            )

            # Clean up
            if os.path.exists(installer_path):
                os.remove(installer_path)

            if result.returncode != 0:
                console.print(f"[red]Installer exited with code: {result.returncode}[/red]")
                return False

            return True

        except subprocess.TimeoutExpired:
            console.print("[red]Installation timed out.[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Installation failed: {e}[/red]")
            return False

    def _install_node_macos(self) -> bool:
        """Install Node.js on macOS using Homebrew."""
        try:
            # Check if Homebrew is installed
            brew_path = shutil.which("brew")
            if not brew_path:
                console.print("[dim]Homebrew not found. Installing Homebrew...[/dim]")
                subprocess.run(
                    ['/bin/bash', '-c', '$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)'],
                    check=True,
                )

            console.print("[dim]Installing Node.js via Homebrew...[/dim]")
            subprocess.run(["brew", "install", "node"], check=True)

            return True

        except subprocess.CalledProcessError as e:
            console.print(f"[red]Homebrew installation failed: {e}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Installation failed: {e}[/red]")
            return False

    def _install_node_linux(self) -> bool:
        """Install Node.js on Linux using NodeSource."""
        try:
            # Detect package manager
            if shutil.which("apt-get"):
                console.print("[dim]Installing Node.js via apt...[/dim]")
                # Check if curl is available
                if not shutil.which("curl"):
                    subprocess.run(["sudo", "apt-get", "update"], check=True)
                    subprocess.run(["sudo", "apt-get", "install", "-y", "curl"], check=True)

                # Add NodeSource repository
                subprocess.run(
                    ["curl", "-fsSL", "https://deb.nodesource.com/setup_22.x", "-o", "/tmp/nodesource_setup.sh"],
                    check=True,
                )
                subprocess.run(["sudo", "bash", "/tmp/nodesource_setup.sh"], check=True)
                subprocess.run(["sudo", "apt-get", "install", "-y", "nodejs"], check=True)
                subprocess.run(["rm", "-f", "/tmp/nodesource_setup.sh"], check=True)
                return True

            elif shutil.which("yum"):
                console.print("[dim]Installing Node.js via yum...[/dim]")
                subprocess.run(["curl", "-fsSL", "https://rpm.nodesource.com/setup_22.x", "-o", "/tmp/nodesource_setup.sh"], check=True)
                subprocess.run(["sudo", "bash", "/tmp/nodesource_setup.sh"], check=True)
                subprocess.run(["sudo", "yum", "install", "-y", "nodejs"], check=True)
                subprocess.run(["rm", "-f", "/tmp/nodesource_setup.sh"], check=True)
                return True

            else:
                console.print("[red]Unsupported package manager.[/red]")
                console.print("[dim]Please install Node.js manually from https://nodejs.org/[/dim]")
                return False

        except subprocess.CalledProcessError as e:
            console.print(f"[red]Installation failed: {e}[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Installation failed: {e}[/red]")
            return False

    # ──────────────────────────────────────────────────────────────
    # INTERNET CONNECTION
    # ──────────────────────────────────────────────────────────────

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

    # ──────────────────────────────────────────────────────────────
    # PROJECT DETECTION
    # ──────────────────────────────────────────────────────────────

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
                    elif "vite" in deps:
                        result["details"] = "Vite project detected"
                        result["project_type"] = "vite"
                    elif "angular" in deps:
                        result["details"] = "Angular project detected"
                        result["project_type"] = "angular"
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

        # Check for app.py / main.py (Python project)
        elif (self.project_path / "app.py").exists() or (self.project_path / "main.py").exists():
            result["passed"] = True
            result["details"] = "Python application detected"
            result["project_type"] = "python"

        return result


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "EnvironmentChecker",
]