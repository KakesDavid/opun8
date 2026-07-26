"""
Backend URLs
============

Centralized definition of all API endpoint URLs for the OPUN8 backend.

This module builds all full endpoint URLs. All other modules should import
URLs from here.

Why This File Exists:
    - Single source of truth for all API endpoints
    - Easy to update if backend URL changes
    - Clean separation of concerns
    - Prevents hardcoded URLs scattered across the codebase

Usage:
    from opun8.services.backend_urls import (
        AUTH_REGISTER,
        AUTH_LOGIN,
        CLONE_CREATE,
        USER_PROFILE
    )

    response = requests.post(AUTH_REGISTER, json={...})

Author: OPUN8 Team
Version: 0.1.4
"""

# =============================================================================
# API BASE URL (LIVE RENDER BACKEND)
# =============================================================================

# ✅ CORRECTED: Using the live Render backend (hyphenated version)
API_BASE_URL = "https://api-opun8.onrender.com"

# ✅ API version
API_VERSION = "v1"


# =============================================================================
# AUTHENTICATION ENDPOINTS
# =============================================================================

AUTH_REGISTER = f"{API_BASE_URL}/{API_VERSION}/auth/register"
AUTH_LOGIN = f"{API_BASE_URL}/{API_VERSION}/auth/login"
AUTH_VERIFY_OTP = f"{API_BASE_URL}/{API_VERSION}/auth/verify-otp"
AUTH_RESEND_OTP = f"{API_BASE_URL}/{API_VERSION}/auth/resend-otp"
AUTH_LOGOUT = f"{API_BASE_URL}/{API_VERSION}/auth/logout"
AUTH_REFRESH = f"{API_BASE_URL}/{API_VERSION}/auth/refresh"


# =============================================================================
# USER ENDPOINTS
# =============================================================================

USER_PROFILE = f"{API_BASE_URL}/{API_VERSION}/user/profile"
USER_LIMITS = f"{API_BASE_URL}/{API_VERSION}/user/limits"
USER_STATS = f"{API_BASE_URL}/{API_VERSION}/user/stats"


# =============================================================================
# CLONE ENDPOINTS
# =============================================================================

CLONE_CREATE = f"{API_BASE_URL}/{API_VERSION}/clones"
CLONE_HISTORY = f"{API_BASE_URL}/{API_VERSION}/clones/history"
CLONE_STATUS = f"{API_BASE_URL}/{API_VERSION}/clones/{{clone_id}}"
CLONE_DELETE = f"{API_BASE_URL}/{API_VERSION}/clones/{{clone_id}}"
CLONE_EXPORT = f"{API_BASE_URL}/{API_VERSION}/clones/{{clone_id}}/export"
CLONE_PROGRESS = f"{API_BASE_URL}/{API_VERSION}/clones/progress/{{clone_id}}"


# =============================================================================
# PAYMENT / SUBSCRIPTION ENDPOINTS
# =============================================================================

PAYMENT_CHECKOUT = f"{API_BASE_URL}/{API_VERSION}/payment/checkout"
PAYMENT_WEBHOOK = f"{API_BASE_URL}/{API_VERSION}/payment/webhook"
SUBSCRIPTION_STATUS = f"{API_BASE_URL}/{API_VERSION}/subscription/status"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_clone_status_url(clone_id: str) -> str:
    """
    Get the status endpoint URL for a specific clone.

    Args:
        clone_id: The ID of the clone operation

    Returns:
        Full URL to check clone status (GET request)

    Example:
        >>> get_clone_status_url("abc123")
        "https://api-opun8.onrender.com/v1/clones/abc123"
    """
    return CLONE_STATUS.format(clone_id=clone_id)


def get_clone_delete_url(clone_id: str) -> str:
    """
    Get the delete endpoint URL for a specific clone.

    Args:
        clone_id: The ID of the clone operation

    Returns:
        Full URL to delete a clone (DELETE request)
    """
    return CLONE_DELETE.format(clone_id=clone_id)


def get_clone_export_url(clone_id: str) -> str:
    """
    Get the export endpoint URL for a specific clone.

    Args:
        clone_id: The ID of the clone operation

    Returns:
        Full URL to export a clone
    """
    return CLONE_EXPORT.format(clone_id=clone_id)


def get_clone_progress_url(clone_id: str) -> str:
    """
    Get the progress endpoint URL for a specific clone (SSE).

    Args:
        clone_id: The ID of the clone operation

    Returns:
        Full URL to stream clone progress

    Example:
        >>> get_clone_progress_url("abc123")
        "https://api-opun8.onrender.com/v1/clones/progress/abc123"
    """
    return CLONE_PROGRESS.format(clone_id=clone_id)


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Base URL
    "API_BASE_URL",
    "API_VERSION",
    # Auth
    "AUTH_REGISTER",
    "AUTH_LOGIN",
    "AUTH_VERIFY_OTP",
    "AUTH_RESEND_OTP",
    "AUTH_LOGOUT",
    "AUTH_REFRESH",
    # User
    "USER_PROFILE",
    "USER_LIMITS",
    "USER_STATS",
    # Clone
    "CLONE_CREATE",
    "CLONE_HISTORY",
    "CLONE_STATUS",
    "CLONE_DELETE",
    "CLONE_EXPORT",
    "CLONE_PROGRESS",
    # Payment
    "PAYMENT_CHECKOUT",
    "PAYMENT_WEBHOOK",
    "SUBSCRIPTION_STATUS",
    # Helpers
    "get_clone_status_url",
    "get_clone_delete_url",
    "get_clone_export_url",
    "get_clone_progress_url",
]