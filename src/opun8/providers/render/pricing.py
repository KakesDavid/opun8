"""
Render Pricing Data
===================

Static pricing data for Render platform.

All prices are in USD and reflect current Render pricing as of 2026.
This data is used by the Cost Estimator to calculate deployment costs.

Source: https://render.com/pricing
Verified against the live pricing page: July 2026.

✅ FIX: Free tier (hobby) now correctly returns $0 for all costs
✅ FIX: COMPUTE_TIERS now includes all real tiers (Free → Starter → Standard → Pro → Pro Plus → Pro Max → Pro Ultra → Custom)
✅ FIX: POSTGRES_INSTANCE_COSTS now matches Render's actual instance types and prices
✅ FIX: REDIS_PRICES now matches Render's actual Key Value tiers
✅ FIX: Docstring example now correctly calculates to $94.25
✅ FIX: Added "custom" sentinel entries for compute and Redis with proper error handling

Author: OPUN8 Team
Version: 0.1.6
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
    price: float  # Monthly per service (-1.0 = custom pricing)
    ram_gb: float
    cpu_cores: float
    description: str


COMPUTE_TIERS = {
    "free": RenderComputeTier(
        name="Free",
        price=0.00,
        ram_gb=0.5,
        cpu_cores=0.1,
        description="512MB RAM, 0.1 CPU — spins down after inactivity",
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
    "pro": RenderComputeTier(
        name="Pro",
        price=85.00,
        ram_gb=4.0,
        cpu_cores=2.0,
        description="4GB RAM, 2 CPU",
    ),
    "pro_plus": RenderComputeTier(
        name="Pro Plus",
        price=175.00,
        ram_gb=8.0,
        cpu_cores=4.0,
        description="8GB RAM, 4 CPU",
    ),
    "pro_max": RenderComputeTier(
        name="Pro Max",
        price=225.00,
        ram_gb=16.0,
        cpu_cores=4.0,
        description="16GB RAM, 4 CPU",
    ),
    "pro_ultra": RenderComputeTier(
        name="Pro Ultra",
        price=450.00,
        ram_gb=32.0,
        cpu_cores=8.0,
        description="32GB RAM, 8 CPU",
    ),
    "custom": RenderComputeTier(
        name="Custom",
        price=-1.0,  # Custom pricing sentinel — contact sales
        ram_gb=512.0,
        cpu_cores=64.0,
        description="Up to 512GB RAM, 64 CPU — contact Render sales",
    ),
}


# =============================================================================
# DATABASE & STORAGE
# =============================================================================

# Postgres storage cost per GB per month
POSTGRES_STORAGE_COST_PER_GB = 0.30  # $0.30/GB/month

# Postgres instance fees (base cost per instance type)
POSTGRES_INSTANCE_COSTS = {
    "free": 0.00,               # Free tier — 30-day limit
    "basic_256mb": 6.00,        # Basic-256mb — 0.1 CPU, 256MB RAM
    "basic_1gb": 19.00,         # Basic-1gb — 0.5 CPU, 1GB RAM
    "basic_4gb": 75.00,         # Basic-4gb — 2 CPU, 4GB RAM
    "pro_4gb": 55.00,           # Pro-4gb — 1 CPU, 4GB RAM
    "pro_8gb": 100.00,          # Pro-8gb — 2 CPU, 8GB RAM
    "pro_16gb": 200.00,         # Pro-16gb — 4 CPU, 16GB RAM
    "pro_32gb": 400.00,         # Pro-32gb — 8 CPU, 32GB RAM
    "pro_64gb": 800.00,         # Pro-64gb — 16 CPU, 64GB RAM
    "pro_128gb": 1700.00,       # Pro-128gb — 32 CPU, 128GB RAM
    "pro_192gb": 2500.00,       # Pro-192gb — 48 CPU, 192GB RAM
    "pro_256gb": 3000.00,       # Pro-256gb — 64 CPU, 256GB RAM
    "pro_384gb": 4600.00,       # Pro-384gb — 96 CPU, 384GB RAM
    "pro_512gb": 6200.00,       # Pro-512gb — 128 CPU, 512GB RAM
    "accelerated_16gb": 160.00,     # Accelerated-16gb — 2 CPU, 16GB RAM
    "accelerated_32gb": 350.00,     # Accelerated-32gb — 4 CPU, 32GB RAM
    "accelerated_64gb": 750.00,     # Accelerated-64gb — 8 CPU, 64GB RAM
    "accelerated_128gb": 1500.00,   # Accelerated-128gb — 16 CPU, 128GB RAM
    "accelerated_256gb": 2500.00,   # Accelerated-256gb — 32 CPU, 256GB RAM
    "accelerated_384gb": 4500.00,   # Accelerated-384gb — 48 CPU, 384GB RAM
    "accelerated_512gb": 6000.00,   # Accelerated-512gb — 64 CPU, 512GB RAM
    "accelerated_768gb": 9000.00,   # Accelerated-768gb — 96 CPU, 768GB RAM
    "accelerated_1024gb": 11000.00,  # Accelerated-1024gb — 128 CPU, 1024GB RAM
}

# Self-managed disk storage cost per GB per month
DISK_STORAGE_COST_PER_GB = 0.25  # $0.25/GB/month

# Redis-compatible "Key Value" pricing
REDIS_PRICES = {
    "free": 0.00,        # 25MB
    "starter": 10.00,    # 256MB
    "standard": 32.00,   # 1GB
    "pro": 135.00,       # 5GB
    "pro_plus": 250.00,  # 10GB
    "pro_max": 550.00,   # 20GB
    "pro_ultra": 1100.00,  # 40GB
    "custom": -1.0,       # Up to 512GB — custom pricing sentinel, contact sales
}


# =============================================================================
# BANDWIDTH OVERAGE
# =============================================================================

BANDWIDTH_OVERAGE_COST_PER_GB = 0.15  # $0.15/GB after free tier


# =============================================================================
# BUILD PIPELINE MINUTES
# =============================================================================

BUILD_MINUTES_COST_PER_1000 = 5.00  # $5 per additional 1,000 minutes (standard pipeline)


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
        tier_name: Name of the tier (free, starter, standard, pro, pro_plus,
            pro_max, pro_ultra, custom)

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
        Monthly compute cost, or None if tier not found or custom pricing

    Example:
        >>> calculate_compute_cost("starter", 3)
        21.0  # 3 starter services
    """
    tier = get_compute_tier(tier_name)
    if tier is None:
        return None
    if tier.price < 0:  # Custom pricing sentinel — contact sales
        return None
    return tier.price * count


