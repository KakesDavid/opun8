"""
Render Pricing Data
===================

Static pricing data for Render platform.

All prices are in USD and reflect current Render pricing as of 2026.
This data is used by the Cost Estimator to calculate deployment costs.

Source: https://render.com/pricing

Author: OPUN8 Team
Version: 0.1.4
"""

from typing import Dict, Optional, List
from dataclasses import dataclass


# =============================================================================
# WORKSPACE PLANS (Updated April 23, 2026)
# =============================================================================

@dataclass
class RenderWorkspacePlan:
    """Render workspace plan definition."""
    name: str
    price: float  # Monthly flat fee (-1.0 = custom pricing)
    max_members: int
    free_bandwidth_gb: float
    free_build_minutes: int
    max_services: int
    features: List[str]


WORKSPACE_PLANS = {
    "hobby": RenderWorkspacePlan(
        name="Hobby",
        price=0.00,
        max_members=1,
        free_bandwidth_gb=5.0,
        free_build_minutes=500,
        max_services=25,
        features=[
            "1 member",
            "5GB bandwidth included",
            "500 build minutes/month",
            "Unlimited projects",
            "Up to 25 services",
        ],
    ),
    "pro": RenderWorkspacePlan(
        name="Pro",
        price=25.00,
        max_members=999999,  # Unlimited
        free_bandwidth_gb=25.0,
        free_build_minutes=1000,
        max_services=999999,
        features=[
            "Unlimited team members",
            "25GB bandwidth included",
            "1,000 build minutes/month",
            "SOC 2 and ISO 27001 reports",
            "Audit logs",
            "Unlimited projects",
        ],
    ),
    "scale": RenderWorkspacePlan(
        name="Scale",
        price=499.00,
        max_members=999999,
        free_bandwidth_gb=1000.0,  # 1TB
        free_build_minutes=5000,
        max_services=999999,
        features=[
            "Unlimited team members",
            "1TB bandwidth included",
            "5,000 build minutes/month",
            "SSO/SCIM support",
            "Organization audit logs",
            "HIPAA-enabled workspaces",
        ],
    ),
    "enterprise": RenderWorkspacePlan(
        name="Enterprise",
        price=-1.0,  # Custom pricing sentinel
        max_members=999999,
        free_bandwidth_gb=0,
        free_build_minutes=0,
        max_services=999999,
        features=[
            "Custom pricing",
            "Dedicated support",
            "Custom terms",
        ],
    ),
}


# =============================================================================
# COMPUTE TIERS
# =============================================================================

@dataclass
class RenderComputeTier:
    """Render compute tier definition."""
    name: str
    price: float  # Monthly per service
    ram_gb: float
    cpu_cores: float
    description: str


COMPUTE_TIERS = {
    "free": RenderComputeTier(
        name="Free",
        price=0.00,
        ram_gb=0.5,
        cpu_cores=0.1,
        description="Spins down after inactivity",
    ),
    "starter": RenderComputeTier(
        name="Starter",
        price=7.00,
        ram_gb=0.5,
        cpu_cores=0.5,
        description="512MB RAM, 0.5 CPU",
    ),
    "standard": RenderComputeTier(
        name="Standard",
        price=25.00,
        ram_gb=2.0,
        cpu_cores=1.0,
        description="2GB RAM, 1 CPU",
    ),
    "pro_ultra": RenderComputeTier(
        name="Pro Ultra",
        price=450.00,
        ram_gb=32.0,
        cpu_cores=8.0,
        description="32GB RAM, 8 CPU",
    ),
}


# =============================================================================
# DATABASE & STORAGE
# =============================================================================

# Postgres storage cost per GB per month
POSTGRES_STORAGE_COST_PER_GB = 0.30  # $0.30/GB/month

# Postgres instance fees (base cost per tier)
POSTGRES_INSTANCE_COSTS = {
    "basic": 6.00,      # Basic-256mb
    "standard": 24.00,  # Standard
    "high": 85.00,      # High
    "enterprise": 420.00,  # Enterprise
}

# Self-managed disk storage cost per GB per month
DISK_STORAGE_COST_PER_GB = 0.25  # $0.25/GB/month

# Redis pricing (Key Value)
REDIS_PRICES = {
    "small": 10.00,    # 1GB
    "medium": 50.00,   # 5GB
    "large": 200.00,   # 20GB
    "xlarge": 1100.00, # 40GB
}


# =============================================================================
# BANDWIDTH OVERAGE
# =============================================================================

BANDWIDTH_OVERAGE_COST_PER_GB = 0.15  # $0.15/GB after free tier


