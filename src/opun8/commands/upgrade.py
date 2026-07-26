"""
Upgrade Command
===============

CLI command for upgrading OPUN8 subscription plans.

This command allows users to:
    - Upgrade from Free to Starter plan ($5/month)
    - Upgrade from Free to Pro plan ($15/month)
    - View available plans and pricing
    - See current plan status
    - Downgrade with explicit confirmation (if applicable)

Usage:
    opun8 upgrade starter
    opun8 upgrade pro
    opun8 upgrade --status
    opun8 upgrade starter --downgrade  # Explicit consent for downgrade

Author: OPUN8 Team
Version: 0.1.4
"""

import json
import requests
from typing import Optional
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Confirm
from rich import box

from opun8.services.backend_urls import PAYMENT_CHECKOUT, SUBSCRIPTION_STATUS
from opun8.services.token_manager import load_token, is_authenticated

console = Console()

# Plan hierarchy for upgrade/downgrade checking
PLAN_RANK = {
    "free": 0,
    "starter": 1,
    "pro": 2,
}


# =============================================================================
# UPGRADE COMMAND
# =============================================================================

def upgrade(
    plan_arg: Optional[str] = None,
    force: bool = False,
    downgrade: bool = False,
) -> None:
    """
    Upgrade your OPUN8 subscription plan.

    Args:
        plan_arg: Plan to upgrade to (starter, pro)
        force: Skip confirmation prompt
        downgrade: Acknowledge that you are downgrading

    Examples:
        opun8 upgrade starter
        opun8 upgrade pro
        opun8 upgrade --status
        opun8 upgrade starter --downgrade  # Explicit consent for downgrade

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
    # 2. CHECK CURRENT STATUS
    # =========================================================================

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.get(SUBSCRIPTION_STATUS, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        status_data = data.get("data", {})
        current_plan = status_data.get("plan", "free")

    except Exception as e:
        console.print(f"[red]❌ Failed to fetch current plan: {e}[/red]")
        raise SystemExit(1)

    # =========================================================================
    # 3. SHOW STATUS (if no plan specified)
    # =========================================================================

    if not plan_arg:
        show_status(status_data)
        return

    # =========================================================================
    # 4. VALIDATE PLAN
    # =========================================================================

    plan = plan_arg.lower().strip()
    if plan not in ["starter", "pro"]:
        console.print()
        console.print(f"[red]❌ Invalid plan: '{plan_arg}'[/red]")
        console.print("[dim]Available plans: [cyan]starter[/cyan], [cyan]pro[/cyan][/dim]")
        console.print()
        raise SystemExit(1)

    if plan == current_plan:
        console.print()
        console.print(f"[yellow]⚠️ You are already on the {plan} plan![/yellow]")
        console.print("[dim]Run [cyan]opun8 upgrade --status[/cyan] to see your current plan.[/dim]")
        console.print()
        return

    # =========================================================================
    # 5. CHECK FOR DOWNGRADE
    # =========================================================================

    is_downgrade = PLAN_RANK[plan] < PLAN_RANK[current_plan]

    if is_downgrade and not downgrade:
        console.print()
        console.print(Panel(
            "[bold yellow]⚠️ This is a DOWNGRADE[/bold yellow]\n\n"
            f"[dim]Current Plan:[/dim] [bold]{current_plan.upper()}[/bold]\n"
            f"[dim]Target Plan:[/dim] [bold]{plan.upper()}[/bold]\n\n"
            "[bold]Downgrading will reduce your clone limits and features.[/bold]\n"
            "[dim]You will lose access to:\n"
            f"  • {get_feature_differences(current_plan, plan)}\n\n"
            "[dim]To confirm, add the [cyan]--downgrade[/cyan] flag:[/dim]\n"
            f"[cyan]  opun8 upgrade {plan} --downgrade[/cyan]",
            border_style="yellow",
            padding=(1, 2),
            width=70,
        ))
        console.print()
        return

    if is_downgrade and downgrade:
        console.print()
        console.print("[bold yellow]⚠️ You are downgrading your plan.[/bold yellow]")
        if not force:
            if not Confirm.ask("[bold]Are you sure you want to downgrade?[/bold]"):
                console.print("[dim]Downgrade cancelled.[/dim]")
                return

    # =========================================================================
    # 6. SHOW PLAN DETAILS
    # =========================================================================

    show_plan_details(plan, current_plan, is_downgrade)

    # =========================================================================
    # 7. CONFIRM UPGRADE/DOWNGRADE
    # =========================================================================

    if not force:
        action = "downgrade" if is_downgrade else "upgrade"
        if not Confirm.ask(f"\n[bold]Continue with {action}?[/bold]"):
            console.print(f"[dim]{action.capitalize()} cancelled.[/dim]")
            return

    # =========================================================================
    # 8. PROCESS PLAN CHANGE
    # =========================================================================

    console.print()
    action = "downgrade" if is_downgrade else "upgrade"
    console.print(f"[bold]🔄 Processing {action}...[/bold]")

    try:
        response = requests.post(
            PAYMENT_CHECKOUT,
            json={"plan": plan, "action": action},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        checkout_data = data.get("data", {})
        checkout_url = checkout_data.get("authorization_url")
        reference = checkout_data.get("reference")

        if checkout_url:
            console.print()
            console.print(Panel(
                f"[bold green]✅ {action.capitalize()} initialized![/bold green]\n\n"
                f"[dim]Reference:[/dim] {reference}\n"
                f"[dim]Plan:[/dim] {plan}\n\n"
                "[bold]🔗 Please complete payment at:[/bold]",
                border_style="green",
                padding=(1, 2),
                width=70,
            ))
            console.print()
            console.print(f"[cyan]{checkout_url}[/cyan]")
            console.print()
            console.print("[dim]After payment, your plan will be updated automatically.[/dim]")
            console.print("[dim]You can check your status with: [cyan]opun8 upgrade --status[/cyan][/dim]")
        else:
            console.print("[yellow]⚠️ Payment URL not returned. Please check your account status.[/yellow]")

    except requests.exceptions.HTTPError as e:
        try:
            error_data = e.response.json()
            error_msg = error_data.get("message", error_data.get("error", str(e)))
            console.print(f"[red]❌ Plan change failed: {error_msg}[/red]")
        except Exception:
            console.print(f"[red]❌ Plan change failed: {e}[/red]")
        raise SystemExit(1)

    except Exception as e:
        console.print(f"[red]❌ An unexpected error occurred: {e}[/red]")
        raise SystemExit(1)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_feature_differences(current_plan: str, target_plan: str) -> str:
    """Get a human-readable list of features that will be lost on downgrade."""
    feature_diffs = []

    if current_plan == "pro" and target_plan == "starter":
        feature_diffs = [
            "Backend cloning (Node.js, Python, etc.)",
            "Custom domain support",
            "Premium support",
            "Team collaboration features",
        ]
    elif current_plan == "pro" and target_plan == "free":
        feature_diffs = [
            "React and Vue cloning",
            "Backend cloning",
            "Custom domain support",
            "Premium support",
            "Team collaboration features",
            "Auto-documentation generation",
        ]
    elif current_plan == "starter" and target_plan == "free":
        feature_diffs = [
            "React and Vue cloning",
            "Advanced code cleanup",
            "Auto-documentation generation",
            "Priority support",
        ]

    return ", ".join(feature_diffs) if feature_diffs else "No features lost"


def show_status(status_data: dict) -> None:
    """Display current subscription status."""
    plan = status_data.get("plan", "free")
    clones_used = status_data.get("clones_used", 0)
    clones_limit = status_data.get("clones_limit", 3)
    clones_remaining = status_data.get("clones_remaining", 3)
    is_active = status_data.get("is_active", False)  # Default to False for safety
    expires_at = status_data.get("expires_at")
    payment_method = status_data.get("payment_method", "N/A")

    console.print()
    console.print(Panel(
        "[bold cyan]📊 Your OPUN8 Subscription[/bold cyan]\n\n"
        f"[dim]Plan:[/dim] [bold]{plan.upper()}[/bold]\n"
        f"[dim]Status:[/dim] {'✅ Active' if is_active else '❌ Inactive / Unknown'}\n"
        f"[dim]Clones Used:[/dim] {clones_used}/{clones_limit}\n"
        f"[dim]Clones Remaining:[/dim] {clones_remaining}\n"
        f"[dim]Payment Method:[/dim] {payment_method}\n"
        f"[dim]Expires:[/dim] {expires_at or 'N/A'}",
        border_style="cyan",
        padding=(1, 2),
        width=70,
    ))
    console.print()

    # Show upgrade prompt for free users
    if plan == "free":
        console.print("[dim]💡 Upgrade to unlock more clones and features:[/dim]")
        console.print("  [cyan]opun8 upgrade starter[/cyan]  → 20 clones/month ($5/mo)")
        console.print("  [cyan]opun8 upgrade pro[/cyan]       → 100 clones/month ($15/mo)")
        console.print()

    # Show plan features table
    show_features_table()


def show_plan_details(plan: str, current_plan: str, is_downgrade: bool = False) -> None:
    """Display plan details before plan change."""
    plan_details = {
        "starter": {
            "price": "$5/month",
            "clones": "20 clones/month",
            "emoji": "🚀",
            "title": "Starter Plan",
            "features": [
                "✅ Clone React.js applications",
                "✅ Clone Vue.js applications",
                "✅ Advanced code cleanup",
                "✅ Auto-documentation generation",
                "✅ Priority support",
            ],
        },
        "pro": {
            "price": "$15/month",
            "clones": "100 clones/month",
            "emoji": "🏆",
            "title": "Pro Plan",
            "features": [
                "✅ Clone React.js applications",
                "✅ Clone Vue.js applications",
                "✅ Clone backend APIs",
                "✅ Advanced code cleanup",
                "✅ Auto-documentation generation",
                "✅ Custom domain support",
                "✅ Premium support",
                "✅ Team collaboration features",
            ],
        },
    }

    details = plan_details.get(plan, {})
    action = "Downgrade" if is_downgrade else "Upgrade"
    action_emoji = "🔽" if is_downgrade else details.get("emoji", "🔄")

    color = "yellow" if is_downgrade else "cyan"

    console.print()
    console.print(Panel(
        f"[bold {color}]{action_emoji} {action} to {details.get('title', plan.upper())}[/bold {color}]\n\n"
        f"[dim]Current Plan:[/dim] [bold]{current_plan.upper()}[/bold]\n"
        f"[dim]Target Plan:[/dim] [bold]{plan.upper()}[/bold]\n"
        f"[dim]Price:[/dim] [bold]{details.get('price', 'N/A')}[/bold]\n"
        f"[dim]Clones:[/dim] {details.get('clones', 'N/A')}\n\n"
        f"[dim]Features:[/dim]\n"
        + "\n".join(f"  {f}" for f in details.get("features", [])),
        border_style=color,
        padding=(1, 2),
        width=70,
    ))
    console.print()


def show_features_table() -> None:
    """Display a comparison table of plan features."""
    table = Table(title="📋 Plan Comparison", box=box.ROUNDED, style="dim")
    table.add_column("Feature", style="bold cyan")
    table.add_column("Free", style="bold white", justify="center")
    table.add_column("Starter", style="bold white", justify="center")
    table.add_column("Pro", style="bold white", justify="center")

    features = [
        ("Clones/month", "3", "20", "100"),
        ("HTML Cloning", "✅", "✅", "✅"),
        ("React Cloning", "❌", "✅", "✅"),
        ("Vue Cloning", "❌", "✅", "✅"),
        ("Backend Cloning", "❌", "❌", "✅"),
        ("Code Cleanup", "✅", "✅", "✅"),
        ("Auto Documentation", "❌", "✅", "✅"),
        ("Custom Domains", "❌", "❌", "✅"),
        ("Priority Support", "❌", "✅", "✅"),
        ("Price", "$0", "$5/mo", "$15/mo"),
    ]

    for feature, free, starter, pro in features:
        table.add_row(feature, free, starter, pro)

    console.print()
    console.print(table)
    console.print()


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "upgrade",
    "show_status",
    "show_plan_details",
    "show_features_table",
    "PLAN_RANK",
]