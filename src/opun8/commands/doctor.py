"""
Doctor command - Check if environment is ready.

✅ UPDATED: Partner tone UI with friendly messages and Node.js auto-download.
✅ FIXED: shutil scoping bug, Windows path bug, temp cleanup, PATH integration.
"""

from pathlib import Path
from rich.table import Table
from rich.console import Console
from rich.panel import Panel
from rich import box
import platform
import shutil
import subprocess
import tempfile
import zipfile
import tarfile
import os
import requests
from typing import Optional

from opun8.core.environment import EnvironmentChecker
from opun8.ui.messages import (
    _sym,
    _emoji_or_empty,
    _escape_text,
    _safe_prompt,
    success,
    info,
    warning,
    error,
)

console = Console()

# ──────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────

OPUN8_HOME = Path.home() / ".opun8"
NODE_HOME = OPUN8_HOME / "bin" / "node"

if platform.system() == "Windows":
    NODE_BIN = NODE_HOME / "node.exe"
else:
    NODE_BIN = NODE_HOME / "bin" / "node"

NODE_VERSION = "20.17.0"
NODE_URL_WINDOWS = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"
NODE_URL_MACOS = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-darwin-x64.tar.gz"
NODE_URL_LINUX = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-linux-x64.tar.gz"


def _add_to_path(path: Path) -> None:
    """Add a directory to the current process's PATH."""
    bin_dir = str(path.parent)
    current_path = os.environ.get("PATH", "")
    if bin_dir not in current_path:
        os.environ["PATH"] = f"{bin_dir}{os.pathsep}{current_path}"


def _get_node_url() -> str:
    system = platform.system()
    if system == "Windows":
        return NODE_URL_WINDOWS
    elif system == "Darwin":
        return NODE_URL_MACOS
    else:
        return NODE_URL_LINUX