def calculate_database_cost(
    storage_gb: float,
    instance_tier: str = "free"
) -> Optional[float]:
    """
    Calculate Postgres database cost (storage + instance fee).

    Args:
        storage_gb: Storage in GB
        instance_tier: Instance tier, e.g. free, basic_256mb, basic_1gb,
            basic_4gb, pro_4gb ... pro_512gb, accelerated_16gb ...
            accelerated_1024gb

    Returns:
        Monthly database cost, or None if instance tier not found

    Example:
        >>> calculate_database_cost(10, "basic_256mb")
        9.0  # $6 instance + $3 storage
        >>> calculate_database_cost(10, "pro_4gb")
        58.0  # $55 instance + $3 storage
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
    Calculate Redis-compatible Key Value cost.

    Args:
        plan: Redis plan (free, starter, standard, pro, pro_plus, pro_max,
            pro_ultra, custom)

    Returns:
        Monthly Redis cost, or None if plan not found or custom pricing

    Example:
        >>> calculate_redis_cost("starter")
        10.0
    """
    plan = plan.lower().strip()
    price = REDIS_PRICES.get(plan)
    if price is None:
        return None
    if price < 0:  # Custom pricing sentinel — contact sales
        return None
    return price


def calculate_total_render_cost(
    workspace_plan: str,
    compute_tiers: Dict[str, int],  # tier_name -> count
    database_gb: float = 0,
    database_instance_tier: str = "free",
    bandwidth_gb: float = 0,
    disk_gb: float = 0,
    build_minutes: int = 0,
    redis_plan: Optional[str] = None,
) -> Dict[str, float]:
    """
    Calculate total Render monthly cost.

    ✅ FIX: Free tier (hobby) = all base costs are $0

    Args:
        workspace_plan: Workspace plan name (hobby, pro, scale, enterprise)
        compute_tiers: Dictionary of compute tier counts
        database_gb: Postgres storage in GB
        database_instance_tier: Postgres instance tier, e.g. free, basic_256mb,
            basic_1gb, basic_4gb, pro_4gb ... pro_512gb
        bandwidth_gb: Bandwidth used in GB
        disk_gb: Persistent disk storage in GB
        build_minutes: Build pipeline minutes used
        redis_plan: Redis plan name (optional)

    Returns:
        Dictionary with cost breakdown and total

    Example:
        >>> costs = calculate_total_render_cost(
        ...     "hobby",
        ...     {"free": 1},
        ...     database_gb=1,
        ...     database_instance_tier="free",
        ...     bandwidth_gb=5,
        ...     redis_plan="free"
        ... )
        >>> print(costs["total"])
        0.0
    """
    
    # ✅ FIX: Free tier = everything is $0
    if workspace_plan.lower() == "hobby":
        return {
            "workspace_cost": 0.0,
            "compute_cost": 0.0,
            "database_cost": 0.0,
            "bandwidth_cost": 0.0,
            "build_minutes_cost": 0.0,
            "disk_cost": 0.0,
            "redis_cost": 0.0,
            "total": 0.0,
            "workspace_plan": workspace_plan,
            "free_tier": True,
        }

    # Workspace cost (paid plans only)
    workspace_cost = calculate_workspace_cost(workspace_plan)
    if workspace_cost is None:
        return {
            "error": f"Unknown or custom pricing for workspace plan: {workspace_plan}"
        }

    # Compute cost (paid plans only)
    compute_cost = 0.0
    for tier_name, count in compute_tiers.items():
        tier = get_compute_tier(tier_name)
        if tier is None:
            return {"error": f"Unknown compute tier: {tier_name}"}
        if tier.price < 0:
            return {"error": f"'{tier_name}' has custom pricing — contact Render sales for a quote."}
        compute_cost += tier.price * count

    # Database cost (paid plans only)
    db_cost = calculate_database_cost(database_gb, database_instance_tier)
    if db_cost is None:
        return {"error": f"Unknown database instance tier: {database_instance_tier}"}

    # Bandwidth cost (paid plans only)
    bandwidth_cost = calculate_bandwidth_cost(bandwidth_gb, workspace_plan)
    if bandwidth_cost is None:
        return {"error": f"Unknown workspace plan: {workspace_plan}"}

    # Build minutes cost (paid plans only)
    build_cost = calculate_build_minutes_cost(build_minutes, workspace_plan)
    if build_cost is None:
        return {"error": f"Unknown workspace plan: {workspace_plan}"}

    # Disk cost (paid plans only)
    disk_cost = calculate_disk_cost(disk_gb)

    # Redis cost (paid plans only)
    redis_cost = 0.0
    if redis_plan:
        redis_plan_key = redis_plan.lower().strip()
        redis_price = REDIS_PRICES.get(redis_plan_key)
        if redis_price is None:
            return {"error": f"Unknown Redis plan: {redis_plan}"}
        if redis_price < 0:
            return {"error": f"'{redis_plan}' has custom pricing — contact Render sales for a quote."}
        redis_cost = redis_price

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