"""
Authentication module for Opun8.
"""

from opun8.auth.github_oauth import (
    login_to_github as _login_to_github,
    get_github_token,
    is_authenticated,
    logout,
    save_github_token,
    get_authenticated_user,
    get_github_user,
    list_github_repos,
    create_github_repo,
)

# Re-export Vercel auth functions from the providers module
from opun8.providers.vercel.auth import (
    login_to_vercel,
    get_vercel_token,
    is_vercel_authenticated,
    logout_vercel,
    show_vercel_projects,
    switch_vercel_team,
    set_deploy_callback,
    get_vercel_user,
    get_vercel_scope,
)


def login_to_github() -> bool:
    """
    Authenticate with GitHub using OAuth.
    
    ✅ FIX: This function now only handles the actual OAuth flow
    and does NOT show its own UI. The UI is handled by 
    `ui/messages.py` -> `github_auth_start()`.
    
    Returns:
        True if authentication succeeded, False otherwise.
    """
    try:
        # Call the underlying GitHub auth function
        # The UI is handled by messages.py, not here
        token = _login_to_github()
        return token is not None
    except Exception:
        return False


__all__ = [
    # GitHub
    "login_to_github",
    "get_github_token",
    "is_authenticated",
    "logout",
    "save_github_token",
    "get_authenticated_user",
    "get_github_user",
    "list_github_repos",
    "create_github_repo",
    # Vercel
    "login_to_vercel",
    "get_vercel_token",
    "is_vercel_authenticated",
    "logout_vercel",
    "show_vercel_projects",
    "switch_vercel_team",
    "set_deploy_callback",
    "get_vercel_user",
    "get_vercel_scope",
]