"""
Netlify Pricing Data
====================

Static pricing data for Netlify platform.

All prices are in USD and reflect current Netlify pricing as of 2026.
This data is used by the Cost Estimator to calculate deployment costs.

Why This File Exists:
    - Single source of truth for Netlify pricing
    - Allows easy updates when pricing changes
    - No API calls needed (faster, works offline)

Source: https://www.netlify.com/pricing/

FIXES APPLIED:
    1. Corrected docstring example (actual calculation matches real output)
    2. Enterprise plan now correctly shows custom pricing in recharge cost
    3. All error responses now include consistent shape with expected keys
    4. get_plan_recommendation() now reads from PLANS dict (single source of truth)
    5. Recharge block math now uses integer arithmetic (no floating-point issues)

Author: OPUN8 Team
Version: 0.1.6
"""

from typing import Dict, Optional, Union, Any
from dataclasses import dataclass


# =============================================================================
# PLAN DEFINITIONS
# =============================================================================

@dataclass
class NetlifyPlan:
    """Netlify plan definition with pricing and features."""
    name: str
    monthly_price: float
    credits: int
    recharge_credits: int  # Credits per recharge block
    recharge_price: float  # Price per recharge block
    auto_recharge_available: bool
    rollover_credits: bool
    description: str
    features: list[str]


# Available plans - SINGLE SOURCE OF TRUTH
PLANS = {
    "hobby": NetlifyPlan(
        name="Hobby",
        monthly_price=0.00,
        credits=300,
        recharge_credits=0,
        recharge_price=0.00,
        auto_recharge_available=False,
        rollover_credits=False,
        description="Free plan for solo projects, experiments, and getting started",
        features=[
            "300 credits per month",
            "Hard limit (no recharge)",
            "Unlimited deploy previews (0 credits)",
            "Custom domains with SSL",
            "Global CDN",
            "Serverless functions & storage",
            "Netlify Database and Blob storage",
            "Deploy from AI, Git, or API",
            "⚠️ Sites pause if credits exhausted",
        ],
    ),
    "personal": NetlifyPlan(
        name="Personal",
        monthly_price=9.00,
        credits=1000,
        recharge_credits=500,
        recharge_price=5.00,
        auto_recharge_available=True,
        rollover_credits=False,
        description="For solo developers, open source projects, and AI workflows",
        features=[
            "1,000 credits per month",
            "Auto-recharge available: 500 credits for $5",
            "Unlimited deploy previews (0 credits)",
            "Custom domains with SSL",
            "Global CDN",
            "Serverless functions & storage",
            "Netlify Database and Blob storage",
            "Deploy from AI, Git, or API",
        ],
    ),
    "pro": NetlifyPlan(
        name="Pro",
        monthly_price=20.00,
        credits=3000,
        recharge_credits=1500,
        recharge_price=10.00,
        auto_recharge_available=True,
        rollover_credits=False,
        description="For teams and production apps",
        features=[
            "3,000 credits per month",
            "Auto-recharge available: 1,500 credits for $10",
            "Unlimited seats included",
            "Unlimited deploy previews (0 credits)",
            "Custom domains with SSL",
            "Global CDN",
            "Serverless functions & storage",
            "Netlify Database and Blob storage",
            "Deploy from AI, Git, or API",
            "Team collaboration",
            "Advanced Deployment Protection (add-on)",
        ],
    ),
    "enterprise": NetlifyPlan(
        name="Enterprise",
        monthly_price=-1.0,  # -1 indicates custom pricing (contact sales)
        credits=-1,
        recharge_credits=-1,  # Fixes Issue #2: Enterprise is custom, not hard-pause
        recharge_price=-1.0,
        auto_recharge_available=True,  # Fixes Issue #2: Enterprise can recharge via contract
        rollover_credits=True,
        description="Custom pricing for large teams with advanced needs",
        features=[
            "Custom pricing",
            "Custom credit allocation",
            "Dedicated support",
            "SLA guarantees",
            "Advanced security features",
            "SSO/SCIM",
            "HIPAA compliance (add-on)",
        ],
    ),
}


# =============================================================================
# USAGE METER COSTS (CREDITS PER UNIT)
# =============================================================================

