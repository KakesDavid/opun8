"""
Cost Display UI
================

Rich terminal UI for displaying cost estimates.

This module provides:
    - Formatted tables for cost breakdowns
    - Color-coded warnings and alerts
    - Interactive confirmation prompts

Usage:
    from opun8.ui.cost_display import display_cost_estimate

    estimate = estimator.estimate("vercel")
    if display_cost_estimate(estimate):
        # User confirmed — proceed with deployment
        deploy()

Author: OPUN8 Team
Version: 0.1.4
"""

from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from rich import box

from opun8.services.cost_estimator import CostEstimate


console = Console()

# Cost thresholds for warnings
HIGH_COST_THRESHOLD = 100.0


# =============================================================================
# DISPLAY FUNCTIONS
# =============================================================================

def display_cost_estimate(estimate: CostEstimate) -> bool:
    """
    Display a cost estimate and ask for confirmation.

    Args:
        estimate: CostEstimate object

    Returns:
        True if the user confirms, False otherwise

    Example:
        >>> if display_cost_estimate(estimate):
        ...     deploy()
    """
    if estimate.error:
        console.print()
        console.print(Panel(
            f"[red]❌ Error estimating cost: {estimate.error}[/red]",
            border_style="red",
            padding=(1, 2),
            width=60,
        ))
        console.print()
        return False

    if estimate.is_custom_pricing:
        console.print()
        console.print(Panel(
            f"[bold yellow]⚠️ {estimate.plan} Pricing[/bold yellow]\n"
            f"[dim]{estimate.warning or 'Custom pricing applies — contact sales for accurate costs.'}[/dim]",
            border_style="yellow",
            padding=(1, 2),
            width=60,
        ))
        console.print()
        # ✅ FIX: Default to False for safety
        return Confirm.ask("[bold]Proceed with deployment?[/bold]", default=False)

    console.print()
    _print_cost_table(estimate)
    console.print()

    # Show warning if total is high
    if estimate.total and estimate.total > HIGH_COST_THRESHOLD:
        console.print("[bold yellow]⚠️ This deployment costs over $100/month.[/bold yellow]")
        console.print("[dim]Consider optimizing your resources or choosing a different plan.[/dim]")
        console.print()
        # ✅ FIX: Default to False for safety
        return Confirm.ask(
            f"[bold]Deploy to {estimate.platform.capitalize()}?[/bold]",
            default=False
        )

    return Confirm.ask(
        f"[bold]Deploy to {estimate.platform.capitalize()}?[/bold]",
        default=True
    )


def _print_cost_table(estimate: CostEstimate) -> None:
    """
    Print a formatted cost breakdown table.
    """
    # Build the table
    table = Table(
        title=f"[bold]💰 Cost Estimate — {estimate.platform.capitalize()}[/bold]",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        width=60,
    )
    table.add_column("Resource", style="bold white", width=25)
    table.add_column("Monthly Cost", style="bold green", width=20)

    # ✅ FIX: Guard against None breakdown
    breakdown = estimate.breakdown or {}

    # Add breakdown rows
    total_visible = 0.0
    for resource, cost in breakdown.items():
        if cost > 0:
            table.add_row(resource, f"${cost:.2f}")
            total_visible += cost

    # Add total
    if estimate.total is not None:
        table.add_section()

        # ✅ FIX: Note if total doesn't match visible sum
        total_label = "[bold]Total[/bold]"
        total_value = f"[bold green]${estimate.total:.2f}/month[/bold green]"

        if abs(total_visible - estimate.total) > 0.01:
            total_label += " [dim](incl. credits)[/dim]"

        table.add_row(total_label, total_value)

    console.print(table)

    # Show plan info
    if estimate.plan:
        console.print(f"[dim]Plan: {estimate.plan}[/dim]")

    # Show warning if present
    if estimate.warning:
        console.print()
        console.print(f"[yellow]⚠️ {estimate.warning}[/yellow]")


