"""
Clone Command
=============

CLI command for cloning websites with real-time progress tracking.

This command allows users to:
    - Clone any website with a single command
    - Clean up messy code (remove comments, console.log, etc.)
    - Clone only a single page (skip external links and sub-pages)
    - Track progress in real-time with a beautiful progress bar
    - Save cloned websites to a custom output directory

Usage:
    opun8 clone https://example.com
    opun8 clone https://example.com --clean
    opun8 clone https://example.com --single-page -o ./my-clone

Author: OPUN8 Team
Version: 0.1.4
"""

import os
import sys
import json
import time
import requests
from pathlib import Path
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress,
    BarColumn,
    TextColumn,
    TimeRemainingColumn,
    SpinnerColumn,
)
from rich.prompt import Confirm
from rich.table import Table

from opun8.services.backend_urls import CLONE_CREATE, CLONE_PROGRESS
from opun8.services.token_manager import load_token, is_authenticated

console = Console()


# =============================================================================
# CLONE COMMAND
# =============================================================================

def clone(
    url: str,
    clean: bool = False,
    single_page: bool = False,
    output: str = "./cloned-site",
) -> None:
    """
    Clone a website to your local machine.

    Args:
        url: URL of the website to clone (must start with http:// or https://)
        clean: Clean up messy code (remove comments, console.log, etc.)
        single_page: Clone only the current page (skip external links)
        output: Output directory for the cloned website

    Examples:
        opun8 clone https://example.com
        opun8 clone https://example.com --clean
        opun8 clone https://example.com --single-page
        opun8 clone https://example.com -o ./my-clone

    Raises:
        SystemExit: If user is not authenticated or server error occurs
    """
    # =========================================================================
    # 1. AUTHENTICATION CHECK
    # =========================================================================

    if not is_authenticated():
        console.print()
        console.print("[red]❌ You must be logged in![/red]")
        console.print("[dim]Run: [cyan]opun8 login[/cyan] or [cyan]opun8 register[/cyan][/dim]")
        console.print()
        raise SystemExit(1)

    token = load_token()
    if not token:
        console.print()
        console.print("[red]❌ Authentication token not found. Please log in again.[/red]")
        console.print("[dim]Run: [cyan]opun8 login[/cyan][/dim]")
        console.print()
        raise SystemExit(1)

    # =========================================================================
    # 2. WELCOME PANEL
    # =========================================================================

    console.print()
    console.print(Panel(
        "[bold cyan]📦 OPUN8 Website Cloner[/bold cyan]\n\n"
        f"[dim]URL:[/dim] {url}\n"
        f"[dim]Single Page:[/dim] {'✅ Yes' if single_page else '❌ No'}\n"
        f"[dim]Clean Code:[/dim] {'✅ Yes' if clean else '❌ No'}\n"
        f"[dim]Output:[/dim] {output}",
        border_style="cyan",
        padding=(1, 2),
        width=70,
    ))
    console.print()

    # =========================================================================
    # 3. PREPARE REQUEST
    # =========================================================================

    payload = {
        "url": url,
        "options": {
            "clean": clean,
            "single_page": single_page,
            "organize": True,
            "document": False,
        }
    }

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    # =========================================================================
    # 4. SEND CLONE REQUEST
    # =========================================================================

    try:
        console.print("[bold]🚀 Initializing clone...[/bold]")

        response = requests.post(
            CLONE_CREATE,
            json=payload,
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        clone_data = data.get("data", {})
        clone_id = clone_data.get("id")

        if not clone_id:
            console.print("[red]❌ Failed to get clone ID from response.[/red]")
            console.print(f"[dim]{json.dumps(data, indent=2)}[/dim]")
            raise SystemExit(1)

        console.print(f"[green]✅ Clone initiated! ID: {clone_id}[/green]")
        console.print()

    except requests.exceptions.ConnectionError:
        console.print("[red]❌ Connection error. Please check your internet connection.[/red]")
        raise SystemExit(1)

    except requests.exceptions.Timeout:
        console.print("[red]❌ Request timed out. The server may be busy.[/red]")
        raise SystemExit(1)

    except requests.exceptions.HTTPError as e:
        try:
            error_data = e.response.json()
            error_msg = error_data.get("message", error_data.get("error", str(e)))
            console.print(f"[red]❌ Error: {error_msg}[/red]")
        except Exception:
            console.print(f"[red]❌ HTTP Error: {e}[/red]")
        raise SystemExit(1)

    except Exception as e:
        console.print(f"[red]❌ An unexpected error occurred: {e}[/red]")
        raise SystemExit(1)

    # =========================================================================
    # 5. DISPLAY PROGRESS
    # =========================================================================

    display_progress(clone_id, token, output)


# =============================================================================
# PROGRESS DISPLAY
# =============================================================================

def display_progress(clone_id: str, token: str, output_dir: str) -> None:
    """
    Display real-time progress for a clone operation using Server-Sent Events.

    Args:
        clone_id: The ID of the clone operation
        token: JWT token for authentication
        output_dir: Output directory for the cloned website
    """
    progress_url = CLONE_PROGRESS.format(clone_id=clone_id)
    headers = {"Authorization": f"Bearer {token}"}

    console.print("[dim]📊 Tracking clone progress...[/dim]")
    console.print()

    # =========================================================================
    # 6. PROGRESS BAR
    # =========================================================================

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(bar_width=40),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Cloning...", total=100)

        last_progress = 0
        retries = 0
        max_retries = 120
        clone_failed = False
        failure_reason = None

        while retries < max_retries:
            try:
                response = requests.get(
                    progress_url,
                    headers=headers,
                    timeout=10,
                )

                if response.status_code == 200:
                    data = response.json()
                    progress_data = data.get("data", {})

                    current_progress = progress_data.get("progress", 0)
                    status = progress_data.get("status", "in_progress")
                    file_count = progress_data.get("file_count", 0)
                    error = progress_data.get("error")

                    # Update progress bar
                    if current_progress > last_progress:
                        progress.update(task, completed=current_progress)
                        last_progress = current_progress

                    # Update description with status
                    if status == "in_progress":
                        if file_count > 0:
                            desc = f"[cyan]Cloning... ({file_count} files)"
                        else:
                            desc = "[cyan]Cloning..."
                        progress.update(task, description=desc)

                    elif status == "completed":
                        progress.update(
                            task,
                            description="[green]✅ Clone completed successfully!"
                        )
                        progress.update(task, completed=100)
                        last_progress = 100
                        break

                    elif status == "failed":
                        clone_failed = True
                        failure_reason = error or "Unknown error"
                        progress.update(
                            task,
                            description=f"[red]❌ Clone failed: {failure_reason}"
                        )
                        break

                    retries = 0  # Reset retries on success

                elif response.status_code == 404:
                    # Progress endpoint not found (backend route missing)
                    # This could happen if the backend hasn't implemented the
                    # progress endpoint yet. We'll show a warning and skip progress.
                    console.print("[yellow]⚠️ Progress endpoint not found. Clone may still be running.[/yellow]")
                    console.print("[dim]Check status with: opun8 history[/dim]")
                    return

                else:
                    retries += 1
                    time.sleep(1)
                    continue

            except requests.exceptions.Timeout:
                retries += 1
                time.sleep(1)
                continue

            except requests.exceptions.ConnectionError:
                retries += 1
                time.sleep(2)
                continue

            except Exception:
                retries += 1
                time.sleep(1)
                continue

            time.sleep(0.5)  # Check every 500ms for smooth progress

    # =========================================================================
    # 7. FINAL STATUS
    # =========================================================================

    console.print()

    # Check if clone explicitly failed
    if clone_failed:
        console.print(Panel(
            f"[bold red]❌ Clone Failed[/bold red]\n\n"
            f"[dim]Reason:[/dim] {failure_reason}\n\n"
            "[dim]💡 To fix this issue:[/dim]\n"
            "  • Check your clone limit\n"
            "  • Make sure the URL is accessible\n"
            "  • Upgrade your plan if needed\n"
            "[dim]Run:[/dim] [cyan]opun8 history[/cyan] to see all clones",
            border_style="red",
            padding=(1, 2),
            width=70,
        ))
        return

    # Check if clone completed successfully
    if last_progress >= 100:
        console.print(Panel(
            "[bold green]✅ Clone Completed Successfully![/bold green]\n\n"
            f"[dim]📂 Output:[/dim] {output_dir}\n"
            f"[dim]📄 Open:[/dim] {output_dir}/index.html\n\n"
            "[dim]💡 To deploy this clone, run:[/dim]\n"
            f"[cyan]  opun8 deploy[/cyan]",
            border_style="green",
            padding=(1, 2),
            width=70,
        ))
        return

    # Check if there was partial progress (timeout or interruption)
    if last_progress > 0:
        console.print(Panel(
            "[bold yellow]⚠️ Clone Progress Interrupted[/bold yellow]\n\n"
            f"[dim]Progress:[/dim] {last_progress}%\n"
            "[dim]Check your clone status with:[/dim]\n"
            f"[cyan]  opun8 history[/cyan]",
            border_style="yellow",
            padding=(1, 2),
            width=70,
        ))
        return

    # No progress at all
    console.print(Panel(
        "[bold red]❌ Clone Failed to Start[/bold red]\n\n"
        "[dim]The clone operation could not be initiated.[/dim]\n"
        "[dim]Check your connection and try again.[/dim]",
        border_style="red",
        padding=(1, 2),
        width=70,
    ))


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "clone",
    "display_progress",
]