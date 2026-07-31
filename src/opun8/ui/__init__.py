"""
UI module for Opun8.

Exports all user interface components from messages.py including:
    - Core messages (success, info, warning, error, goodbye)
    - Screens (welcome, help)
    - Detection UI
    - Deploy UI (platform start, platform menu)
    - Auth UI (GitHub, Vercel, Netlify, Render)
    - History UI
    - Doctor UI
    - Safe prompts (_safe_prompt, _safe_prompt_free, _safe_confirm)

Version: 0.2.2
"""

from opun8.ui.messages import *

# All exports are handled by messages.py's __all__
# This file simply re-exports everything for convenience