"""
Vercel Pricing Data
===================

Static pricing data for Vercel platform.

All prices are in USD and reflect current Vercel pricing as of 2026.
This data is used by the Cost Estimator to calculate deployment costs.

Why This File Exists:
    - Single source of truth for Vercel pricing
    - Allows easy updates when pricing changes
    - No API calls needed (faster, works offline)

Source: https://vercel.com/pricing

Author: OPUN8 Team
Version: 0.1.4
"""

from typing import Dict, Optional
from dataclasses import dataclass


# =============================================================================
# PLAN DEFINITIONS
# =============================================================================

@dataclass
class VercelPlan:
    """Vercel plan definition with pricing and features."""
    name: str
    base_price: float  # Per seat per month
    description: str
    features: list[str]
    free_bandwidth_gb: float = 0
    free_build_minutes: int = 0
    free_functions: int = 0


# Available plans
PLANS = {
    "hobby": VercelPlan(
        name="Hobby",
        base_price=0.00,
        description="Free plan for personal, non-commercial projects",
        free_bandwidth_gb=100.0,      # 100GB free
        free_build_minutes=0,          # Hobby has no free build minutes
        free_functions=1_000_000,      # 1 million function invocations
        features=[
            "Personal projects only",
            "100GB bandwidth included",
            "1,000,000 function invocations included",
            "1GB storage included",
            "Limited team collaboration",
        ],
    ),
    "pro": VercelPlan(
        name="Pro",
        base_price=20.00,  # $20/seat/month
        description="Commercial use, team collaboration",
        free_bandwidth_gb=1000.0,      # 1TB included
        free_build_minutes=1000,       # 1,000 free build minutes
        free_functions=1_000_000,      # 1 million free invocations
        features=[
            "Commercial use allowed",
            "1TB bandwidth included",
            "1,000 free build minutes/month",
            "1,000,000 function invocations included",
            "$20 monthly usage credit included",
            "Team collaboration (per seat)",
            "Advanced Deployment Protection ($150/mo)",
        ],
    ),
    "enterprise": VercelPlan(
        name="Enterprise",
        base_price=-1.0,  # -1 indicates custom pricing (contact sales)
        description="Custom pricing based on platform activity",
        free_bandwidth_gb=0,
        free_build_minutes=0,
        free_functions=0,
        features=[
            "Custom pricing",
            "Dedicated support",
            "Security requirements",
            "Organizational scale",
        ],
    ),
}


# =============================================================================
# OVERAGE / ADD-ON COSTS
# =============================================================================

class OverageCosts:
    """Vercel overage and add-on costs."""

    # Bandwidth
    BANDWIDTH_COST_PER_100GB = 40.00  # $40 per 100GB

    # Build Minutes
    BUILD_MINUTES_COST_PER_MIN = 0.014  # ~$0.014/min on 4-CPU machine

    # Pro Add-ons
    SAML_SSO_COST = 300.00  # $300/month
    HIPAA_BAA_COST = 350.00  # $350/month
    ADVANCED_DEPLOYMENT_PROTECTION = 150.00  # $150/month

    # Speed Insights
    SPEED_INSIGHTS_BASE_COST = 10.00  # $10/project/month
    SPEED_INSIGHTS_FREE_EVENTS = 10000
    SPEED_INSIGHTS_COST_PER_10K = 0.65  # $0.65 per additional 10,000 events

    # Web Analytics Plus (separate add-on from base)
    WEB_ANALYTICS_PLUS_COST = 10.00  # $10/month (optional)


# =============================================================================
# FRAMEWORK DETECTION
# =============================================================================

