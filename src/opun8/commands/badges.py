"""
Badges command - View your badge progress and achievements.

This module provides:
    - View all available badges and their unlock status
    - Track progress toward the next badge
    - Show celebration for newly unlocked badges

`show_badge_notification` is the single shared entry point for rendering a
"badge unlocked" panel. It is called from the deploy command and from the
history command's redeploy flow, so the celebration UI only lives in one
place instead of being duplicated across files.
"""

from __future__ import annotations

import typer
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from opun8.services.deployment_history import (
    get_deployment_count,
    get_badge_info,
    get_platform_stats,
    get_platform_icon,
)
from opun8.ui import messages as msg

console = Console()

PANEL_WIDTH = 60

# ──────────────────────────────────────────────────────────────
# BADGE DEFINITIONS
# ──────────────────────────────────────────────────────────────

BADGE_LEVELS = [
    {"level": 1, "emoji": "🥉", "name": "First Launch", "deployments": 1},
    {"level": 2, "emoji": "🥉", "name": "Apprentice", "deployments": 3},
    {"level": 3, "emoji": "🥈", "name": "Builder", "deployments": 5},
    {"level": 4, "emoji": "🥈", "name": "Ship Captain", "deployments": 10},
    {"level": 5, "emoji": "🥇", "name": "Deployment Master", "deployments": 25},
    {"level": 6, "emoji": "🥇", "name": "Shipping Machine", "deployments": 50},
    {"level": 7, "emoji": "🏆", "name": "Opun8 Legend", "deployments": 100},
]


# ──────────────────────────────────────────────────────────────
# PLATFORM ICONS
# ──────────────────────────────────────────────────────────────

PLATFORM_ICONS = {
    "vercel": "▲",
    "netlify": "📦",
    "render": "☁️",
}


def badges() -> None:
    """
    Show your badge progress and achievements.
    """
    try:
        _show_badges_screen()
    except KeyboardInterrupt:
        console.print("\n[yellow]⚠️  Operation cancelled.[/yellow]")
        raise typer.Exit(0)
    except Exception as e:
        console.print_exception()
        msg.error(
            f"Unexpected error: {e}",
            suggestion="Try again or run `opun8 help` for assistance.",
        )
        raise typer.Exit(1)


def _get_unlocked_badge_names(count: int) -> List[str]:
    """
    Compute which badges are unlocked from the deployment count directly,
    rather than depending on a separate persisted "unlocked" list that can
    drift out of sync with `count`. BADGE_LEVELS is the single source of
    truth for thresholds.
    """
    return [b["name"] for b in BADGE_LEVELS if count >= b["deployments"]]


def _show_badges_screen() -> None:
    """Display the main badges screen."""
    count = get_deployment_count()
    unlocked = _get_unlocked_badge_names(count)
    platform_stats = get_platform_stats()

    console.print()
    console.print(Panel(
        "[bold cyan]🏅 Badge Progress[/bold cyan]\n"
        "[dim]Track your achievements as you deploy more projects.[/dim]",
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))

    badge = get_badge_info(count)
    console.print()
    console.print(f"[dim]Current: {badge['emoji']} [bold]{badge['name']}[/bold] ({count} deployments)[/dim]")

    if badge["next"]:
        next_badge = get_badge_info(badge["next"])
        prev_threshold = _previous_threshold(badge["level"])
        span = badge["next"] - prev_threshold
        progress_pct = min(100, int(((count - prev_threshold) / span) * 100)) if span > 0 else 100

        console.print()
        console.print(
            f"[dim]Next milestone: {next_badge['emoji']} "
            f"[cyan]{next_badge['name']}[/cyan] ({badge['next']} deployments)[/dim]"
        )
        _render_progress_bar(progress_pct)

        remaining = badge["next"] - count
        console.print(f"[dim]{remaining} more deployment(s) to unlock[/dim]")
    else:
        console.print()
        console.print("[bold yellow]🏆 MAX LEVEL REACHED![/bold yellow]")
        console.print("[dim]You've unlocked all badges. You're a true Opun8 Legend![/dim]")

    # ──────────────────────────────────────────────────────────────
    # DEPLOYMENT STATS BY PLATFORM
    # ──────────────────────────────────────────────────────────────

    if platform_stats:
        console.print()
        console.print("[bold]📊 Deployments by Platform:[/bold]")
        console.print()
        for platform, count in sorted(platform_stats.items(), key=lambda x: x[1], reverse=True):
            icon = PLATFORM_ICONS.get(platform.lower(), "●")
            console.print(f"  {icon} [dim]{platform.capitalize()}:[/dim] [white]{count}[/white]")
        console.print()

    console.print()
    _display_badge_table(count)

    console.print()
    console.print(f"[dim]📊 Unlocked: {len(unlocked)} of {len(BADGE_LEVELS)} badges[/dim]")


def _previous_threshold(level: int) -> int:
    """Deployment count required for the badge just below `level`, or 0."""
    for b in BADGE_LEVELS:
        if b["level"] == level - 1:
            return b["deployments"]
    return 0


def _render_progress_bar(progress_pct: int) -> None:
    """Render a progress bar for badge progress."""
    bar_length = 30
    filled = int((progress_pct / 100) * bar_length)
    empty = bar_length - filled

    bar = "█" * filled + "░" * empty
    console.print(f"[cyan]  {bar}[/cyan] [dim]{progress_pct}%[/dim]")


def _display_badge_table(count: int) -> None:
    """Display all badges with their unlock status."""
    table = Table(
        title="Badge Collection",
        border_style="cyan",
        title_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Badge", style="bold", width=6)
    table.add_column("Name", style="white", width=20)
    table.add_column("Status", style="bold", width=12)
    table.add_column("Requirement", style="dim", width=15)

    for badge_level in BADGE_LEVELS:
        required = badge_level["deployments"]
        is_unlocked = count >= required

        if is_unlocked:
            status = "[green]✅ Unlocked[/green]"
            status_emoji = badge_level["emoji"]
            progress_text = "✓"
        else:
            status = "[dim]❌ Locked[/dim]"
            status_emoji = "⬜"
            progress_text = f"{count}/{required}"

        table.add_row(status_emoji, badge_level["name"], status, progress_text)

    console.print(table)


def show_badge_notification(badge_info: Optional[Dict[str, Any]]) -> None:
    """
    Display a badge-unlock celebration panel.

    Args:
        badge_info: The badge dict returned when a NEW badge was just
            unlocked (e.g. the "badge_unlocked" value returned by
            add_deployment, or the result of check_badge_progress).
            Pass None (or nothing) to indicate no new badge was unlocked
            this time — the function is then a no-op, so callers don't
            need to guard the call site with an `if` themselves.
    """
    if not badge_info:
        return

    next_text = (
        f"{badge_info['next']} deployments" if badge_info.get("next") else "Max level reached! 🏆"
    )

    console.print()
    console.print(Panel(
        f"[bold yellow]🏆 Badge Unlocked![/bold yellow]\n\n"
        f"{badge_info['emoji']} [bold]{badge_info['name']}[/bold]\n\n"
        f"[dim]You've reached {badge_info['progress']} deployments![/dim]\n"
        f"[dim]Next milestone: [cyan]{next_text}[/cyan][/dim]",
        border_style="yellow",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))