def display_cost_comparison(
    vercel_estimate: Optional[CostEstimate],
    render_estimate: Optional[CostEstimate],
) -> None:
    """
    Display a side-by-side cost comparison of multiple platforms.

    Args:
        vercel_estimate: CostEstimate for Vercel
        render_estimate: CostEstimate for Render

    Example:
        >>> display_cost_comparison(vercel_est, render_est)
    """
    if not vercel_estimate and not render_estimate:
        console.print("[yellow]No estimates available for comparison.[/yellow]")
        return

    console.print()
    console.print(Panel(
        "[bold cyan]💰 Platform Cost Comparison[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
        width=60,
    ))
    console.print()

    # Comparison table
    comparison = Table(
        box=box.ROUNDED,
        border_style="cyan",
        width=60,
    )
    comparison.add_column("Platform", style="bold white", width=15)
    comparison.add_column("Plan", style="dim", width=15)
    comparison.add_column("Monthly Cost", style="bold green", width=15)

    if vercel_estimate and vercel_estimate.is_valid:
        comparison.add_row(
            # ✅ FIX: Use actual platform name from estimate
            vercel_estimate.platform.capitalize(),
            vercel_estimate.plan or "N/A",
            vercel_estimate.formatted_total
        )
    elif vercel_estimate:
        comparison.add_row(
            vercel_estimate.platform.capitalize(),
            "Error",
            f"[red]{vercel_estimate.error or 'N/A'}[/red]"
        )

    if render_estimate and render_estimate.is_valid:
        comparison.add_row(
            render_estimate.platform.capitalize(),
            render_estimate.plan or "N/A",
            render_estimate.formatted_total
        )
    elif render_estimate:
        comparison.add_row(
            render_estimate.platform.capitalize(),
            "Error",
            f"[red]{render_estimate.error or 'N/A'}[/red]"
        )

    console.print(comparison)
    console.print()


def display_savings_tip(estimate: CostEstimate) -> None:
    """
    Display optimization tips based on the estimate.

    Args:
        estimate: CostEstimate object
    """
    if not estimate.is_valid:
        return

    total = estimate.total or 0

    if total == 0:
        console.print("[green]✅ Free tier — no cost![/green]")
        return

    # ✅ FIX: Guard against None breakdown
    breakdown = estimate.breakdown or {}

    tips = []

    # Bandwidth tips
    if breakdown.get("Bandwidth", 0) > 10:
        tips.append(("⚡ High bandwidth cost", "consider optimizing assets or using a CDN"))

    # Build minutes tips
    if breakdown.get("Build Minutes", 0) > 10:
        tips.append(("🔄 High build minutes", "consider caching or incremental builds"))

    # Database tips
    if breakdown.get("Database", 0) > 20:
        tips.append(("📊 High database cost", "consider a smaller instance or optimizing queries"))

    # Compute tips
    if breakdown.get("Compute", 0) > 50:
        tips.append(("💻 High compute cost", "consider scaling down or using free tier"))

    # Workspace tips
    if breakdown.get("Workspace", 0) > 25:
        tips.append(("👥 Workspace plan cost", "consider if you need the extra features"))

    # Seats tips
    if breakdown.get("Seats", 0) > 50:
        tips.append(("👤 High seat cost", "consider reducing team members or using a different plan"))

    if tips:
        console.print()
        console.print("[bold dim]💡 Optimization Tips:[/bold dim]")
        # ✅ FIX: Show all tips, not just first 3
        for emoji, tip in tips:
            console.print(f"  {emoji} {tip}")


def display_free_tier_info(estimate: CostEstimate) -> None:
    """
    Display free tier information if applicable.

    Args:
        estimate: CostEstimate object
    """
    if not estimate.is_valid:
        return

    total = estimate.total or 0

    if total == 0:
        console.print()
        console.print(Panel(
            "[bold green]✅ You're on the free tier![/bold green]\n"
            "[dim]No charges will be incurred for this deployment.[/dim]",
            border_style="green",
            padding=(1, 2),
            width=60,
        ))
    elif total < 10:
        console.print()
        console.print(f"[dim]💡 This deployment is estimated at [green]${total:.2f}/month[/green] — "
                      "likely covered by free tier or minimal cost.[/dim]")
    else:
        pass


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "display_cost_estimate",
    "display_cost_comparison",
    "display_savings_tip",
    "display_free_tier_info",
]