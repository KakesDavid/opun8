"""
Render API data models for Opun8.

Defines the data structures used for Render API requests and responses.
Based on Render's official API documentation:
https://render.com/docs/api

These models are used by:
    - auth.py: OAuth token exchange and user info
    - deploy.py: Creating services and deployments
"""

from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, HttpUrl, ConfigDict, SecretStr, field_validator
import re


# ──────────────────────────────────────────────────────────────
# ENUMS (for reference, but response models use str for safety)
# ──────────────────────────────────────────────────────────────

class ServiceType(str, Enum):
    """Render service types."""
    WEB_SERVICE = "web_service"
    STATIC_SITE = "static_site"
    PRIVATE_SERVICE = "private_service"
    BACKGROUND_WORKER = "background_worker"
    CRON_JOB = "cron_job"


class EnvType(str, Enum):
    """Render environment types for web services."""
    NODE = "node"
    PYTHON = "python"
    RUBY = "ruby"
    GO = "go"
    STATIC = "static"
    ELIXIR = "elixir"
    RUST = "rust"
    PHP = "php"
    JAVA = "java"
    DOCKER = "docker"


class Region(str, Enum):
    """Render deployment regions."""
    OREGON = "oregon"
    FRANKFURT = "frankfurt"
    SINGAPORE = "singapore"
    OHIO = "ohio"
    VIRGINIA = "virginia"


class AutoDeploy(str, Enum):
    """Auto-deploy setting for Render services."""
    YES = "yes"
    NO = "no"


# ──────────────────────────────────────────────────────────────
# OAUTH MODELS
# ──────────────────────────────────────────────────────────────

class OAuthTokenResponse(BaseModel):
    """Response from Render's OAuth token endpoint."""
    access_token: str = Field(..., description="Access token for API requests")
    refresh_token: str = Field(..., description="Refresh token for obtaining new access tokens")
    expires_in: int = Field(..., description="Token expiry time in seconds")
    token_type: str = Field(default="Bearer", description="Token type")
    scope: Optional[str] = Field(None, description="Scopes granted")

    model_config = ConfigDict(extra="allow")


class OAuthErrorResponse(BaseModel):
    """Error response from Render's OAuth token endpoint."""
    error: str = Field(..., description="Error code")
    error_description: Optional[str] = Field(None, description="Human-readable error description")


# ──────────────────────────────────────────────────────────────
# USER MODELS
# ──────────────────────────────────────────────────────────────

class User(BaseModel):
    """Render user information."""
    id: str = Field(..., description="User ID")
    name: str = Field(..., description="User's full name")
    email: str = Field(..., description="User's email address")
    username: str = Field(..., description="User's username")
    created_at: datetime = Field(..., description="Account creation timestamp")

    model_config = ConfigDict(extra="allow")


# ──────────────────────────────────────────────────────────────
# ENVIRONMENT VARIABLE MODELS
# ──────────────────────────────────────────────────────────────

class EnvVar(BaseModel):
    """Environment variable for a Render service."""
    key: str = Field(..., description="Variable name", min_length=1, max_length=100)
    value: Union[str, SecretStr] = Field(..., description="Variable value")
    secret: bool = Field(default=False, description="Whether the value is secret")

    model_config = ConfigDict(extra="forbid")

    @field_validator("key")
    @classmethod
    def validate_key(cls, v: str) -> str:
        """Validate environment variable key format."""
        if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', v):
            raise ValueError(
                f"Invalid env var key '{v}'. Must start with letter or underscore, "
                "and contain only letters, numbers, and underscores."
            )
        return v


class EnvVarResponse(BaseModel):
    """Response from Render's environment variable endpoint."""
    id: str = Field(..., description="Environment variable ID")
    key: str = Field(..., description="Variable name")
    value: Optional[str] = Field(None, description="Variable value (may be redacted)")
    secret: bool = Field(..., description="Whether the value is secret")

    model_config = ConfigDict(extra="allow")