# =============================================================================
# BUILD PIPELINE MINUTES
# =============================================================================

BUILD_MINUTES_COST_PER_1000 = 5.00  # $5 per additional 1,000 minutes


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_workspace_plan(plan_name: str) -> Optional[RenderWorkspacePlan]:
    """
    Get workspace plan by name.

    Args:
        plan_name: Name of the plan (hobby, pro, scale, enterprise)

    Returns:
        RenderWorkspacePlan or None if not found
    """
    plan_name = plan_name.lower().strip()
    return WORKSPACE_PLANS.get(plan_name)


def get_compute_tier(tier_name: str) -> Optional[RenderComputeTier]:
    """
    Get compute tier by name.

    Args:
        tier_name: Name of the tier (free, starter, standard, pro_ultra)

    Returns:
        RenderComputeTier or None if not found
    """
    tier_name = tier_name.lower().strip()
    return COMPUTE_TIERS.get(tier_name)


def calculate_workspace_cost(plan_name: str) -> Optional[float]:
    """
    Calculate workspace cost.

    Args:
        plan_name: Name of the workspace plan

    Returns:
        Monthly workspace cost, or None if plan not found or custom pricing

    Example:
        >>> calculate_workspace_cost("pro")
        25.0
        >>> calculate_workspace_cost("enterprise")
        None  # Custom pricing
    """
    plan = get_workspace_plan(plan_name)
    if plan is None:
        return None
    if plan.price < 0:  # Custom pricing sentinel
        return None
    return plan.price


def calculate_compute_cost(tier_name: str, count: int = 1) -> Optional[float]:
    """
    Calculate compute cost for multiple services.

    Args:
        tier_name: Name of the compute tier
        count: Number of services

    Returns:
        Monthly compute cost, or None if tier not found

    Example:
        >>> calculate_compute_cost("starter", 3)
        21.0  # 3 starter services
    """
    tier = get_compute_tier(tier_name)
    if tier is None:
        return None
    return tier.price * count


def calculate_database_cost(
    storage_gb: float,
    instance_tier: str = "basic"
) -> Optional[float]:
    """
    Calculate Postgres database cost (storage + instance fee).

    Args:
        storage_gb: Storage in GB
        instance_tier: Instance tier (basic, standard, high, enterprise)

    Returns:
        Monthly database cost, or None if instance tier not found

    Example:
        >>> calculate_database_cost(10, "basic")
        9.0  # $6 instance + $3 storage
        >>> calculate_database_cost(10, "standard")
        27.0  # $24 instance + $3 storage
    """
    instance_tier = instance_tier.lower().strip()
    instance_cost = POSTGRES_INSTANCE_COSTS.get(instance_tier)
    if instance_cost is None:
        return None

    storage_cost = storage_gb * POSTGRES_STORAGE_COST_PER_GB
    return instance_cost + storage_cost


def calculate_disk_cost(storage_gb: float) -> float:
    """
    Calculate persistent disk storage cost.

    Args:
        storage_gb: Storage in GB

    Returns:
        Monthly disk cost

    Example:
        >>> calculate_disk_cost(10)
        2.5  # $0.25/GB * 10GB
    """
    return storage_gb * DISK_STORAGE_COST_PER_GB


def calculate_bandwidth_cost(bandwidth_gb: float, plan_name: str = "hobby") -> Optional[float]:
    """
    Calculate bandwidth overage cost.

    Args:
        bandwidth_gb: Bandwidth used in GB
        plan_name: Workspace plan name

    Returns:
        Monthly bandwidth cost, or None if plan not found

    Example:
        >>> calculate_bandwidth_cost(10, "hobby")
        0.75  # 5GB free, 5GB overage * $0.15
    """
    plan = get_workspace_plan(plan_name)
    if plan is None:
        return None

    free_bandwidth = plan.free_bandwidth_gb
    overage = max(0, bandwidth_gb - free_bandwidth)

    return overage * BANDWIDTH_OVERAGE_COST_PER_GB


def calculate_build_minutes_cost(build_minutes: int, plan_name: str = "hobby") -> Optional[float]:
    """
    Calculate build pipeline minutes overage cost.

    Args:
        build_minutes: Build minutes used
        plan_name: Workspace plan name

    Returns:
        Monthly build minutes cost, or None if plan not found

    Example:
        >>> calculate_build_minutes_cost(800, "hobby")
        1.5  # 500 free, 300 overage → $5 per 1000 minutes
    """
    plan = get_workspace_plan(plan_name)
    if plan is None:
        return None

    free_minutes = plan.free_build_minutes
    overage = max(0, build_minutes - free_minutes)

    return (overage / 1000) * BUILD_MINUTES_COST_PER_1000


