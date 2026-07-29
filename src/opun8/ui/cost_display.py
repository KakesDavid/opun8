"""
Cost Display UI
================

Rich terminal UI for displaying cost estimates.

This module provides:
    - Formatted tables for cost breakdowns
    - Color-coded warnings and alerts
    - Interactive confirmation prompts
    - Netlify credit-based pricing support ✅ NEW

Usage:
    from opun8.ui.cost_display import display_cost_estimate

    estimate = estimator.estimate("vercel")
    if display_cost_estimate(estimate):
        # User confirmed — proceed with deployment
        deploy()

Author: OPUN8 Team
Version: 0.1.5
"""

from typing import Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Confirm
from rich import box
from rich.text import Text
from rich.align import Align

from opun8.services.cost_estimator import CostEstimate


console = Console()

# Cost thresholds for warnings
HIGH_COST_THRESHOLD = 100.0
PANEL_WIDTH = 60


# =============================================================================
# DISPLAY FUNCTIONS
# =============================================================================

def display_cost_estimate(estimate: CostEstimate) -> bool:
    """
    Display a cost estimate and ask for confirmation.

    Supports Vercel, Render, and Netlify cost estimates.

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
            width=PANEL_WIDTH,
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
            width=PANEL_WIDTH,
        ))
        console.print()
        return Confirm.ask("[bold]Proceed with deployment?[/bold]", default=False)

    console.print()
    _print_cost_table(estimate)
    console.print()

    # Show warning if total is high
    if estimate.total and estimate.total > HIGH_COST_THRESHOLD:
        console.print("[bold yellow]⚠️ This deployment costs over $100/month.[/bold yellow]")
        console.print("[dim]Consider optimizing your resources or choosing a different plan.[/dim]")
        console.print()
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

    Supports Vercel (dollar-based), Render (dollar-based),
    and Netlify (credit-based) estimates.
    """
    # Platform-specific display
    if estimate.platform == "netlify":
        _print_netlify_cost_table(estimate)
    else:
        _print_standard_cost_table(estimate)


def _print_standard_cost_table(estimate: CostEstimate) -> None:
    """
    Print a standard dollar-based cost breakdown table.
    Used for Vercel and Render.
    """
    table = Table(
        title=f"[bold]💰 Cost Estimate — {estimate.platform.capitalize()}[/bold]",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        width=PANEL_WIDTH,
    )
    table.add_column("Resource", style="bold white", width=25)
    table.add_column("Monthly Cost", style="bold green", width=20)

    breakdown = estimate.breakdown or {}

    total_visible = 0.0
    for resource, cost in breakdown.items():
        if cost > 0:
            table.add_row(resource, f"${cost:.2f}")
            total_visible += cost

    if estimate.total is not None:
        table.add_section()
        total_label = "[bold]Total[/bold]"
        total_value = f"[bold green]${estimate.total:.2f}/month[/bold green]"

        if abs(total_visible - estimate.total) > 0.01:
            total_label += " [dim](incl. credits)[/dim]"

        table.add_row(total_label, total_value)

    console.print(table)

    if estimate.plan:
        console.print(f"[dim]Plan: {estimate.plan}[/dim]")

    if estimate.warning:
        console.print()
        console.print(f"[yellow]⚠️ {estimate.warning}[/yellow]")


def _print_netlify_cost_table(estimate: CostEstimate) -> None:
    """
    Print a Netlify credit-based cost breakdown table.
    """
    # Get Netlify-specific data
    credits_breakdown = getattr(estimate, 'credits_breakdown', {})
    credits_used = getattr(estimate, 'credits_used', 0)
    plan_credits = getattr(estimate, 'plan_credits', 0)
    overage_credits = getattr(estimate, 'overage_credits', 0)
    recharge_available = getattr(estimate, 'recharge_available', True)

    table = Table(
        title="[bold]💰 Cost Estimate — Netlify[/bold]",
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        width=PANEL_WIDTH,
    )
    table.add_column("Item", style="bold white", width=25)
    table.add_column("Cost / Credits", style="bold green", width=20)

    # Plan cost
    plan_cost = estimate.breakdown.get("Plan", 0)
    if plan_cost > 0:
        table.add_row("Plan", f"${plan_cost:.2f}")
    else:
        table.add_row("Plan", Text("Free", style="green"))

    # Credits section
    if credits_breakdown:
        table.add_section()
        table.add_row(Text("Credits", style="bold dim"), Text("", style="dim"))

        credit_labels = {
            "bandwidth_credits": "Bandwidth",
            "compute_credits": "Compute",
            "web_requests_credits": "Web Requests",
            "deploy_credits": "Production Deploys",
            "ai_credits": "AI Inference",
        }

        for key, label in credit_labels.items():
            if key in credits_breakdown and credits_breakdown[key] > 0:
                table.add_row(
                    label,
                    f"{credits_breakdown[key]:.0f} credits",
                )

        # Total credits
        table.add_row(
            Text("Total Credits Used", style="bold dim"),
            f"{credits_used:.0f} credits",
        )

        # Plan credits
        if plan_credits > 0:
            table.add_row(
                Text("Plan Credits", style="bold dim"),
                f"{plan_credits:.0f} credits",
            )

        # Overage
        if overage_credits > 0:
            if recharge_available:
                table.add_row(
                    Text("Overage (recharge needed)", style="yellow"),
                    f"{overage_credits:.0f} credits",
                )
                if estimate.breakdown.get("Extra Credits"):
                    table.add_row(
                        Text("Recharge Cost", style="yellow"),
                        f"${estimate.breakdown['Extra Credits']:.2f}",
                    )
            else:
                table.add_row(
                    Text("Overage", style="red"),
                    Text(f"{overage_credits:.0f} credits (no recharge)", style="red"),
                )

    # Total
    table.add_section()
    if estimate.total and estimate.total > 0:
        table.add_row(
            Text("Total", style="bold green"),
            Text(f"${estimate.total:.2f}/month", style="bold green"),
        )
    else:
        table.add_row(
            Text("Total", style="bold green"),
            Text("Free", style="green"),
        )

    console.print(table)

    # Plan info
    if estimate.plan:
        console.print(f"[dim]Plan: {estimate.plan} (credit-based)[/dim]")

    # Credit usage percentage
    if credits_used > 0 and plan_credits > 0:
        percent_used = (credits_used / plan_credits) * 100
        if percent_used > 100:
            console.print(f"[yellow]⚠️ You've exceeded your {plan_credits:.0f} monthly credits by {overage_credits:.0f} credits.[/yellow]")
        elif percent_used > 80:
            console.print(f"[yellow]⚠️ You're using {percent_used:.0f}% of your {plan_credits:.0f} monthly credits.[/yellow]")
        else:
            console.print(f"[dim]You're using {percent_used:.0f}% of your {plan_credits:.0f} monthly credits.[/dim]")

    if overage_credits > 0 and recharge_available:
        console.print("[dim]Extra credits can be purchased in recharge blocks.[/dim]")

    if estimate.warning:
        console.print()
        console.print(f"[yellow]⚠️ {estimate.warning}[/yellow]")


