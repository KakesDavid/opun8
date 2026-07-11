"""
Authentication module for Opun8.
"""

from opun8.auth.github_oauth import (
    login_to_github,
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