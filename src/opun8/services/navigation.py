"""
Navigation service for Opun8.
Provides folder selection using native system file picker.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from rich.console import Console

console = Console()


def open_folder_picker() -> Optional[Path]:
    """
    Open the native system folder picker dialog.
    
    Returns:
        Selected folder path, or None if cancelled.
    
    Supported platforms:
        - Windows: Uses tkinter.filedialog.askdirectory()
        - macOS: Uses osascript (AppleScript)
        - Linux: Uses zenity or kdialog
    """
    try:
        if sys.platform == "win32":
            return _windows_picker()
        elif sys.platform == "darwin":
            return _macos_picker()
        else:
            return _linux_picker()
    except Exception as e:
        console.print(f"[red]❌ Failed to open folder picker: {e}[/red]")
        console.print("[dim]Falling back to terminal input...[/dim]")
        return _fallback_picker()


def _windows_picker() -> Optional[Path]:
    """Windows native folder picker using tkinter."""
    try:
        import tkinter as tk
        from tkinter import filedialog
        
        root = tk.Tk()
        root.withdraw()  # Hide the main window
        root.attributes('-topmost', True)
        
        folder_path = filedialog.askdirectory(
            title="Select Project Folder to Deploy",
            mustexist=True,
        )
        
        root.destroy()
        
        if folder_path:
            return Path(folder_path)
        return None
        
    except ImportError:
        console.print("[yellow]⚠️  tkinter not available. Falling back to terminal.[/yellow]")
        return _fallback_picker()
    except Exception as e:
        console.print(f"[red]❌ Folder picker error: {e}[/red]")
        return _fallback_picker()


def _macos_picker() -> Optional[Path]:
    """macOS native folder picker using AppleScript."""
    script = '''
    tell application "System Events"
        activate
        set folderPath to choose folder with prompt "Select Project Folder to Deploy"
        if folderPath is not false then
            return POSIX path of folderPath
        end if
    end tell
    '''
    
    try:
        result = subprocess.run(
            ['osascript', '-e', script],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
        return None
        
    except Exception as e:
        console.print(f"[red]❌ Folder picker error: {e}[/red]")
        return _fallback_picker()


def _linux_picker() -> Optional[Path]:
    """Linux native folder picker using zenity or kdialog."""
    # Try zenity (GNOME)
    try:
        result = subprocess.run(
            [
                'zenity',
                '--file-selection',
                '--directory',
                '--title=Select Project Folder to Deploy',
                '--filename=' + str(Path.cwd()),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
            
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # Try kdialog (KDE)
    try:
        result = subprocess.run(
            [
                'kdialog',
                '--getexistingdirectory',
                str(Path.cwd()),
                '--title=Select Project Folder to Deploy',
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            return Path(result.stdout.strip())
            
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    console.print("[yellow]⚠️  No GUI folder picker found. Using terminal fallback.[/yellow]")
    return _fallback_picker()


def _fallback_picker() -> Optional[Path]:
    """Fallback: terminal-based folder selection."""
    console.print()
    console.print("[bold]📁 Enter the path to your project folder:[/bold]")
    console.print(f"[dim]Current directory: {Path.cwd()}[/dim]")
    console.print("[dim](Press Enter to use current directory)[/dim]")
    console.print()
    
    try:
        path_input = input("[bold cyan]➜[/] Path: ").strip()
        
        if not path_input:
            return Path.cwd()
        
        target = Path(path_input).expanduser().resolve()
        
        if target.exists() and target.is_dir():
            return target
        
        console.print(f"[red]❌ Invalid path: {path_input}[/red]")
        return None
        
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]⚠️  Cancelled.[/yellow]")
        return None


def browse_to_folder() -> Optional[Path]:
    """
    Open native folder picker for selecting a project directory.
    
    Returns:
        Path of the selected folder, or None if cancelled.
    
    Example:
        >>> selected = browse_to_folder()
        >>> if selected:
        ...     print(f"Selected: {selected}")
    """
    console.print()
    console.print("[bold cyan]📂 Opening folder picker...[/bold cyan]")
    
    result = open_folder_picker()
    
    if result:
        console.print(f"[green]✅ Selected: {result}[/green]")
    else:
        console.print("[yellow]⚠️  No folder selected.[/yellow]")
    
    return result


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "open_folder_picker",
    "browse_to_folder",
]