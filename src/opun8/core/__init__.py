"""
Core module for OPUN8.

Provides project detection, environment checking, and other core functionality.
"""

from opun8.core.detector import detect_project, ProjectInfo, get_build_commands, get_deploy_config
from opun8.core.environment import EnvironmentChecker

__all__ = [
    "detect_project",
    "ProjectInfo",
    "get_build_commands",
    "get_deploy_config",
    "EnvironmentChecker",
]