"""
Render provider for Opun8.

Handles authentication and deployment to Render.com via:
    - OAuth 2.0 (if supported by Render)
    - Personal API keys (primary method)

Exports:
    - auth: login, logout, token management
    - deploy: deploy projects to Render
    - models: data models for Render API
"""

from opun8.providers.render.auth import (
    login_to_render,
    logout_render,
    is_render_authenticated,
    get_render_token,
    get_render_user,
    get_render_owner_id,
    save_render_token,
    save_api_key,
    clear_api_key,
    refresh_render_token,
    list_render_owners,
    prompt_owner_selection,
    switch_render_owner,
    show_render_auth_status,
)

from opun8.providers.render.deploy import (
    deploy_to_render,
    get_render_service_status,
    delete_render_service,
    list_render_services,
    get_render_deployment_logs,
)

from opun8.providers.render.models import (
    ServiceType,
    EnvType,
    Region,
    AutoDeploy,
    Service,
    Deployment,
    EnvVar,
    ServiceDetails,
    CreateServiceRequest,
    CreateDeploymentRequest,
    User,
    OAuthTokenResponse,
    map_framework_to_render_env,
    get_default_build_command,
    get_default_start_command,
)

__all__ = [
    # Auth
    "login_to_render",
    "logout_render",
    "is_render_authenticated",
    "get_render_token",
    "get_render_user",
    "get_render_owner_id",
    "save_render_token",
    "save_api_key",
    "clear_api_key",
    "refresh_render_token",
    "list_render_owners",
    "prompt_owner_selection",
    "switch_render_owner",
    "show_render_auth_status",
    # Deploy
    "deploy_to_render",
    "get_render_service_status",
    "delete_render_service",
    "list_render_services",
    "get_render_deployment_logs",
    # Models
    "ServiceType",
    "EnvType",
    "Region",
    "AutoDeploy",
    "Service",
    "Deployment",
    "EnvVar",
    "ServiceDetails",
    "CreateServiceRequest",
    "CreateDeploymentRequest",
    "User",
    "OAuthTokenResponse",
    "map_framework_to_render_env",
    "get_default_build_command",
    "get_default_start_command",
]