# Estimated resource usage per project type
FRAMEWORK_RESOURCES = {
    "react": {
        "bandwidth_gb": 10,      # Average monthly bandwidth for a React app
        "build_minutes": 100,    # Average build minutes per month
        "functions": 50000,      # Average function invocations per month
    },
    "nextjs": {
        "bandwidth_gb": 15,
        "build_minutes": 150,
        "functions": 100000,
    },
    "vue": {
        "bandwidth_gb": 8,
        "build_minutes": 80,
        "functions": 40000,
    },
    "angular": {
        "bandwidth_gb": 12,
        "build_minutes": 120,
        "functions": 60000,
    },
    "static": {
        "bandwidth_gb": 5,
        "build_minutes": 0,
        "functions": 0,
    },
    "nodejs": {
        "bandwidth_gb": 20,
        "build_minutes": 50,
        "functions": 200000,
    },
    "python": {
        "bandwidth_gb": 10,
        "build_minutes": 0,
        "functions": 0,
    },
    "unknown": {
        "bandwidth_gb": 10,
        "build_minutes": 50,
        "functions": 50000,
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_plan(plan_name: str) -> Optional[VercelPlan]:
    """
    Get plan information by name.

    Args:
        plan_name: Name of the plan (hobby, pro, enterprise)

    Returns:
        VercelPlan object, or None if plan not found

    Example:
        >>> plan = get_plan("pro")
        >>> print(plan.base_price)
        20.0
    """
    plan_name = plan_name.lower().strip()
    return PLANS.get(plan_name)


def get_framework_resources(framework: str) -> Dict[str, float]:
    """
    Get estimated resource usage for a framework.

    Args:
        framework: Framework name (react, nextjs, vue, etc.)

    Returns:
        Dictionary with bandwidth_gb, build_minutes, functions

    Example:
        >>> resources = get_framework_resources("react")
        >>> print(resources["bandwidth_gb"])
        10
    """
    framework = framework.lower().strip()
    return FRAMEWORK_RESOURCES.get(framework, FRAMEWORK_RESOURCES["unknown"])


def calculate_bandwidth_cost(bandwidth_gb: float, plan: str = "pro") -> float:
    """
    Calculate bandwidth cost based on usage and plan.

    Args:
        bandwidth_gb: Bandwidth used in GB
        plan: Plan name (hobby, pro)

    Returns:
        Estimated monthly bandwidth cost

    Example:
        >>> calculate_bandwidth_cost(1500, "pro")  # 1.5TB on Pro
        200.0  # $200 for 500GB overage
    """
    plan_obj = get_plan(plan)
    if plan_obj is None:
        return 0.0

    free_bandwidth = plan_obj.free_bandwidth_gb
    overage = max(0, bandwidth_gb - free_bandwidth)

    if overage <= 0:
        return 0.0

    return (overage / 100) * OverageCosts.BANDWIDTH_COST_PER_100GB


def calculate_build_cost(build_minutes: float, plan: str = "pro") -> float:
    """
    Calculate build minutes cost.

    Args:
        build_minutes: Number of build minutes used
        plan: Plan name (hobby, pro)

    Returns:
        Estimated monthly build cost

    Example:
        >>> calculate_build_cost(500, "pro")  # 500 min on Pro
        0.0  # Free tier covers it (1000 free)
        >>> calculate_build_cost(1500, "pro")
        7.0  # $7 for 500 overage
    """
    plan_obj = get_plan(plan)
    if plan_obj is None:
        return 0.0

    free_minutes = plan_obj.free_build_minutes
    overage = max(0, build_minutes - free_minutes)

    return overage * OverageCosts.BUILD_MINUTES_COST_PER_MIN


def calculate_function_cost(invocations: int, plan: str = "pro") -> float:
    """
    Calculate function invocation cost.

    Args:
        invocations: Number of function invocations
        plan: Plan name (hobby, pro)

    Returns:
        Estimated monthly function cost

    Example:
        >>> calculate_function_cost(1_500_000, "pro")
        5.0  # $5 for 500k overage (Vercel charges ~$0.00001/invocation)
    """
    plan_obj = get_plan(plan)
    if plan_obj is None:
        return 0.0

    free_functions = plan_obj.free_functions
    overage = max(0, invocations - free_functions)

    # Vercel's function pricing is roughly $0.00001 per invocation
    # (standard tier, varies by region)
    return overage * 0.00001


def calculate_speed_insights_cost(events: int) -> float:
    """
    Calculate Speed Insights cost.

    Args:
        events: Number of events per month

    Returns:
        Estimated monthly Speed Insights cost

    Example:
        >>> calculate_speed_insights_cost(5000)
        10.0  # $10 base (under 10k free)
        >>> calculate_speed_insights_cost(15000)
        10.65  # $10 base + $0.65 for 5k additional
    """
    if events <= OverageCosts.SPEED_INSIGHTS_FREE_EVENTS:
        return OverageCosts.SPEED_INSIGHTS_BASE_COST

    overage = events - OverageCosts.SPEED_INSIGHTS_FREE_EVENTS
    overage_cost = (overage / 10000) * OverageCosts.SPEED_INSIGHTS_COST_PER_10K

    return OverageCosts.SPEED_INSIGHTS_BASE_COST + overage_cost


def calculate_total_vercel_cost(
    plan: str,
    num_seats: int,
    bandwidth_gb: float,
    build_minutes: float,
    invocations: int = 0,
    addons: Optional[Dict[str, bool]] = None,
) -> Dict[str, float]:
    """
    Calculate total Vercel monthly cost.

    Args:
        plan: Plan name (hobby, pro)
        num_seats: Number of team members
        bandwidth_gb: Bandwidth used in GB
        build_minutes: Build minutes used
        invocations: Function invocations
        addons: Dictionary of add-ons (saml_sso, hipaa_baa, etc.)

    Returns:
        Dictionary with cost breakdown and total

    Example:
        >>> costs = calculate_total_vercel_cost("pro", 5, 1500, 500)
        >>> print(costs["total"])
        120.0  # 5 seats * $20 + $0 bandwidth overage + $0 build overage
    """
    plan_obj = get_plan(plan)
    if plan_obj is None:
        return {"error": f"Unknown plan: {plan}"}

    # Base seat cost
    base_cost = plan_obj.base_price * num_seats

    # Usage costs
    bandwidth_cost = calculate_bandwidth_cost(bandwidth_gb, plan)
    build_cost = calculate_build_cost(build_minutes, plan)
    function_cost = calculate_function_cost(invocations, plan)

    # Add-ons
    if addons is None:
        addons = {}

    addon_costs = 0.0
    if addons.get("saml_sso", False):
        addon_costs += OverageCosts.SAML_SSO_COST
    if addons.get("hipaa_baa", False):
        addon_costs += OverageCosts.HIPAA_BAA_COST
    if addons.get("advanced_deployment_protection", False):
        addon_costs += OverageCosts.ADVANCED_DEPLOYMENT_PROTECTION
    if addons.get("speed_insights", False):
        addon_costs += OverageCosts.SPEED_INSIGHTS_BASE_COST

    total = base_cost + bandwidth_cost + build_cost + function_cost + addon_costs

    return {
        "base_cost": base_cost,
        "bandwidth_cost": bandwidth_cost,
        "build_cost": build_cost,
        "function_cost": function_cost,
        "addon_costs": addon_costs,
        "total": total,
        "plan": plan_obj.name,
    }


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "PLANS",
    "OverageCosts",
    "FRAMEWORK_RESOURCES",
    "VercelPlan",
    "get_plan",
    "get_framework_resources",
    "calculate_bandwidth_cost",
    "calculate_build_cost",
    "calculate_function_cost",
    "calculate_speed_insights_cost",
    "calculate_total_vercel_cost",
]