# -*- coding: utf-8 -*-
"""
Anki Reflect — Entry Point
==========================
Registers the "Generate Session Reflection" menu item under Tools after the
user's Anki profile has finished loading. This deferred approach ensures that
mw.col (the collection) is available when the menu action is triggered.

GitHub: https://github.com/MRHemmati/anki-reflect
License: MIT
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "Mohammad Hemmati"
__license__ = "MIT"

from aqt import gui_hooks
from .ui.menu import setup_menu


def _on_profile_loaded() -> None:
    """Called once Anki has loaded the user profile and collection is ready."""
    setup_menu()


# Hook fires every time a profile is opened (including profile switches).
gui_hooks.profile_did_open.append(_on_profile_loaded)