def _is_node_installed() -> bool:
    # Check OPUN8-managed installation first
    if NODE_BIN.exists():
        try:
            result = subprocess.run(
                [str(NODE_BIN), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    # Check global installation
    if shutil.which("node"):
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


def _get_node_version() -> Optional[str]:
    if NODE_BIN.exists():
        try:
            result = subprocess.run(
                [str(NODE_BIN), "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    if shutil.which("node"):
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass

    return None


def _download_with_progress(url: str, dest_path: Path) -> bool:
    try:
        from rich.progress import (
            Progress,
            SpinnerColumn,
            TextColumn,
            BarColumn,
            TaskProgressColumn,
        )

        response = requests.get(url, stream=True, timeout=30)
        response.raise_for_status()

        total_size = int(response.headers.get("content-length", 0))

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(bar_width=30),
            TaskProgressColumn(),
            console=console,
            transient=False,
        ) as progress:
            task_total = total_size if total_size > 0 else 100
            task = progress.add_task(
                f"[cyan]{_emoji_or_empty('download')}Downloading Node.js {NODE_VERSION}...",
                total=task_total,
            )

            with open(dest_path, "wb") as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            progress.update(task, completed=min(downloaded, total_size))
                        else:
                            current = progress.tasks[task].completed
                            if current < 100:
                                progress.update(task, advance=1)

            progress.update(task, completed=task_total, description="[green]✅ Download complete!")

        return True

    except Exception as e:
        if dest_path.exists():
            try:
                dest_path.unlink()
            except Exception:
                pass
        error(f"Failed to download Node.js: {_escape_text(str(e))}")
        return False


def _extract_nodejs(archive_path: Path) -> bool:
    try:
        bin_dir = OPUN8_HOME / "bin"
        bin_dir.mkdir(parents=True, exist_ok=True)

        console.print(f"[dim]{_emoji_or_empty('box')}Extracting Node.js...[/dim]")

        temp_dir = Path(tempfile.mkdtemp(prefix="opun8_node_"))
        extracted = None

        try:
            if archive_path.suffix == ".zip":
                with zipfile.ZipFile(archive_path, "r") as zf:
                    zf.extractall(temp_dir)
            else:
                with tarfile.open(archive_path, "r:gz") as tar:
                    tar.extractall(temp_dir)

            extracted_folders = [d for d in temp_dir.iterdir() if d.is_dir()]
            if extracted_folders:
                extracted = extracted_folders[0]
            else:
                error("Could not find extracted Node.js folder.")
                return False

            if NODE_HOME.exists():
                shutil.rmtree(NODE_HOME)

            shutil.move(str(extracted), str(NODE_HOME))

            if platform.system() != "Windows":
                node_exe = NODE_HOME / "bin" / "node"
                if node_exe.exists():
                    node_exe.chmod(0o755)

            _add_to_path(NODE_BIN)

            return True

        finally:
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
            if archive_path.exists():
                archive_path.unlink(missing_ok=True)

    except Exception as e:
        error(f"Failed to extract Node.js: {_escape_text(str(e))}")
        return False


def _install_nodejs() -> bool:
    console.print()
    console.print(Panel(
        f"[bold yellow]{_sym('warning')} Hmm, Node.js is missing, partner! {_sym('thinking')}[/bold yellow]\n\n"
        f"[white]I need Node.js to build and deploy your project.[/white]\n"
        f"[dim]Don't worry — I can download it for you automatically![/dim]\n\n"
        f"[dim]I'll install it at: {NODE_HOME}[/dim]\n"
        f"[dim]This is completely safe and requires no admin rights![/dim]",
        border_style="yellow",
        padding=(1, 2),
        width=60,
    ))
    console.print()

    console.print("[bold]What would you like to do?[/bold]")
    console.print()
    console.print(f"  [bold cyan]1[/] {_emoji_or_empty('download')}[white]YES, download it for me![/white]")
    console.print(f"  [bold cyan]2[/] {_emoji_or_empty('skip')}[white]No, I'll install it myself[/white]")
    console.print()
    console.print(f"[dim]{_emoji_or_empty('bulb')}If you choose 'No', I'll show you how to install it manually.[/dim]")
    console.print()

    choice = _safe_prompt(
        f"[bold cyan]{_emoji_or_empty('arrow')}[/] Select an option",
        choices=["1", "2"],
        default="1",
    )

    if choice == "1":
        console.print()
        console.print(f"[bold green]{_emoji_or_empty('heart')} LET'S GET YOU SET UP, PARTNER! {_emoji_or_empty('rocket')}[/bold green]")
        console.print()

        OPUN8_HOME.mkdir(parents=True, exist_ok=True)

        url = _get_node_url()
        ext = "zip" if platform.system() == "Windows" else "tar.gz"
        archive_path = OPUN8_HOME / f"node-{NODE_VERSION}.{ext}"

        console.print(f"[dim]Downloading from: {url}[/dim]")
        console.print()

        if not _download_with_progress(url, archive_path):
            return False

        if not _extract_nodejs(archive_path):
            return False

        if _is_node_installed():
            version = _get_node_version()
            console.print()
            success(f"🎉 Node.js {_escape_text(version or NODE_VERSION)} is ready to roll, partner!")
            console.print(f"[dim]I've installed it at {NODE_HOME}[/dim]")
            console.print()
            return True
        else:
            error("Node.js installation verification failed. Please install it manually.")
            return False

    else:
        console.print()
        console.print(f"[dim]{_emoji_or_empty('bulb')}You can install Node.js from: [cyan]https://nodejs.org[/cyan][/dim]")
        console.print("[dim]After installing, run 'opun8 doctor' again to verify.[/dim]")
        console.print()
        return False


def doctor():
    console.print()
    console.print(Panel(
        f"[bold cyan]{_emoji_or_empty('search')} Opun8 Doctor — Let's check your setup![/bold cyan]\n"
        "[dim]I'll make sure everything is ready for us to launch your site![/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()

    checker = EnvironmentChecker()
    results = checker.check_all()

    table = Table(
        title="🔧 Environment Status",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        width=60,
    )
    table.add_column("Component", style="bold white", width=16)
    table.add_column("Status", style="bold", width=12)
    table.add_column("Details", style="dim", width=30)

    for key, result in results.items():
        status_text = "[green]✅ OK[/green]" if result["passed"] else "[red]❌ Missing[/red]"
        table.add_row(result["name"], status_text, _escape_text(result["details"]))

    console.print(table)

    node_installed = _is_node_installed()
    if not node_installed:
        node_in_results = any(r["name"] == "Node.js" for r in results.values())
        if not node_in_results:
            console.print(f"[yellow]{_sym('warning')} Node.js: [red]❌ Missing[/red][/yellow]")

        if _install_nodejs():
            node_installed = _is_node_installed()
        else:
            console.print()
            warning("Node.js is still missing. Some features may not work.")

    all_passed = all(r["passed"] for r in results.values()) and node_installed

    if all_passed:
        console.print()
        console.print(Panel(
            f"[bold green]{_emoji_or_empty('party')} EVERYTHING LOOKS GREAT, PARTNER! {_emoji_or_empty('party')}[/bold green]\n\n"
            "[white]You're ready to deploy! Let's launch your site! 🚀[/white]\n\n"
            f"[dim]{_emoji_or_empty('point')}Run [cyan]opun8 deploy[/cyan] to get started![/dim]",
            border_style="green",
            padding=(1, 2),
            width=60,
        ))
    else:
        console.print()
        console.print(Panel(
            f"[bold yellow]{_emoji_or_empty('warning')} SOME COMPONENTS ARE MISSING, PARTNER![/bold yellow]\n\n"
            f"[white]Don't worry — I can help you get set up![/white]\n\n"
            f"[dim]{_emoji_or_empty('bulb')}Install the missing components and run [cyan]opun8 doctor[/cyan] again.[/dim]",
            border_style="yellow",
            padding=(1, 2),
            width=60,
        ))

    console.print()