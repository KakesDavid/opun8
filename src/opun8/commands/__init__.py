"""
Opun8 Commands - Available CLI commands.
"""

from opun8.commands.doctor import doctor
from opun8.commands.detect import detect
from opun8.commands.deploy import deploy
from opun8.commands.repo import deploy_repository

__all__ = ["doctor", "detect", "deploy"]