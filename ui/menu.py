# -*- coding: utf-8 -*-
"""
ui/menu.py — Anki Menu Integration
=====================================
Injects a "Generate Session Reflection" item into Anki's **Tools** menu.
Called once from ``__init__.py`` after ``profileLoaded`` fires.

The action is safe to call repeatedly (e.g. profile switches) because
we check for an existing action before adding a duplicate.
"""

from __future__ import annotations

from aqt import mw
from aqt.qt import QAction

from .dialog import show_reflection_dialog

# Module-level reference so we can remove/replace the action cleanly
_menu_action: QAction | None = None


def setup_menu() -> None:
    """Add 'Generate Session Reflection' to Tools menu (idempotent)."""
    global _menu_action

    # Guard: don't add the action twice on profile switches
    if _menu_action is not None:
        return

    _menu_action = QAction("Generate Session Reflection…", mw)
    _menu_action.setStatusTip(
        "Anki Reflect: Build a narrative stats report for your current study session"
    )
    _menu_action.triggered.connect(show_reflection_dialog)
    mw.form.menuTools.addAction(_menu_action)
