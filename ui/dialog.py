# -*- coding: utf-8 -*-
"""
ui/dialog.py — Anki Reflect Report Dialog
===========================================
Opens a resizable PyQt dialog containing Anki's native WebView
(``AnkiWebView``). The report HTML is injected via ``stdHtml()``,
which automatically provides Anki's CSS environment and JS bridge.

The dialog:
  - Shows a "Generating…" spinner while the report is built on the
    main thread (fast enough for typical collections).
  - Displays the rendered HTML report.
  - Provides toolbar buttons: Export HTML, Copy to Clipboard, Close.
  - Is non-modal so the user can interact with Anki while reading.
"""

from __future__ import annotations

import traceback

from aqt import mw
from aqt.qt import (
    QAction,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QShortcut,
    QSizePolicy,
    QToolBar,
    QVBoxLayout,
    Qt,
    QKeySequence,
)
from aqt.webview import AnkiWebView

from ..report.builder import build_report


# ---------------------------------------------------------------------------
# Public entry point called by the menu action
# ---------------------------------------------------------------------------

def show_reflection_dialog() -> None:
    """
    Entry point: reads config, builds the report, and shows the dialog.
    Handles errors gracefully — never crashes Anki.
    """
    if mw.col is None:
        from aqt.utils import showWarning
        showWarning(
            "No collection is open. Please open a profile first.",
            title="Anki Reflect",
        )
        return

    try:
        config = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
    except Exception:
        config = {}

    try:
        html = build_report(mw.col.db, config)
    except Exception:
        tb = traceback.format_exc()
        from aqt.utils import showCritical
        showCritical(
            f"Anki Reflect encountered an error while building the report:\n\n{tb}",
            title="Anki Reflect — Error",
        )
        return

    dialog = ReflectionDialog(html=html, parent=mw)
    dialog.show()


# ---------------------------------------------------------------------------
# Dialog window
# ---------------------------------------------------------------------------

class ReflectionDialog(QDialog):
    """Non-modal dialog displaying the generated HTML report in a WebView."""

    def __init__(self, html: str, parent=None) -> None:
        super().__init__(parent)
        self._html = html
        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setWindowTitle("Anki Reflect — Session Report")
        self.setMinimumSize(860, 640)
        self.resize(1000, 740)
        # Allow resize; not always-on-top
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.WindowMinMaxButtonsHint
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Toolbar ────────────────────────────────────────────────────
        toolbar = self._build_toolbar()
        root_layout.addWidget(toolbar)

        # ── WebView ────────────────────────────────────────────────────
        self._web = AnkiWebView(parent=self)
        self._web.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        # stdHtml wraps content in Anki's base HTML shell (fonts, nightmode vars, etc.)
        self._web.stdHtml(self._html)
        root_layout.addWidget(self._web)

        # Escape closes the dialog
        QShortcut(QKeySequence("Escape"), self, activated=self.close)

    def _build_toolbar(self) -> QToolBar:
        toolbar = QToolBar(self)
        toolbar.setMovable(False)
        toolbar.setStyleSheet(
            """
            QToolBar {
                background: #1a1b2e;
                border-bottom: 1px solid rgba(124,106,247,0.2);
                spacing: 6px;
                padding: 4px 8px;
            }
            QPushButton {
                background: rgba(124,106,247,0.15);
                color: #e8e8ff;
                border: 1px solid rgba(124,106,247,0.35);
                border-radius: 6px;
                padding: 4px 14px;
                font-size: 12px;
                font-family: Inter, sans-serif;
            }
            QPushButton:hover {
                background: rgba(124,106,247,0.3);
                border-color: rgba(124,106,247,0.7);
            }
            QLabel {
                color: #5a5a7a;
                font-size: 11px;
                padding: 0 8px;
            }
            """
        )

        # Label
        label = QLabel("📊 Anki Reflect")
        label.setStyleSheet("color: #7C6AF7; font-weight: 600; font-size: 13px;")
        toolbar.addWidget(label)

        # Spacer
        spacer = QLabel("")
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        # Export HTML button
        btn_export = QPushButton("⬇  Export HTML")
        btn_export.setToolTip("Save the report as an HTML file")
        btn_export.clicked.connect(self._export_html)
        toolbar.addWidget(btn_export)

        # Refresh button
        btn_refresh = QPushButton("🔄  Refresh")
        btn_refresh.setToolTip("Regenerate the report with the latest data")
        btn_refresh.clicked.connect(self._refresh)
        toolbar.addWidget(btn_refresh)

        # Close button
        btn_close = QPushButton("✕  Close")
        btn_close.clicked.connect(self.close)
        toolbar.addWidget(btn_close)

        return toolbar

    # ── Actions ────────────────────────────────────────────────────────

    def _export_html(self) -> None:
        """Save the rendered HTML to a user-chosen file."""
        from aqt.qt import QFileDialog
        import os, datetime

        default_name = f"anki_reflect_{datetime.date.today().isoformat()}.html"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Report",
            os.path.join(os.path.expanduser("~"), default_name),
            "HTML Files (*.html);;All Files (*)",
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(self._html)
                from aqt.utils import tooltip
                tooltip(f"Report saved to {path}", period=4000)
            except OSError as e:
                from aqt.utils import showWarning
                showWarning(f"Could not save file:\n{e}", title="Anki Reflect")

    def _refresh(self) -> None:
        """Rebuild the report with fresh data and reload the WebView."""
        if mw.col is None:
            return
        try:
            config = mw.addonManager.getConfig(__name__.split(".")[0]) or {}
        except Exception:
            config = {}

        self._html = build_report(mw.col.db, config)
        self._web.stdHtml(self._html)
