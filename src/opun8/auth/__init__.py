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