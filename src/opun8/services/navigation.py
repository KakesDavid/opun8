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


def browse_to_folder() -> Optional[Path]:
    """
    Interactive folder browser for selecting a project directory.

    Allows the user to:
        - Navigate through directories
        - Go up one level
        - Select a folder
        - Cancel

    Returns:
        Path of the selected folder, or None if cancelled.

    Example:
        >>> selected = browse_to_folder()
        >>> if selected:
        ...     print(f"Selected: {selected}")
    """
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt
    from rich.table import Table

    console = Console()
    current_path = Path.cwd()
    PANEL_WIDTH = 60

    while True:
        # Clear screen for cleaner UX
        os.system('cls' if os.name == 'nt' else 'clear')

        # Show current directory
        console.print()
        console.print(Panel(
            f"[bold cyan]📂 Select Project Folder[/bold cyan]\n"
            f"[dim]Current: {current_path}[/dim]",
            border_style="cyan",
            padding=(1, 2),
            width=PANEL_WIDTH,
        ))
        console.print()

        # List items
        folders, files = list_items(str(current_path))

        # Show navigation options
        console.print("[bold]Navigation:[/bold]")
        console.print("  [bold cyan]..[/]  [white]Go up one level[/white]")

        if folders:
            console.print()
            console.print("[bold]📁 Folders:[/bold]")
            for i, folder in enumerate(folders[:20], 1):
                console.print(f"  [bold cyan]{i:2}[/]  [white]{folder}[/white]")
            if len(folders) > 20:
                console.print(f"  [dim]... and {len(folders) - 20} more[/dim]")

        if files:
            console.print()
            console.print("[bold]📄 Files:[/bold] [dim](for reference)[/dim]")
            for i, file in enumerate(files[:10], 1):
                console.print(f"  [dim]{i:2}[/]  {file}")
            if len(files) > 10:
                console.print(f"  [dim]... and {len(files) - 10} more[/dim]")

        console.print()
        console.print("[bold]Options:[/bold]")
        console.print("  [bold cyan]0[/]  [green]Select this folder[/green]")
        console.print("  [bold cyan]..[/]  [yellow]Go up one level[/yellow]")
        console.print("  [bold cyan]q[/]   [red]Cancel[/red]")
        console.print()

        choice = Prompt.ask(
            "[bold cyan]➜[/] Enter folder number, '..' to go up, 'q' to cancel",
            default="0",
            show_choices=False,
        )

        if choice.lower() == 'q':
            console.print("[yellow]Cancelled.[/yellow]")
            return None

        if choice == '..':
            if current_path.parent == current_path:
                console.print("[yellow]Already at root.[/yellow]")
                # Pause so user can see the message
                Prompt.ask("[dim]Press Enter to continue...[/dim]", default="")
                continue
            current_path = current_path.parent
            continue

        try:
            idx = int(choice)
            if idx == 0:
                # Select current folder
                console.print(f"[green]✅ Selected: {current_path}[/green]")
                return current_path

            if 1 <= idx <= len(folders):
                selected_folder = folders[idx - 1]
                new_path = current_path / selected_folder
                if new_path.exists() and new_path.is_dir():
                    current_path = new_path
                else:
                    console.print("[red]❌ Invalid folder.[/red]")
                    Prompt.ask("[dim]Press Enter to continue...[/dim]", default="")
            else:
                console.print("[red]❌ Invalid selection.[/red]")
                Prompt.ask("[dim]Press Enter to continue...[/dim]", default="")
        except ValueError:
            console.print("[red]❌ Please enter a number, '..', or 'q'.[/red]")
            Prompt.ask("[dim]Press Enter to continue...[/dim]", default="")


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "get_current_directory",
    "change_directory",
    "go_up",
    "list_items",
    "get_drive_list",
    "is_valid_path",
    "browse_to_folder",
]