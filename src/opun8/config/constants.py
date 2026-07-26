"""
OPUN8 Configuration Constants
=============================

This module contains all immutable configuration values used across the OPUN8
application. It serves as the single source of truth for:

- Clone limits and subscription tiers
- Badge/achievement levels
- File type mappings
- API base URL (not full endpoints)
- OTP settings
- Email templates
- System-wide constants

Usage:
    from opun8.config.constants import CLONE_LIMITS, get_badge_by_clones

    free_limit = CLONE_LIMITS["free"]["limit"]
    badge = get_badge_by_clones(5)

Author: OPUN8 Team
Version: 0.1.4
"""

# =============================================================================
# STANDARD LIBRARY IMPORTS
# =============================================================================
from typing import Dict, List, Tuple, Final, Optional
from enum import Enum

# =============================================================================
# ENUMS FOR TYPE SAFETY
# =============================================================================

class SubscriptionTier(str, Enum):
    """
    Subscription tiers available to users.

    Attributes:
        FREE: Basic tier with limited features
        STARTER: Mid-tier with React/Vue support
        PRO: Full tier with backend support
    """
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"


class PlatformType(str, Enum):
    """
    Supported platforms for website cloning.

    Attributes:
        HTML: Static HTML/CSS/JS websites
        REACT: React.js applications
        VUE: Vue.js applications
        BACKEND: Backend API services
        UNKNOWN: Unrecognized platform type
    """
    HTML = "html"
    REACT = "react"
    VUE = "vue"
    BACKEND = "backend"
    UNKNOWN = "unknown"


class CloneStatus(str, Enum):
    """
    Status states for a cloning operation.

    Attributes:
        PENDING: Clone request received, not yet started
        IN_PROGRESS: Clone is actively downloading/organizing
        COMPLETED: Clone finished successfully
        FAILED: Clone encountered an error
        CANCELLED: User cancelled the operation
    """
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# =============================================================================
# SUBSCRIPTION & CLONE LIMITS
# =============================================================================

CLONE_LIMITS: Final[Dict[str, Dict]] = {
    SubscriptionTier.FREE.value: {
        "limit": 3,
        "platforms": [PlatformType.HTML.value],
        "description": "3 HTML clones per month. Perfect for trying OPUN8!",
        "price_monthly": 0.00,
        "features": [
            "Clone static HTML websites",
            "Auto-organize files into folders",
            "Basic code cleanup",
            "Clone history tracking",
        ]
    },
    SubscriptionTier.STARTER.value: {
        "limit": 20,
        "platforms": [
            PlatformType.HTML.value,
            PlatformType.REACT.value,
            PlatformType.VUE.value,
        ],
        "description": "20 clones per month. Clone React and Vue apps!",
        "price_monthly": 5.00,
        "features": [
            "Clone React.js applications",
            "Clone Vue.js applications",
            "Advanced code cleanup",
            "Auto-documentation generation",
            "Priority support",
        ]
    },
    SubscriptionTier.PRO.value: {
        "limit": 100,
        "platforms": [
            PlatformType.HTML.value,
            PlatformType.REACT.value,
            PlatformType.VUE.value,
            PlatformType.BACKEND.value,
        ],
        "description": "100 clones per month. Clone everything including backends!",
        "price_monthly": 15.00,
        "features": [
            "Clone backend APIs (Node.js, Python, etc.)",
            "Full project structure preservation",
            "Custom domain support",
            "Premium support",
            "Team collaboration features",
        ]
    }
}


# =============================================================================
# BADGE / ACHIEVEMENT SYSTEM
# =============================================================================

