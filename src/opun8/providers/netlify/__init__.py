"""
Netlify provider package for OPUN8.

This package provides complete Netlify integration including:
    - OAuth 2.0 authentication and token management (auth.py)
    - Site deployment with file upload, conflict resolution, and .gitignore support (deploy.py)
    - Pricing data, cost estimation, and plan recommendations (pricing.py)

All modules are fully implemented and production-ready.

Exports:
    # Authentication (from auth.py)
    - login_to_netlify: Start OAuth flow or PAT login
    - is_netlify_authenticated: Check auth status (local, no network calls)
    - get_netlify_token: Get stored token with auto-refresh
    - logout_netlify: Clear stored token
    - netlify_auth_command: CLI auth command
    - get_netlify_user: Get stored user info
    - get_netlify_user_info: Fetch user info from API
    - show_netlify_sites: Display sites in terminal with rich UI
    - list_netlify_sites: Get paginated sites list
    - save_netlify_token: Save token to storage
    - refresh_netlify_token: Refresh expired token
    - refresh_if_needed: Refresh token only if near expiry
    - set_deploy_callback: Set deploy callback for site listing
    - save_pat_token: Save Personal Access Token with user info
    - get_pat_token: Get stored PAT
    - clear_pat_token: Remove PAT

    # Deployment (from deploy.py)
    - deploy_to_netlify: Deploy project to Netlify with conflict resolution
    - prompt_for_env_vars: Interactive environment variable collection

    # Pricing (from pricing.py)
    - PLANS: Dictionary of all Netlify plans
    - UsageMeterCosts: Credit costs per usage meter
    - FRAMEWORK_RESOURCES: Estimated resource usage per framework
    - NetlifyPlan: Plan dataclass
    - get_plan: Get plan by name
    - get_framework_resources: Get estimated resources for a framework
    - calculate_credits_used: Calculate credits from usage
    - calculate_credit_shortfall: Check if usage exceeds plan
    - calculate_recharge_cost: Calculate cost of additional credits
    - calculate_total_netlify_cost: Complete cost breakdown
    - get_available_plans: Get all non-enterprise plans
    - get_plan_recommendation: Recommend plan based on estimated usage

Version: 0.1.6
Author: OPUN8 Team
"""

# =============================================================================
# Authentication Exports
# =============================================================================

from .auth import (
    login_to_netlify,
    is_netlify_authenticated,
    get_netlify_token,
    logout_netlify,
    netlify_auth_command,
    get_netlify_user,
    get_netlify_user_info,
    show_netlify_sites,
    list_netlify_sites,
    save_netlify_token,
    refresh_netlify_token,
    set_deploy_callback,
    save_pat_token,
    get_pat_token,
    clear_pat_token,
    refresh_if_needed,
)

# =============================================================================
# Deployment Exports
# =============================================================================

from .deploy import (
    deploy_to_netlify,
    prompt_for_env_vars,
)

# =============================================================================
# Pricing Exports
# =============================================================================

from .pricing import (
    PLANS,
    UsageMeterCosts,
    FRAMEWORK_RESOURCES,
    NetlifyPlan,
    get_plan,
    get_framework_resources,
    calculate_credits_used,
    calculate_credit_shortfall,
    calculate_recharge_cost,
    calculate_total_netlify_cost,
    get_available_plans,
    get_plan_recommendation,
)

# =============================================================================
# Public API
# =============================================================================

__all__ = [
    # Authentication
    "login_to_netlify",
    "is_netlify_authenticated",
    "get_netlify_token",
    "logout_netlify",
    "netlify_auth_command",
    "get_netlify_user",
    "get_netlify_user_info",
    "show_netlify_sites",
    "list_netlify_sites",
    "save_netlify_token",
    "refresh_netlify_token",
    "refresh_if_needed",
    "set_deploy_callback",
    "save_pat_token",
    "get_pat_token",
    "clear_pat_token",
    # Deployment
    "deploy_to_netlify",
    "prompt_for_env_vars",
    # Pricing
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

# =============================================================================
# Module Metadata
# =============================================================================

__version__ = "0.1.6"
__description__ = "Complete Netlify provider for OPUN8 deployment platform"