"""
Netlify provider package for Opun8.

This package provides Netlify integration including:
    - OAuth 2.0 authentication (via auth.py)
    - Site deployment (via deploy.py - coming soon)
    - Pricing data (via pricing.py - coming soon)

Exports:
    - login_to_netlify: Start OAuth flow
    - is_netlify_authenticated: Check auth status
    - get_netlify_token: Get stored token
    - logout_netlify: Clear stored token
    - netlify_auth_command: CLI auth command
    - get_netlify_user: Get stored user info
    - get_netlify_user_info: Fetch user info from API
    - show_netlify_sites: List sites
    - list_netlify_sites: Get sites list
    - save_netlify_token: Save token to storage
    - refresh_netlify_token: Refresh expired token
    - set_deploy_callback: Set deploy callback
    - save_pat_token: Save PAT with user info
    - get_pat_token: Get stored PAT
    - clear_pat_token: Remove PAT
"""

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
)

__all__ = [
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
    "set_deploy_callback",
    "save_pat_token",
    "get_pat_token",
    "clear_pat_token",
]