# ──────────────────────────────────────────────────────────────
# SERVICE MODELS
# ──────────────────────────────────────────────────────────────

class Service(BaseModel):
    """Render service representation."""
    id: str = Field(..., description="Service ID")
    name: str = Field(..., description="Service name")
    type: str = Field(..., description="Type of service")  # str, not Enum, for forward compatibility
    status: str = Field(..., description="Current service status")  # str, not Enum
    url: Optional[str] = Field(None, description="Live service URL")  # str, not HttpUrl (handles empty strings)
    repo: Optional[str] = Field(None, description="GitHub repository URL")
    env: Optional[str] = Field(None, description="Environment type")
    region: Optional[str] = Field(None, description="Deployment region")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    owner_id: Optional[str] = Field(None, description="Owner/workspace ID")

    model_config = ConfigDict(extra="allow")

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v: Any) -> Optional[str]:
        """Handle empty strings and None for URL."""
        if v is None or v == "":
            return None
        return str(v)


class ServiceDetails(BaseModel):
    """
    Nested service details for Render API requests.
    Render nests build/start commands inside serviceDetails.
    """
    build_command: Optional[str] = Field(None, description="Command to build the project")
    start_command: Optional[str] = Field(None, description="Command to start the service")
    publish_path: Optional[str] = Field(None, description="Directory to publish for static sites")
    env_vars: Optional[List[EnvVar]] = Field(None, description="Environment variables")
    secret_files: Optional[List[Dict[str, str]]] = Field(None, description="Secret files")
    build_filter: Optional[Dict[str, Any]] = Field(None, description="Build filter configuration")
    root_dir: Optional[str] = Field(None, description="Root directory for the build")
    image: Optional[Dict[str, Any]] = Field(None, description="Docker image configuration")
    environment_id: Optional[str] = Field(None, description="Environment ID")

    model_config = ConfigDict(extra="allow")


class CreateServiceRequest(BaseModel):
    """
    Request payload for creating a Render service.
    Matches Render's POST /v1/services endpoint.
    """
    name: str = Field(..., description="Service name", min_length=1, max_length=100)
    owner_id: str = Field(..., description="Owner/workspace ID (required)")
    type: ServiceType = Field(..., description="Type of service")
    env: EnvType = Field(..., description="Environment type")

    # Repository settings
    repo: Optional[str] = Field(None, description="GitHub repository URL")
    branch: Optional[str] = Field("main", description="Branch to deploy")

    # Auto-deploy setting
    auto_deploy: AutoDeploy = Field(
        default=AutoDeploy.YES,
        description="Auto-deploy on git push"
    )

    # Nested service details
    service_details: Optional[ServiceDetails] = Field(
        None,
        description="Nested service configuration"
    )

    model_config = ConfigDict(extra="forbid")

    def to_api_payload(self) -> Dict[str, Any]:
        """
        Convert to Render's expected API payload format.
        Builds the nested serviceDetails structure.
        """
        # NOTE: Render's create-service endpoint has no top-level "env" field.
        # Runtime/environment is implied by "type" (and, for services that run
        # a process, expressed inside serviceDetails). Sending "env" here gets
        # silently rejected by Render's strict per-type schema.
        payload: Dict[str, Any] = {
            "name": self.name,
            "ownerId": self.owner_id,
            "type": self.type.value,
            "autoDeploy": self.auto_deploy.value,
        }

        if self.repo:
            payload["repo"] = self.repo

        if self.branch:
            payload["branch"] = self.branch

        # Build the nested serviceDetails
        details: Dict[str, Any] = {}
        is_static_site = self.type == ServiceType.STATIC_SITE

        if self.service_details:
            if self.service_details.build_command is not None:
                details["buildCommand"] = self.service_details.build_command
            # startCommand only applies to services that run a long-lived
            # process (web_service, private_service, background_worker).
            # Static sites serve prebuilt files from publishPath and have
            # no process to start — Render rejects startCommand for them.
            if not is_static_site and self.service_details.start_command is not None:
                details["startCommand"] = self.service_details.start_command
            if self.service_details.publish_path is not None:
                details["publishPath"] = self.service_details.publish_path
            if self.service_details.env_vars:
                details["envVars"] = [
                    {"key": v.key, "value": v.value.get_secret_value() if isinstance(v.value, SecretStr) else v.value}
                    for v in self.service_details.env_vars
                ]
            if self.service_details.secret_files:
                details["secretFiles"] = self.service_details.secret_files
            if self.service_details.build_filter:
                details["buildFilter"] = self.service_details.build_filter
            if self.service_details.root_dir:
                details["rootDir"] = self.service_details.root_dir
            if self.service_details.image:
                details["image"] = self.service_details.image
            if self.service_details.environment_id:
                details["environmentId"] = self.service_details.environment_id

        if details:
            payload["serviceDetails"] = details

        return payload


