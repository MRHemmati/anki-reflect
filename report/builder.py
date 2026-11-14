# -*- coding: utf-8 -*-
"""
report/builder.py — Report Orchestration Layer
================================================
Wires together all modules into a single ``build_report()`` function that
returns a complete HTML string ready to be injected into Anki's WebView.

Pipeline:
    1. Read config from Anki's add-on config system
    2. Run all SQL queries  →  raw metrics dict
    3. Parse FSRS blobs    →  enriched metrics dict
    4. Generate graphs     →  dict of inline SVG strings
    5. Generate insights   →  dict of narrative strings
    6. Render Jinja2 HTML  →  final HTML string

All steps are wrapped in try/except so a failure in (e.g.) graph generation
does not break the entire report — the section is simply omitted.
"""

from __future__ import annotations

from html import escape
import os
import traceback
from typing import Optional

# Jinja2 is bundled with Anki
try:
    from jinja2 import Environment, FileSystemLoader, select_autoescape
    _HAS_JINJA2 = True
except ImportError:
    _HAS_JINJA2 = False

from .._version_info import __version__          # re-export from __init__
from ..data.queries import get_all_metrics
from ..data.fsrs_metrics import enrich_metrics_with_fsrs
from .graphs import render_all_graphs
from .insights import InsightEngine


# ---------------------------------------------------------------------------
# Jinja2 environment (lazy initialised once)
# ---------------------------------------------------------------------------

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")
_jinja_env: Optional["Environment"] = None


def _get_jinja_env() -> "Environment":
    global _jinja_env
    if _jinja_env is None and _HAS_JINJA2:
        _jinja_env = Environment(
            loader=FileSystemLoader(_TEMPLATES_DIR),
            autoescape=select_autoescape(["html", "htm", "xml", "j2"]),
        )
        # Custom filter: format large integers with thousands separators
        _jinja_env.filters["format_number"] = lambda v: f"{int(v):,}"
    return _jinja_env


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_report(db: object, config: dict) -> str:
    """
    Build and return the complete HTML report string.

    Args:
        db:     Anki DB connection object (``mw.col.db``).
        config: The add-on config dict (from ``mw.addonManager.getConfig``).

    Returns:
        A complete HTML string, or a minimal error page if something goes
        catastrophically wrong.
    """
    try:
        return _build_report_inner(db, config)
    except Exception:
        tb = traceback.format_exc()
        return _error_page(tb)


def _build_report_inner(db: object, config: dict) -> str:
    """Internal build — may raise; caller handles exceptions."""

    # ── Step 1: SQL queries ──────────────────────────────────────────────
    metrics = get_all_metrics(db, config)

    # ── Step 2: FSRS enrichment ──────────────────────────────────────────
    raw_fsrs = metrics.pop("_fsrs_raw", [])
    metrics = enrich_metrics_with_fsrs(metrics, raw_fsrs)

    # ── Step 3: Graphs ───────────────────────────────────────────────────
    graphs: dict = {}
    try:
        graphs = render_all_graphs(metrics, config)
    except Exception:
        pass  # graphs section will show "not available" in template

    # ── Step 4: Insights ─────────────────────────────────────────────────
    engine = InsightEngine()
    insights = engine.generate(metrics, config)

    # ── Step 5: Render Jinja2 template ───────────────────────────────────
    env = _get_jinja_env()
    if not env:
        return _fallback_html(metrics, insights)

    template = env.get_template("report.html.j2")
    html = template.render(
        metrics=metrics,
        insights=insights,
        graphs=graphs,
        config=config,
        version=_safe_version(),
    )
    return html


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_version() -> str:
    try:
        return __version__
    except Exception:
        return "0.1.0"


def _error_page(traceback_str: str) -> str:
    """Return a minimal styled error page with the traceback."""
    escaped = (
        traceback_str
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Anki Reflect — Error</title>
  <style>
    body {{
      font-family: monospace;
      background: #0f1021;
      color: #f77b6b;
      padding: 2rem;
    }}
    h1 {{ color: #7C6AF7; margin-bottom: 1rem; }}
    pre {{
      background: #1a1b2e;
      padding: 1rem;
      border-radius: 8px;
      white-space: pre-wrap;
      color: #e8e8ff;
      font-size: 0.82rem;
    }}
  </style>
</head>
<body>
  <h1>⚠️  Anki Reflect encountered an error</h1>
  <p>Please report this on the GitHub issues page. Traceback below:</p>
  <pre>{escaped}</pre>
</body>
</html>"""


def _fallback_html(metrics: dict, insights: dict) -> str:
    """Minimal plain-text fallback when Jinja2 is unavailable."""
    report_date = escape(str(insights.get("report_date", "")))
    lines = [
        "<html><head><meta charset='UTF-8'></head>",
        "<body style='font-family:monospace;background:#0f1021;color:#e8e8ff;padding:2rem'>",
        f"<h2>📊 Anki Reflect — {report_date}</h2>",
        f"<p>Cards reviewed: <strong>{int(metrics.get('total_reviews',0))}</strong></p>",
        f"<p>Time: <strong>{float(metrics.get('total_time_min',0)):.2f} min</strong></p>",
        f"<p>Avg speed: <strong>{float(metrics.get('avg_time_sec',0)):.2f}s/card</strong></p>",
        f"<p>Mature retention: <strong>{float(metrics.get('mature_retention',0)):.2f}%</strong></p>",
        f"<p>Lapse rate: <strong>{float(metrics.get('lapse_rate',0)):.2f}%</strong></p>",
        "<p><em>Jinja2 not available — install it for the full report.</em></p>",
        "</body></html>",
    ]
    return "\n".join(lines)