BADGE_LEVELS: Final[List[Dict]] = [
    {
        "level": 1,
        "emoji": "🌱",
        "name": "First Clone",
        "description": "Your very first clone!",
        "clones": 1,
    },
    {
        "level": 2,
        "emoji": "🔍",
        "name": "Curious Explorer",
        "description": "Starting to explore the web!",
        "clones": 3,
    },
    {
        "level": 3,
        "emoji": "🧩",
        "name": "Pattern Finder",
        "description": "You're seeing the patterns in code.",
        "clones": 5,
    },
    {
        "level": 4,
        "emoji": "📚",
        "name": "Archivist",
        "description": "Building your collection of websites.",
        "clones": 10,
    },
    {
        "level": 5,
        "emoji": "🚀",
        "name": "Speed Runner",
        "description": "Cloning websites at lightning speed!",
        "clones": 25,
    },
    {
        "level": 6,
        "emoji": "🏆",
        "name": "Master Archiver",
        "description": "You've cloned more than most!",
        "clones": 50,
    },
    {
        "level": 7,
        "emoji": "👑",
        "name": "Clone King",
        "description": "The ultimate cloner! You're legendary.",
        "clones": 100,
    },
]

MAX_BADGE_LEVEL: Final[int] = len(BADGE_LEVELS)


# =============================================================================
# FILE TYPE MAPPINGS
# =============================================================================

FILE_TYPE_MAPPING: Final[Dict[str, List[str]]] = {
    "html": ["html", "htm", "xhtml", "shtml"],
    "css": ["css", "scss", "sass", "less", "styl"],
    "js": ["js", "mjs", "ts", "jsx", "tsx"],
    "images": ["png", "jpg", "jpeg", "gif", "svg", "webp", "ico", "bmp", "tiff"],
    "fonts": ["woff", "woff2", "ttf", "eot", "otf", "svgz"],
    "assets": ["json", "xml", "yaml", "yml", "toml", "ini", "cfg"],
    "media": ["mp4", "webm", "ogg", "mp3", "wav", "flac", "aac"],
    "documents": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "txt"],
    "backend": ["py", "rb", "go", "rs", "java", "php", "cs", "cpp", "c"],
}

#: Reverse mapping for quick extension to folder lookup
EXTENSION_TO_FOLDER: Final[Dict[str, str]] = {
    ext: folder
    for folder, extensions in FILE_TYPE_MAPPING.items()
    for ext in extensions
}


# =============================================================================
# API & BACKEND CONFIGURATION
# =============================================================================

#: Base URL for the OPUN8 backend API (Render free domain)
#: Used by backend_urls.py to build full endpoints
API_BASE_URL: Final[str] = "https://api-opun8.onrender.com"

#: API version prefix
API_VERSION: Final[str] = "v1"


# =============================================================================
# OTP (ONE-TIME PASSWORD) CONFIGURATION
# =============================================================================

OTP_EXPIRY_SECONDS: Final[int] = 300          # 5 minutes
OTP_LENGTH: Final[int] = 6                    # 6-digit code
OTP_MAX_ATTEMPTS: Final[int] = 5              # Max verification attempts
OTP_RESEND_COOLDOWN_SECONDS: Final[int] = 60  # 1 minute


# =============================================================================
# EMAIL CONFIGURATION (BREVO)
# =============================================================================

BREVO_TEMPLATES: Final[Dict[str, int]] = {
    "welcome": 1,
    "verify_otp": 2,
    "password_reset": 3,
    "promotional": 4,
    "clone_complete": 5,
    "subscription_update": 6,
    "limit_reminder": 7,
    "upgrade_offer": 8,
}

BREVO_SENDER: Final[Dict[str, str]] = {
    "name": "OPUN8 Team",
    "email": "hello@opun8.com",
}

EMAIL_SUBJECTS: Final[Dict[str, str]] = {
    "welcome": "Welcome to OPUN8! 🚀",
    "verify_otp": "Your OPUN8 Verification Code: {code}",
    "password_reset": "Reset Your OPUN8 Password",
    "promotional": "New Features Available in OPUN8!",
    "clone_complete": "Your Clone is Ready! ✅",
    "subscription_update": "Your OPUN8 Plan Has Been Updated",
    "limit_reminder": "You're Almost Out of Clones! ⚠️",
    "upgrade_offer": "Unlock More Clones with OPUN8 Pro! 🔓",
}


# =============================================================================
# CLONE OPERATION SETTINGS
# =============================================================================