class UpdateServiceRequest(BaseModel):
    """Request payload for updating a Render service."""
    name: Optional[str] = Field(None, description="New service name")
    build_command: Optional[str] = Field(None, description="New build command")
    start_command: Optional[str] = Field(None, description="New start command")
    env: Optional[EnvType] = Field(None, description="New environment type")
    region: Optional[Region] = Field(None, description="New region")
    auto_deploy: Optional[AutoDeploy] = Field(None, description="Auto-deploy setting")

    model_config = ConfigDict(extra="forbid")


# ──────────────────────────────────────────────────────────────
# DEPLOYMENT MODELS
# ──────────────────────────────────────────────────────────────

class Deployment(BaseModel):
    """Render deployment representation."""
    id: str = Field(..., description="Deployment ID")
    service_id: str = Field(..., description="Service ID this deployment belongs to")
    status: str = Field(..., description="Current deployment status")  # str, not Enum
    url: Optional[str] = Field(None, description="Live deployment URL")
    commit: Optional[str] = Field(None, description="Git commit SHA")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    finished_at: Optional[datetime] = Field(None, description="Completion timestamp")

    model_config = ConfigDict(extra="allow")

    @field_validator("url", mode="before")
    @classmethod
    def validate_url(cls, v: Any) -> Optional[str]:
        """Handle empty strings and None for URL."""
        if v is None or v == "":
            return None
        return str(v)


class CreateDeploymentRequest(BaseModel):
    """
    Request payload for creating a deployment.
    Matches Render's Trigger Deploy endpoint.
    The service_id is passed in the URL path, not the body.
    """
    commit_id: Optional[str] = Field(None, description="Git commit SHA to deploy")
    clear_cache: bool = Field(default=False, description="Clear build cache before deploying")

    model_config = ConfigDict(extra="forbid")


class DeploymentLogs(BaseModel):
    """Deployment logs from Render."""
    id: str = Field(..., description="Log entry ID")
    text: str = Field(..., description="Log text")
    timestamp: datetime = Field(..., description="Log timestamp")
    level: str = Field(default="info", description="Log level")

    model_config = ConfigDict(extra="allow")


# ──────────────────────────────────────────────────────────────
# UPLOAD MODELS
# ──────────────────────────────────────────────────────────────

class UploadFile(BaseModel):
    """File to upload to Render for deployment."""
    path: str = Field(..., description="File path in the project")
    content: str = Field(..., description="Base64 encoded file content")
    sha: Optional[str] = Field(None, description="SHA1 hash of the file")

    model_config = ConfigDict(extra="forbid")


class UploadManifest(BaseModel):
    """Manifest of files to upload to Render."""
    files: List[UploadFile] = Field(..., description="List of files to upload")

    model_config = ConfigDict(extra="forbid")


# ──────────────────────────────────────────────────────────────
# RESPONSE WRAPPERS
# ──────────────────────────────────────────────────────────────

class PaginatedResponse(BaseModel):
    """Paginated response from Render API."""
    items: List[Dict[str, Any]] = Field(..., description="List of items")
    total: Optional[int] = Field(None, description="Total number of items")
    next: Optional[str] = Field(None, description="Cursor for next page")

    model_config = ConfigDict(extra="allow")


