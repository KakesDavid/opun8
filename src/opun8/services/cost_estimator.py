"""
Cost Estimator Service
======================

Estimates deployment costs for different platforms before deployment.

This service:
    1. Detects the project type and expected resources
    2. Fetches pricing data for the selected platform
    3. Calculates estimated monthly costs
    4. Returns a clean breakdown for display

Why This File Exists:
    - Centralizes cost estimation logic
    - Uses static pricing data (fast, works offline)
    - Provides consistent cost breakdown across platforms

Usage:
    from opun8.services.cost_estimator import CostEstimator

    estimator = CostEstimator()
    estimate = estimator.estimate("vercel", project_info)
    print(estimate["total"])

Author: OPUN8 Team
Version: 0.1.4
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from opun8.core.detector import ProjectInfo
from opun8.providers.vercel.pricing import (
    FRAMEWORK_RESOURCES as VERCEL_RESOURCES,
    calculate_bandwidth_cost as calculate_vercel_bandwidth,
    calculate_build_cost as calculate_vercel_build,
    calculate_function_cost as calculate_vercel_functions,
    get_plan as get_vercel_plan,
)
from opun8.providers.render.pricing import (
    calculate_total_render_cost,
)


# =============================================================================
# DATA MODELS
# =============================================================================

@dataclass
class CostEstimate:
    """
    Cost estimate for a deployment.

    Attributes:
        platform: Platform name (vercel, render)
        total: Total estimated monthly cost
        breakdown: Dictionary of cost components
        plan: Selected plan name
        warning: Optional warning message
        error: Optional error message
        is_custom_pricing: Whether pricing is custom (enterprise)
    """
    platform: str
    total: Optional[float] = None
    breakdown: Dict[str, float] = field(default_factory=dict)
    plan: Optional[str] = None
    warning: Optional[str] = None
    error: Optional[str] = None
    is_custom_pricing: bool = False

    @property
    def is_valid(self) -> bool:
        """Check if the estimate is valid."""
        return self.error is None and self.total is not None

    @property
    def formatted_total(self) -> str:
        """Get formatted total cost."""
        if self.total is None:
            return "N/A"
        return f"${self.total:.2f}/month"


# =============================================================================
# COST ESTIMATOR
# =============================================================================

class CostEstimator:
    """
    Service for estimating deployment costs.

    Attributes:
        project_info: Detected project information
        team_size: Number of team members
        custom_bandwidth_gb: Custom bandwidth estimate (overrides detection)
        custom_build_minutes: Custom build minutes (overrides detection)
        custom_functions: Custom function invocations (overrides detection)
    """

    def __init__(self, project_info: Optional[ProjectInfo] = None):
        """
        Initialize the cost estimator.

        Args:
            project_info: Detected project information
        """
        self.project_info = project_info
        self.team_size = 1
        self.custom_bandwidth_gb = None
        self.custom_build_minutes = None
        self.custom_functions = None

    def set_team_size(self, size: int) -> None:
        """Set team size for cost estimation."""
        self.team_size = max(1, size)

    def set_bandwidth_gb(self, bandwidth: float) -> None:
        """Override bandwidth estimation."""
        self.custom_bandwidth_gb = bandwidth

    def set_build_minutes(self, minutes: int) -> None:
        """Override build minutes estimation."""
        self.custom_build_minutes = minutes

    def set_functions(self, functions: int) -> None:
        """Override function invocations estimation."""
        self.custom_functions = functions

    def _get_framework_resources(self) -> Dict[str, float]:
        """
        Get estimated resources based on the project framework.

        Returns a copy of the resources to avoid mutating global state.
        """
        if self.project_info is None:
            resources = VERCEL_RESOURCES["unknown"].copy()
        else:
            framework = self.project_info.framework
            resources = VERCEL_RESOURCES.get(framework, VERCEL_RESOURCES["unknown"]).copy()

        # Apply custom overrides if set
        if self.custom_bandwidth_gb is not None:
            resources["bandwidth_gb"] = self.custom_bandwidth_gb
        if self.custom_build_minutes is not None:
            resources["build_minutes"] = self.custom_build_minutes
        if self.custom_functions is not None:
            resources["functions"] = self.custom_functions

        return resources

    # =========================================================================
    # VERCEL ESTIMATION
    # =========================================================================

    def estimate_vercel(
        self,
        plan: str = "pro",
        addons: Optional[Dict[str, bool]] = None,
    ) -> CostEstimate:
        """
        Estimate Vercel deployment cost.

        Args:
            plan: Plan name (hobby, pro)
            addons: Dictionary of add-ons to include

        Returns:
            CostEstimate object

        Example:
            >>> estimator = CostEstimator()
            >>> estimate = estimator.estimate_vercel("pro")
            >>> print(estimate.formatted_total)
            $20.00/month
        """
        # Get plan info
        plan_obj = get_vercel_plan(plan)
        if plan_obj is None:
            return CostEstimate(
                platform="vercel",
                error=f"Unknown plan: {plan}"
            )

        # Check if custom pricing
        is_custom = plan.lower() == "enterprise"
        if is_custom:
            return CostEstimate(
                platform="vercel",
                plan="Enterprise",
                is_custom_pricing=True,
                warning="Enterprise pricing is custom — contact Vercel sales for accurate pricing."
            )

        resources = self._get_framework_resources()

        # Calculate costs
        bandwidth_cost = calculate_vercel_bandwidth(
            resources.get("bandwidth_gb", 10),
            plan
        )
        build_cost = calculate_vercel_build(
            resources.get("build_minutes", 50),
            plan
        )
        function_cost = calculate_vercel_functions(
            resources.get("functions", 50000),
            plan
        )

        # Base seat cost
        base_cost = plan_obj.base_price * self.team_size

        # Add-ons
        if addons is None:
            addons = {}
        addon_costs = 0.0
        from opun8.providers.vercel.pricing import OverageCosts
        if addons.get("saml_sso", False):
            addon_costs += OverageCosts.SAML_SSO_COST
        if addons.get("hipaa_baa", False):
            addon_costs += OverageCosts.HIPAA_BAA_COST
        if addons.get("advanced_deployment_protection", False):
            addon_costs += OverageCosts.ADVANCED_DEPLOYMENT_PROTECTION

        total = base_cost + bandwidth_cost + build_cost + function_cost + addon_costs

        # Build breakdown
        breakdown = {}
        if base_cost > 0:
            breakdown["Seats"] = base_cost
        if bandwidth_cost > 0:
            breakdown["Bandwidth"] = bandwidth_cost
        if build_cost > 0:
            breakdown["Build Minutes"] = build_cost
        if function_cost > 0:
            breakdown["Functions"] = function_cost
        if addon_costs > 0:
            breakdown["Add-ons"] = addon_costs

        return CostEstimate(
            platform="vercel",
            total=total,
            breakdown=breakdown,
            plan=plan_obj.name,
            is_custom_pricing=is_custom,
        )

    # =========================================================================
    # RENDER ESTIMATION
    # =========================================================================

    def estimate_render(
        self,
        workspace_plan: str = "hobby",
        compute_tiers: Optional[Dict[str, int]] = None,
        database_gb: float = 1,
        bandwidth_gb: Optional[float] = None,
        redis_plan: Optional[str] = None,
    ) -> CostEstimate:
        """
        Estimate Render deployment cost.

        Args:
            workspace_plan: Workspace plan name (hobby, pro, scale)
            compute_tiers: Dictionary of compute tier counts
            database_gb: Postgres storage in GB
            bandwidth_gb: Bandwidth used in GB (auto-detected if not provided)
            redis_plan: Redis plan name

        Returns:
            CostEstimate object

        Example:
            >>> estimator = CostEstimator()
            >>> estimate = estimator.estimate_render(
            ...     "pro",
            ...     {"starter": 2, "standard": 1}
            ... )
            >>> print(estimate.formatted_total)
            $64.00/month
        """
        if compute_tiers is None:
            compute_tiers = {"starter": 1}

        # Get bandwidth
        if bandwidth_gb is None:
            resources = self._get_framework_resources()
            bandwidth_gb = resources.get("bandwidth_gb", 10)

        try:
            result = calculate_total_render_cost(
                workspace_plan=workspace_plan,
                compute_tiers=compute_tiers,
                database_gb=database_gb,
                bandwidth_gb=bandwidth_gb,
                redis_plan=redis_plan,
            )
        except Exception as e:
            return CostEstimate(
                platform="render",
                error=f"Failed to calculate cost: {str(e)}"
            )

        if "error" in result:
            return CostEstimate(
                platform="render",
                error=result["error"]
            )

        # Check if custom pricing
        is_custom = workspace_plan.lower() == "enterprise"
        if is_custom:
            return CostEstimate(
                platform="render",
                plan="Enterprise",
                is_custom_pricing=True,
                warning="Enterprise pricing is custom — contact Render sales for accurate pricing."
            )

        # Build breakdown
        breakdown = {}
        if result.get("workspace_cost", 0) > 0:
            breakdown["Workspace"] = result.get("workspace_cost", 0)
        if result.get("compute_cost", 0) > 0:
            breakdown["Compute"] = result.get("compute_cost", 0)
        if result.get("database_cost", 0) > 0:
            breakdown["Database"] = result.get("database_cost", 0)
        if result.get("bandwidth_cost", 0) > 0:
            breakdown["Bandwidth"] = result.get("bandwidth_cost", 0)
        if result.get("redis_cost", 0) > 0:
            breakdown["Redis"] = result.get("redis_cost", 0)

        total = result.get("total", 0)

        return CostEstimate(
            platform="render",
            total=total,
            breakdown=breakdown,
            plan=workspace_plan,
            is_custom_pricing=is_custom,
        )

    # =========================================================================
    # AUTO DETECTION
    # =========================================================================

    def estimate(self, platform: str = "vercel") -> CostEstimate:
        """
        Auto-detect and estimate cost for a platform.

        Args:
            platform: Platform name (vercel, render)

        Returns:
            CostEstimate object

        Example:
            >>> estimator = CostEstimator(project_info)
            >>> estimate = estimator.estimate("vercel")
            >>> print(estimate.formatted_total)
            $20.00/month
        """
        platform = platform.lower().strip()

        if platform == "vercel":
            return self.estimate_vercel()
        elif platform == "render":
            return self.estimate_render()
        else:
            return CostEstimate(
                platform=platform,
                error=f"Unknown platform: {platform}"
            )


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_estimator: Optional[CostEstimator] = None
_estimator_project_info: Optional[ProjectInfo] = None


def get_cost_estimator(project_info: Optional[ProjectInfo] = None) -> CostEstimator:
    """
    Get or create the global cost estimator instance.

    Preserves configuration when called multiple times with different project info.

    Args:
        project_info: Detected project information

    Returns:
        CostEstimator singleton instance
    """
    global _estimator, _estimator_project_info

    if _estimator is None:
        _estimator = CostEstimator(project_info)
        _estimator_project_info = project_info
    elif project_info is not None and _estimator_project_info is None:
        # First time we have project info — update the existing instance
        _estimator.project_info = project_info
        _estimator_project_info = project_info

    return _estimator


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    "CostEstimate",
    "CostEstimator",
    "get_cost_estimator",
]