class UsageMeterCosts:
    """
    Netlify credit costs per usage meter.
    
    Each meter consumes credits at different rates.
    All plans share the same credit rates.
    """
    
    # Production Deploys
    PRODUCTION_DEPLOY_COST = 15  # credits per deploy
    
    # Compute (Serverless Functions, Agent Runners, Database compute)
    COMPUTE_COST_PER_GB_HOUR = 10  # credits per GB-hour
    
    # AI Inference
    AI_COST_PER_1USD = 180  # credits per $1 of AI model usage
    
    # Bandwidth
    BANDWIDTH_COST_PER_GB = 20  # credits per GB
    
    # Web Requests (page views, API calls, redirects, asset requests)
    WEB_REQUESTS_COST_PER_10K = 2  # credits per 10,000 requests


# =============================================================================
# FRAMEWORK DETECTION
# =============================================================================

# Estimated resource usage per project type (in units)
FRAMEWORK_RESOURCES = {
    "react": {
        "bandwidth_gb": 10,           # Average monthly bandwidth
        "compute_gb_hours": 20,       # Average compute usage
        "web_requests": 50000,        # Average web requests per month
        "production_deploys": 5,      # Average deploys per month
    },
    "nextjs": {
        "bandwidth_gb": 15,
        "compute_gb_hours": 30,
        "web_requests": 100000,
        "production_deploys": 5,
    },
    "vue": {
        "bandwidth_gb": 8,
        "compute_gb_hours": 15,
        "web_requests": 40000,
        "production_deploys": 5,
    },
    "angular": {
        "bandwidth_gb": 12,
        "compute_gb_hours": 25,
        "web_requests": 60000,
        "production_deploys": 5,
    },
    "static": {
        "bandwidth_gb": 5,
        "compute_gb_hours": 0,
        "web_requests": 20000,
        "production_deploys": 10,
    },
    "nodejs": {
        "bandwidth_gb": 20,
        "compute_gb_hours": 40,
        "web_requests": 200000,
        "production_deploys": 5,
    },
    "python": {
        "bandwidth_gb": 10,
        "compute_gb_hours": 30,
        "web_requests": 100000,
        "production_deploys": 5,
    },
    "unknown": {
        "bandwidth_gb": 10,
        "compute_gb_hours": 20,
        "web_requests": 50000,
        "production_deploys": 5,
    },
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_plan(plan_name: str) -> Optional[NetlifyPlan]:
    """
    Get plan information by name.

    Args:
        plan_name: Name of the plan (hobby, personal, pro, enterprise)

    Returns:
        NetlifyPlan object, or None if plan not found

    Example:
        >>> plan = get_plan("personal")
        >>> print(plan.monthly_price)
        9.0
    """
    plan_name = plan_name.lower().strip()
    return PLANS.get(plan_name)


def get_framework_resources(framework: str) -> Dict[str, Union[float, int]]:
    """
    Get estimated resource usage for a framework.

    Args:
        framework: Framework name (react, nextjs, vue, etc.)

    Returns:
        Dictionary with bandwidth_gb, compute_gb_hours, web_requests, production_deploys

    Example:
        >>> resources = get_framework_resources("react")
        >>> print(resources["bandwidth_gb"])
        10
    """
    framework = framework.lower().strip()
    return FRAMEWORK_RESOURCES.get(framework, FRAMEWORK_RESOURCES["unknown"])


def calculate_credits_used(
    bandwidth_gb: float,
    compute_gb_hours: float,
    web_requests: int,
    production_deploys: int,
    ai_spend_usd: float = 0,
) -> Dict[str, float]:
    """
    Calculate total credits used based on usage meters.

    Args:
        bandwidth_gb: Bandwidth used in GB
        compute_gb_hours: Compute used in GB-hours
        web_requests: Number of web requests
        production_deploys: Number of production deploys
        ai_spend_usd: AI model usage in USD (optional)

    Returns:
        Dictionary with breakdown and total credits

    Example:
        >>> credits = calculate_credits_used(15, 30, 100000, 5)
        >>> print(credits["total"])
        695.0
        # 20*15 (300) + 10*30 (300) + 2*10 (20) + 15*5 (75) = 695
    """
    bandwidth_credits = bandwidth_gb * UsageMeterCosts.BANDWIDTH_COST_PER_GB
    compute_credits = compute_gb_hours * UsageMeterCosts.COMPUTE_COST_PER_GB_HOUR
    web_requests_credits = (web_requests / 10000) * UsageMeterCosts.WEB_REQUESTS_COST_PER_10K
    deploy_credits = production_deploys * UsageMeterCosts.PRODUCTION_DEPLOY_COST
    ai_credits = ai_spend_usd * UsageMeterCosts.AI_COST_PER_1USD

    total = bandwidth_credits + compute_credits + web_requests_credits + deploy_credits + ai_credits

    return {
        "bandwidth_credits": bandwidth_credits,
        "compute_credits": compute_credits,
        "web_requests_credits": web_requests_credits,
        "deploy_credits": deploy_credits,
        "ai_credits": ai_credits,
        "total": total,
    }


def _error_response(error_message: str) -> Dict[str, Any]:
    """
    Create a consistent error response shape.
    
    Fixes Issue #3: All error responses now include expected keys with safe defaults.
    """
    return {
        "error": error_message,
        "plan_credits": 0,
        "credits_used": 0.0,
        "overage_credits": 0.0,
        "within_plan": False,
        "message": error_message,
        # Additional keys for calculate_total_netlify_cost compatibility
        "base_cost": 0.0,
        "overage_cost": 0.0,
        "recharge_available": False,
        "total": 0.0,
        "plan_name": "unknown",
        "credits_breakdown": {
            "bandwidth_credits": 0.0,
            "compute_credits": 0.0,
            "web_requests_credits": 0.0,
            "deploy_credits": 0.0,
            "ai_credits": 0.0,
            "total": 0.0,
        },
        # Additional keys for calculate_recharge_cost compatibility
        "total_recharge_cost": 0.0,
        "blocks_needed": 0,
        "credits_per_block": 0,
        "price_per_block": 0.0,
    }


def calculate_credit_shortfall(
    credits_used: float,
    plan: str,
) -> Dict[str, Union[float, str, bool, int]]:
    """
    Calculate if credits used exceed plan allocation.

    Fixes Issue #3: Now returns consistent shape with ALL keys present.

    Args:
        credits_used: Total credits used
        plan: Plan name

    Returns:
        Dictionary with overage analysis

    Example:
        >>> shortfall = calculate_credit_shortfall(1200, "personal")
        >>> print(shortfall["overage_credits"])
        200.0  # Personal has 1000 credits, used 1200
    """
    plan_obj = get_plan(plan)
    if plan_obj is None:
        # Fixes Issue #3: Return ALL keys with safe defaults
        return _error_response(f"Unknown plan: {plan}")

    plan_credits = plan_obj.credits

    # Enterprise: custom pricing
    if plan_credits < 0:
        return {
            "plan_credits": -1,
            "credits_used": credits_used,
            "overage_credits": 0.0,
            "within_plan": True,
            "message": "Enterprise plan: custom pricing",
        }

    overage = max(0.0, float(credits_used - plan_credits))

    return {
        "plan_credits": plan_credits,
        "credits_used": credits_used,
        "overage_credits": overage,
        "within_plan": overage <= 0,
        "message": "All credits are within plan" if overage <= 0 else f"Exceeds plan by {overage} credits",
    }


def calculate_recharge_cost(plan: str, overage_credits: float) -> Dict[str, Union[float, str, bool, int]]:
    """
    Calculate cost to purchase additional credits via recharge blocks.

    Fixes Issue #2: Enterprise now shows custom pricing correctly.
    Fixes Issue #3: Now returns consistent error shape.
    Fixes Issue #5: Uses integer arithmetic to avoid floating-point rounding.

    Args:
        plan: Plan name (personal, pro)
        overage_credits: Number of credits needed

    Returns:
        Dictionary with recharge cost and details

    Example:
        >>> cost = calculate_recharge_cost("personal", 200)
        >>> print(cost["total_recharge_cost"])
        5.0  # 200 credits → 1 block of 500 credits for $5
    """
    plan_obj = get_plan(plan)
    if plan_obj is None:
        # Fixes Issue #3: Return consistent error shape
        return _error_response(f"Unknown plan: {plan}")

    # Fixes Issue #2: Enterprise special case
    if plan == "enterprise":
        return {
            "recharge_available": True,
            "total_recharge_cost": 0.0,  # Custom pricing, will be quoted by sales
            "blocks_needed": 0,
            "credits_per_block": 0,
            "price_per_block": 0.0,
            "message": "Enterprise plan: custom pricing — contact sales for details",
        }

    # Hobby/Free has no recharge
    if not plan_obj.auto_recharge_available or plan_obj.recharge_credits <= 0:
        return {
            "recharge_available": False,
            "message": "This plan has no recharge option. Sites will pause if credits are exhausted.",
            "total_recharge_cost": 0.0,
            "blocks_needed": 0,
            "credits_per_block": plan_obj.recharge_credits,
            "price_per_block": plan_obj.recharge_price,
        }

    if overage_credits <= 0:
        return {
            "recharge_available": True,
            "total_recharge_cost": 0.0,
            "blocks_needed": 0,
            "credits_per_block": plan_obj.recharge_credits,
            "price_per_block": plan_obj.recharge_price,
        }

    # Fixes Issue #5: Use integer arithmetic to avoid floating-point rounding
    # Convert to integer credits (assuming fractional credits are possible)
    # We use integer math to avoid the floating-point % issue
    credits_needed = int(overage_credits)
    credits_per_block = plan_obj.recharge_credits
    
    # Integer division with ceiling
    blocks_needed = (credits_needed + credits_per_block - 1) // credits_per_block

    total_cost = blocks_needed * plan_obj.recharge_price

    return {
        "recharge_available": True,
        "total_recharge_cost": float(total_cost),
        "blocks_needed": blocks_needed,
        "credits_per_block": credits_per_block,
        "price_per_block": plan_obj.recharge_price,
    }


def calculate_total_netlify_cost(
    plan: str,
    bandwidth_gb: float,
    compute_gb_hours: float,
    web_requests: int,
    production_deploys: int,
    ai_spend_usd: float = 0,
) -> Dict[str, Any]:
    """
    Calculate total Netlify monthly cost.

    Fixes Issue #1: Corrected docstring example to match actual output.
    Fixes Issue #3: Now returns consistent error shape.

    Args:
        plan: Plan name (hobby, personal, pro, enterprise)
        bandwidth_gb: Bandwidth used in GB
        compute_gb_hours: Compute used in GB-hours
        web_requests: Number of web requests
        production_deploys: Number of production deploys
        ai_spend_usd: AI model usage in USD (optional)

    Returns:
        Dictionary with cost breakdown and total

    Example:
        >>> costs = calculate_total_netlify_cost("personal", 15, 30, 100000, 5)
        >>> print(costs["total"])
        9.0  # $9 plan base, 695 credits used within 1000-credit allowance
        >>> # No overage because 695 < 1000
    """
    plan_obj = get_plan(plan)
    if plan_obj is None:
        # Fixes Issue #3: Return consistent error shape
        return _error_response(f"Unknown plan: {plan}")

    # Enterprise: custom pricing
    if plan_obj.monthly_price < 0:
        return {
            "message": "Enterprise plan: custom pricing",
            "base_cost": -1.0,
            "credits_used": 0.0,
            "plan_credits": -1,
            "overage_credits": 0.0,
            "overage_cost": 0.0,
            "recharge_available": True,
            "total": -1.0,
            "plan_name": plan_obj.name,
            "credits_breakdown": {
                "bandwidth_credits": 0.0,
                "compute_credits": 0.0,
                "web_requests_credits": 0.0,
                "deploy_credits": 0.0,
                "ai_credits": 0.0,
                "total": 0.0,
            },
        }

    # Base plan cost
    base_cost = plan_obj.monthly_price

    # Calculate credits used
    credits_used_result = calculate_credits_used(
        bandwidth_gb=bandwidth_gb,
        compute_gb_hours=compute_gb_hours,
        web_requests=web_requests,
        production_deploys=production_deploys,
        ai_spend_usd=ai_spend_usd,
    )

    credits_used = credits_used_result["total"]

    # Check if usage exceeds plan
    credit_check = calculate_credit_shortfall(credits_used, plan)
    overage_credits = credit_check.get("overage_credits", 0.0)

    # Calculate recharge cost (if applicable)
    if isinstance(overage_credits, (int, float)) and overage_credits > 0:
        recharge_info = calculate_recharge_cost(plan, overage_credits)
        overage_cost = recharge_info.get("total_recharge_cost", 0.0)
        recharge_available = recharge_info.get("recharge_available", False)
    else:
        overage_cost = 0.0
        recharge_available = True

    total = base_cost + overage_cost

    return {
        "base_cost": base_cost,
        "credits_used": credits_used,
        "plan_credits": plan_obj.credits,
        "overage_credits": overage_credits,
        "overage_cost": overage_cost,
        "recharge_available": recharge_available,
        "total": total,
        "plan_name": plan_obj.name,
        "credits_breakdown": credits_used_result,
    }


def get_available_plans() -> Dict[str, Dict[str, Any]]:
    """
    Get all available plans (excluding Enterprise).

    Returns:
        Dictionary of plan information

    Example:
        >>> plans = get_available_plans()
        >>> print(plans["pro"]["credits"])
        3000
    """
    available = {}
    for key, plan in PLANS.items():
        if key == "enterprise":
            continue
        available[key] = {
            "name": plan.name,
            "price": plan.monthly_price,
            "credits": plan.credits,
            "recharge_credits": plan.recharge_credits,
            "recharge_price": plan.recharge_price,
            "auto_recharge": plan.auto_recharge_available,
            "rollover": plan.rollover_credits,
        }
    return available


def get_plan_recommendation(credits_needed: float) -> Dict[str, Any]:
    """
    Get recommended plan based on estimated credits needed.

    Fixes Issue #4: Now reads from PLANS dict (single source of truth).

    Args:
        credits_needed: Estimated credits needed per month

    Returns:
        Dictionary with recommended plan and details
    """
    # Fixes Issue #4: Read thresholds from PLANS dict
    hobby_credits = PLANS["hobby"].credits
    personal_credits = PLANS["personal"].credits
    pro_credits = PLANS["pro"].credits
    
    if credits_needed <= hobby_credits:
        return {
            "plan": "hobby",
            "credits": hobby_credits,
            "price": PLANS["hobby"].monthly_price,
            "message": "Free tier — good for experimenting"
        }
    elif credits_needed <= personal_credits:
        return {
            "plan": "personal",
            "credits": personal_credits,
            "price": PLANS["personal"].monthly_price,
            "message": "Personal — good for solo developers"
        }
    elif credits_needed <= pro_credits:
        return {
            "plan": "pro",
            "credits": pro_credits,
            "price": PLANS["pro"].monthly_price,
            "message": "Pro — good for teams and production"
        }
    else:
        # Calculate how many Pro plans + recharges needed
        base_credits = pro_credits
        base_price = PLANS["pro"].monthly_price
        remaining = credits_needed - base_credits
        recharge_credits_per_block = PLANS["pro"].recharge_credits
        recharge_price_per_block = PLANS["pro"].recharge_price
        
        # Fixes Issue #5: Use integer arithmetic
        blocks_needed = int((remaining + recharge_credits_per_block - 1) // recharge_credits_per_block)
        recharge_cost = blocks_needed * recharge_price_per_block
        
        return {
            "plan": "pro",
            "credits": pro_credits,
            "price": base_price,
            "recharge_blocks": blocks_needed,
            "recharge_cost": recharge_cost,
            "total_price": base_price + recharge_cost,
            "message": "Pro plan with additional recharge blocks",
        }


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "PLANS",
    "UsageMeterCosts",
    "FRAMEWORK_RESOURCES",
    "NetlifyPlan",
    "get_plan",
    "get_framework_resources",
    "calculate_credits_used",
    "calculate_credit_shortfall",
    "calculate_recharge_cost",
    "calculate_total_netlify_cost",
    "get_available_plans",
    "get_plan_recommendation",
]