def display_cost_comparison(
    vercel_estimate: Optional[CostEstimate],
    render_estimate: Optional[CostEstimate],
    netlify_estimate: Optional[CostEstimate] = None,
) -> None:
    """
    Display a side-by-side cost comparison of multiple platforms.

    Args:
        vercel_estimate: CostEstimate for Vercel
        render_estimate: CostEstimate for Render
        netlify_estimate: CostEstimate for Netlify (optional)

    Example:
        >>> display_cost_comparison(vercel_est, render_est, netlify_est)
    """
    estimates = []
    if vercel_estimate:
        estimates.append(vercel_estimate)
    if render_estimate:
        estimates.append(render_estimate)
    if netlify_estimate:
        estimates.append(netlify_estimate)

    if not estimates:
        console.print("[yellow]No estimates available for comparison.[/yellow]")
        return

    console.print()
    console.print(Panel(
        "[bold cyan]💰 Platform Cost Comparison[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
        width=PANEL_WIDTH,
    ))
    console.print()

    comparison = Table(
        box=box.ROUNDED,
        border_style="cyan",
        width=PANEL_WIDTH,
    )
    comparison.add_column("Platform", style="bold white", width=15)
    comparison.add_column("Plan", style="dim", width=15)
    comparison.add_column("Monthly Cost", style="bold green", width=20)

    for est in estimates:
        if est.is_valid:
            comparison.add_row(
                est.platform.capitalize(),
                est.plan or "N/A",
                est.formatted_total
            )
        else:
            comparison.add_row(
                est.platform.capitalize(),
                "Error",
                f"[red]{est.error or 'N/A'}[/red]"
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

    breakdown = estimate.breakdown or {}
    tips = []

    # Platform-specific tips
    if estimate.platform == "netlify":
        tips = _get_netlify_tips(estimate)
    elif estimate.platform == "vercel":
        tips = _get_vercel_tips(estimate, breakdown)
    else:
        tips = _get_render_tips(estimate, breakdown)

    if tips:
        console.print()
        console.print("[bold dim]💡 Optimization Tips:[/bold dim]")
        for tip in tips:
            console.print(f"  • {tip}")


def _get_vercel_tips(estimate: CostEstimate, breakdown: dict) -> list:
    """Get Vercel-specific savings tips."""
    tips = []

    if breakdown.get("Bandwidth", 0) > 10:
        tips.append("Optimize your assets (images, fonts) to reduce bandwidth usage")
    if breakdown.get("Build Minutes", 0) > 10:
        tips.append("Optimize your build process to reduce build minutes")
    if breakdown.get("Functions", 0) > 5:
        tips.append("Review your serverless function usage and cache where possible")
    if estimate.plan == "Pro" and estimate.total and estimate.total > 100:
        tips.append("Consider Enterprise for high-volume projects (custom pricing)")

    return tips


def _get_render_tips(estimate: CostEstimate, breakdown: dict) -> list:
    """Get Render-specific savings tips."""
    tips = []

    if breakdown.get("Compute", 0) > 50:
        tips.append("Consider using Starter instances for dev/staging environments")
    if breakdown.get("Database", 0) > 20:
        tips.append("Optimize your database usage and consider connection pooling")
    if breakdown.get("Bandwidth", 0) > 10:
        tips.append("Use a CDN for static assets to reduce bandwidth costs")

    return tips


def _get_netlify_tips(estimate: CostEstimate) -> list:
    """Get Netlify-specific savings tips."""
    tips = []

    credits_used = getattr(estimate, 'credits_used', 0)
    plan_credits = getattr(estimate, 'plan_credits', 0)
    overage_credits = getattr(estimate, 'overage_credits', 0)

    if credits_used > 0 and plan_credits > 0:
        percent_used = (credits_used / plan_credits) * 100
        if percent_used > 80:
            tips.append("Consider upgrading to a higher plan if you regularly exceed 80% of your credits")
            tips.append("Optimize your assets and deployment frequency to reduce credit usage")

    if overage_credits > 0:
        tips.append("Reduce deployment frequency or optimize your build process to save credits")
        tips.append("Consider the Personal plan ($9/month) for more credits if you're on Hobby")

    tips.append("Use deploy previews (they're free!) to test changes before production")

    return tips


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
            width=PANEL_WIDTH,
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