MAX_FILE_SIZE_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB
MAX_FILES_PER_CLONE: Final[int] = 1000
MAX_RECURSION_DEPTH: Final[int] = 3

BINARY_FILE_EXTENSIONS: Final[List[str]] = [
    "png", "jpg", "jpeg", "gif", "bmp", "ico",
    "woff", "woff2", "ttf", "eot", "otf",
    "pdf", "doc", "docx", "xls", "xlsx",
    "mp4", "webm", "mp3", "wav", "flac",
    "zip", "rar", "tar", "gz", "7z",
    "exe", "msi", "dmg", "appimage",
]

CLEANABLE_FILE_EXTENSIONS: Final[List[str]] = [
    "html", "htm", "xhtml",
    "css", "scss", "sass", "less",
    "js", "jsx", "ts", "tsx", "mjs",
    "py", "rb", "go", "rs",
    "json", "xml", "yaml", "yml",
]


# =============================================================================
# UI & DISPLAY CONFIGURATION
# =============================================================================

UI_COLORS: Final[Dict[str, str]] = {
    "success": "green",
    "error": "red",
    "warning": "yellow",
    "info": "blue",
    "highlight": "cyan",
    "muted": "dim",
    "header": "bold magenta",
    "badge": "bold yellow",
    "emoji": "bold",
    "url": "underline blue",
    "code": "bold white on black",
}

UI_EMOJIS: Final[Dict[str, str]] = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "question": "❓",
    "rocket": "🚀",
    "clone": "📦",
    "folder": "📁",
    "file": "📄",
    "check": "✔️",
    "cross": "✖️",
    "star": "⭐",
    "heart": "❤️",
    "clock": "⏱️",
    "lock": "🔒",
    "unlock": "🔓",
    "user": "👤",
    "users": "👥",
    "email": "📧",
    "gear": "⚙️",
}


# =============================================================================
# PATH CONFIGURATION
# =============================================================================

OPUN8_CONFIG_DIR: Final[str] = ".opun8"
CLONES_DIR: Final[str] = "clones"
DEFAULT_CLONE_OUTPUT_DIR: Final[str] = "./cloned_sites"
TOKEN_FILENAME: Final[str] = "config.json"


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

LOG_LEVEL: Final[str] = "INFO"
LOG_FILENAME: Final[str] = "debug.log"
MAX_LOG_SIZE_BYTES: Final[int] = 5 * 1024 * 1024  # 5 MB
LOG_BACKUP_COUNT: Final[int] = 3


# =============================================================================
# HEADER & USER AGENT
# =============================================================================

USER_AGENT: Final[str] = (
    "Mozilla/5.0 (compatible; OPUN8/1.0; +https://opun8.com)"
)

HTTP_TIMEOUT_SECONDS: Final[int] = 30
CONNECT_TIMEOUT_SECONDS: Final[int] = 10


# =============================================================================
# VERSION & METADATA
# =============================================================================

OPUN8_VERSION: Final[str] = "0.1.4"
SUPPORTED_PYTHON_VERSIONS: Final[Tuple[str, ...]] = (
    "3.8", "3.9", "3.10", "3.11", "3.12"
)
MINIMUM_PYTHON_VERSION: Final[str] = "3.8"


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_subscription_limits(tier: str) -> Dict:
    """
    Get the clone limits for a given subscription tier.

    Args:
        tier: The subscription tier (free, starter, pro)

    Returns:
        Dictionary containing limit and platform information

    Raises:
        ValueError: If the tier is invalid

    Example:
        >>> get_subscription_limits("free")
        {"limit": 3, "platforms": ["html"], ...}
    """
    if tier not in CLONE_LIMITS:
        raise ValueError(
            f"Invalid subscription tier: '{tier}'. "
            f"Valid options: {', '.join(CLONE_LIMITS.keys())}"
        )
    return CLONE_LIMITS[tier]