class ErrorResponse(BaseModel):
    """Error response from Render API."""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error details")

    model_config = ConfigDict(extra="allow")


# ──────────────────────────────────────────────────────────────
# HELPER FUNCTIONS
# ──────────────────────────────────────────────────────────────

def map_framework_to_render_env(framework: Optional[str]) -> Optional[EnvType]:
    """
    Map Opun8 framework detection to Render's EnvType.

    Args:
        framework: The detected framework name

    Returns:
        Render EnvType, or None if not recognized
    """
    if not framework:
        return None

    mapping = {
        "react": EnvType.STATIC,
        "next": EnvType.NODE,
        "nextjs": EnvType.NODE,
        "vue": EnvType.STATIC,
        "angular": EnvType.STATIC,
        "svelte": EnvType.STATIC,
        "sveltekit": EnvType.NODE,
        "node": EnvType.NODE,
        "nodejs": EnvType.NODE,
        "express": EnvType.NODE,
        "python": EnvType.PYTHON,
        "django": EnvType.PYTHON,
        "flask": EnvType.PYTHON,
        "fastapi": EnvType.PYTHON,
        "static": EnvType.STATIC,
        "html": EnvType.STATIC,
        "vite": EnvType.STATIC,
        "astro": EnvType.STATIC,
        "ruby": EnvType.RUBY,
        "rails": EnvType.RUBY,
        "go": EnvType.GO,
        "gin": EnvType.GO,
        "elixir": EnvType.ELIXIR,
        "phoenix": EnvType.ELIXIR,
        "rust": EnvType.RUST,
    }

    result = mapping.get(framework.lower())
    if result is None:
        # Return None instead of silently guessing Node.js
        return None

    return result


def get_default_build_command(env_type: EnvType, framework: Optional[str] = None) -> Optional[str]:
    """
    Get the default build command for a given Render environment.

    Args:
        env_type: Render environment type
        framework: Optional framework name for more specific defaults

    Returns:
        Default build command, or None if not applicable
    """
    commands = {
        EnvType.NODE: "npm install && npm run build",
        EnvType.PYTHON: "pip install -r requirements.txt",
        EnvType.STATIC: "",
        EnvType.RUBY: "bundle install",
        EnvType.GO: "",
        EnvType.RUST: "cargo build --release",
        EnvType.ELIXIR: "mix deps.get && mix compile",
        EnvType.PHP: "composer install",
        EnvType.JAVA: "./gradlew build",
        EnvType.DOCKER: "",
    }

    # Framework-specific overrides
    if framework:
        framework_lower = framework.lower()
        if framework_lower in ("flask", "fastapi"):
            return "pip install -r requirements.txt"

    return commands.get(env_type)


def get_default_start_command(env_type: EnvType, framework: Optional[str] = None) -> Optional[str]:
    """
    Get the default start command for a given Render environment.

    Args:
        env_type: Render environment type
        framework: Optional framework name for more specific defaults

    Returns:
        Default start command, or None if not applicable
    """
    commands = {
        EnvType.NODE: "npm start",
        EnvType.PYTHON: "gunicorn app:app",
        EnvType.STATIC: "",
        EnvType.RUBY: "rails server",
        EnvType.GO: "./main",
        EnvType.RUST: "./target/release/app",
        EnvType.ELIXIR: "mix phx.server",
        EnvType.PHP: "php artisan serve",
        EnvType.JAVA: "java -jar build/libs/*.jar",
        EnvType.DOCKER: "",
    }

    # Framework-specific overrides
    if framework:
        framework_lower = framework.lower()
        if framework_lower == "flask":
            return "gunicorn app:app"
        elif framework_lower == "fastapi":
            return "uvicorn main:app --host 0.0.0.0 --port $PORT"
        elif framework_lower in ("next", "nextjs"):
            return "npm start"

    return commands.get(env_type)