def calculate_redis_cost(plan: str) -> Optional[float]:
    """
    Calculate Redis (Key Value) cost.

    Args:
        plan: Redis plan (small, medium, large, xlarge)

    Returns:
        Monthly Redis cost, or None if plan not found

    Example:
        >>> calculate_redis_cost("small")
        10.0
    """
    plan = plan.lower().strip()
    return REDIS_PRICES.get(plan)


def calculate_total_render_cost(
    workspace_plan: str,
    compute_tiers: Dict[str, int],  # tier_name -> count
    database_gb: float = 0,
    database_instance_tier: str = "basic",
    bandwidth_gb: float = 0,
    disk_gb: float = 0,
    build_minutes: int = 0,
    redis_plan: Optional[str] = None,
) -> Dict[str, float]:
    """
    Calculate total Render monthly cost.

    Args:
        workspace_plan: Workspace plan name
        compute_tiers: Dictionary of compute tier counts
        database_gb: Postgres storage in GB
        database_instance_tier: Postgres instance tier (basic, standard, high)
        bandwidth_gb: Bandwidth used in GB
        disk_gb: Persistent disk storage in GB
        build_minutes: Build pipeline minutes used
        redis_plan: Redis plan name (optional)

    Returns:
        Dictionary with cost breakdown and total

    Example:
        >>> costs = calculate_total_render_cost(
        ...     "pro",
        ...     {"starter": 2, "standard": 1},
        ...     database_gb=10,
        ...     database_instance_tier="basic",
        ...     bandwidth_gb=50,
        ...     disk_gb=20,
        ...     build_minutes=1500,
        ...     redis_plan="small"
        ... )
        >>> print(costs["total"])
        124.75
    """
    # Workspace cost
    workspace_cost = calculate_workspace_cost(workspace_plan)
    if workspace_cost is None:
        # Custom pricing or unknown plan — can't calculate
        return {
            "error": f"Unknown or custom pricing for workspace plan: {workspace_plan}"
        }

    # Compute cost
    compute_cost = 0.0
    for tier, count in compute_tiers.items():
        tier_cost = calculate_compute_cost(tier, count)
        if tier_cost is None:
            return {"error": f"Unknown compute tier: {tier}"}
        compute_cost += tier_cost

    # Database cost
    db_cost = calculate_database_cost(database_gb, database_instance_tier)
    if db_cost is None:
        return {"error": f"Unknown database instance tier: {database_instance_tier}"}

    # Bandwidth cost
    bandwidth_cost = calculate_bandwidth_cost(bandwidth_gb, workspace_plan)
    if bandwidth_cost is None:
        return {"error": f"Unknown workspace plan: {workspace_plan}"}

    # Build minutes cost
    build_cost = calculate_build_minutes_cost(build_minutes, workspace_plan)
    if build_cost is None:
        return {"error": f"Unknown workspace plan: {workspace_plan}"}

    # Disk cost
    disk_cost = calculate_disk_cost(disk_gb)

    # Redis cost
    redis_cost = 0.0
    if redis_plan:
        redis_cost = calculate_redis_cost(redis_plan)
        if redis_cost is None:
            return {"error": f"Unknown Redis plan: {redis_plan}"}

    total = workspace_cost + compute_cost + db_cost + bandwidth_cost + build_cost + disk_cost + redis_cost

    return {
        "workspace_cost": workspace_cost,
        "compute_cost": compute_cost,
        "database_cost": db_cost,
        "bandwidth_cost": bandwidth_cost,
        "build_minutes_cost": build_cost,
        "disk_cost": disk_cost,
        "redis_cost": redis_cost,
        "total": total,
        "workspace_plan": workspace_plan,
    }


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "WORKSPACE_PLANS",
    "COMPUTE_TIERS",
    "REDIS_PRICES",
    "POSTGRES_INSTANCE_COSTS",
    "POSTGRES_STORAGE_COST_PER_GB",
    "DISK_STORAGE_COST_PER_GB",
    "BANDWIDTH_OVERAGE_COST_PER_GB",
    "BUILD_MINUTES_COST_PER_1000",
    "RenderWorkspacePlan",
    "RenderComputeTier",
    "get_workspace_plan",
    "get_compute_tier",
    "calculate_workspace_cost",
    "calculate_compute_cost",
    "calculate_database_cost",
    "calculate_bandwidth_cost",
    "calculate_build_minutes_cost",
    "calculate_disk_cost",
    "calculate_redis_cost",
    "calculate_total_render_cost",
]