def get_badge_by_clones(clones: int) -> Optional[Dict]:
    """
    Get the badge information based on number of clones.

    Args:
        clones: Total number of clones performed

    Returns:
        Dictionary containing badge information, or None if no badge earned yet

    Example:
        >>> get_badge_by_clones(0)
        None
        >>> get_badge_by_clones(1)
        {"level": 1, "emoji": "🌱", "name": "First Clone", "clones": 1}
        >>> get_badge_by_clones(3)
        {"level": 2, "emoji": "🔍", "name": "Curious Explorer", "clones": 3}
    """
    for badge in BADGE_LEVELS:
        if clones >= badge["clones"]:
            return badge
    return None  # No badge earned yet


def get_folder_for_extension(extension: str) -> str:
    """
    Get the destination folder for a file extension.

    Args:
        extension: File extension (without the dot)

    Returns:
        Folder name, or "other" if no mapping exists

    Example:
        >>> get_folder_for_extension("css")
        "css"
        >>> get_folder_for_extension("xyz")
        "other"
    """
    extension = extension.lower().replace(".", "")
    return EXTENSION_TO_FOLDER.get(extension, "other")


# =============================================================================
# MODULE EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "SubscriptionTier",
    "PlatformType",
    "CloneStatus",
    
    # Subscription
    "CLONE_LIMITS",
    
    # Badges
    "BADGE_LEVELS",
    "MAX_BADGE_LEVEL",
    
    # File types
    "FILE_TYPE_MAPPING",
    "EXTENSION_TO_FOLDER",
    
    # API
    "API_BASE_URL",
    "API_VERSION",
    
    # OTP
    "OTP_EXPIRY_SECONDS",
    "OTP_LENGTH",
    "OTP_MAX_ATTEMPTS",
    "OTP_RESEND_COOLDOWN_SECONDS",
    
    # Email
    "BREVO_TEMPLATES",
    "BREVO_SENDER",
    "EMAIL_SUBJECTS",
    
    # Clone settings
    "MAX_FILE_SIZE_BYTES",
    "MAX_FILES_PER_CLONE",
    "MAX_RECURSION_DEPTH",
    "BINARY_FILE_EXTENSIONS",
    "CLEANABLE_FILE_EXTENSIONS",
    
    # UI
    "UI_COLORS",
    "UI_EMOJIS",
    
    # Paths
    "OPUN8_CONFIG_DIR",
    "CLONES_DIR",
    "DEFAULT_CLONE_OUTPUT_DIR",
    "TOKEN_FILENAME",
    
    # Logging
    "LOG_LEVEL",
    "LOG_FILENAME",
    "MAX_LOG_SIZE_BYTES",
    "LOG_BACKUP_COUNT",
    
    # HTTP
    "USER_AGENT",
    "HTTP_TIMEOUT_SECONDS",
    "CONNECT_TIMEOUT_SECONDS",
    
    # Version
    "OPUN8_VERSION",
    "SUPPORTED_PYTHON_VERSIONS",
    "MINIMUM_PYTHON_VERSION",
    
    # Helpers
    "get_subscription_limits",
    "get_badge_by_clones",
    "get_folder_for_extension",
]


# =============================================================================
# VALIDATION (Runs on import)
# =============================================================================

def _validate_constants() -> None:
    """
    Perform validation checks on constants at import time.

    Ensures:
    - All subscription tiers have required keys
    - Badge levels are in ascending order
    - File type mappings are valid
    """
    # Validate subscription tiers
    required_keys = {"limit", "platforms", "description", "price_monthly"}
    for tier, config in CLONE_LIMITS.items():
        missing = required_keys - set(config.keys())
        if missing:
            raise ValueError(
                f"Subscription tier '{tier}' missing required keys: {missing}"
            )

    # Validate badge levels are in ascending order
    clone_counts = [badge["clones"] for badge in BADGE_LEVELS]
    if clone_counts != sorted(clone_counts):
        raise ValueError("Badge levels must be in ascending order by clone count")

    # Validate file type mappings
    for folder, extensions in FILE_TYPE_MAPPING.items():
        if not extensions:
            raise ValueError(f"File type mapping '{folder}' has no extensions")


# Run validation
_validate_constants()

# Clean up namespace
del _validate_constants