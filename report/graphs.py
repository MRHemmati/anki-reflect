# -*- coding: utf-8 -*-
"""
report/graphs.py — Pure Python SVG Graph Generator
===================================================
All graphs are rendered as inline SVG XML strings. This eliminates the dependency
on matplotlib (which is not bundled with Anki), making the add-on offline-first,
cross-platform, and light/dark theme-compatible without compiling binary extensions.
"""

from __future__ import annotations

import datetime
from html import escape
import re
from typing import Optional

_SAFE_COLOR_RE = re.compile(r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z]{3,20})$")


def _safe_color(value: object, default: str) -> str:
    """Validate a CSS color string for safe interpolation into SVG attributes."""
    if isinstance(value, str) and _SAFE_COLOR_RE.match(value.strip()):
        return value.strip()
    return default


# ---------------------------------------------------------------------------
# Graph 1 — Mature Review Activity Plot
# ---------------------------------------------------------------------------

def render_growth_graph(growth_history: list[dict], config: dict) -> Optional[str]:
    """
    Render the mature review activity plot as an inline SVG string.

    Args:
        growth_history: list of {"date": datetime.date, "count": int}
                        sorted ascending by date.
        config: the add-on config dict.

    Returns:
        Inline SVG string, or None if the input data is empty.
    """
    if not growth_history:
        return None

    # Sort history by date to ensure correctness
    history = sorted(growth_history, key=lambda x: x["date"])
    dates = [entry["date"] for entry in history]
    daily_counts = [entry["count"] for entry in history]

    # Build cumulative series
    cumulative = []
    running = 0
    for count in daily_counts:
        running += count
        cumulative.append(running)

    # 7-day rolling average (smooth trend line)
    window = 7
    rolling = []
    for i in range(len(cumulative)):
        start = max(0, i - window + 1)
        rolling.append(sum(cumulative[start:i + 1]) / (i - start + 1))

    # Theme colors
    theme = config.get("graph_theme", "dark")
    accent = _safe_color(config.get("graph_accent_color"), "#7C6AF7")
    secondary = _safe_color(config.get("graph_secondary_color"), "#F7A76C")

    bg_color = "transparent"
    text_color = "#a0a5cc" if theme == "dark" else "#4a4b63"
    grid_color = "#2a2b4e" if theme == "dark" else "#e8e8e8"

    # Dimensions
    width, height = 900.0, 380.0
    pad_left, pad_right, pad_top, pad_bottom = 70.0, 30.0, 44.0, 60.0
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    # Ranges
    min_date = dates[0]
    max_date = dates[-1]
    time_diff = (max_date - min_date).days

    min_val = min(cumulative)
    max_val = max(cumulative)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = max(10.0, max_val * 0.2 if max_val > 0 else 10.0)
        min_val = max(0.0, min_val - val_range / 2.0)
        max_val = min_val + val_range
    else:
        # Give 10% breathing room top and bottom
        padding = val_range * 0.1
        min_val = max(0.0, min_val - padding)
        max_val = max_val + padding
        val_range = max_val - min_val

    # Mapping helpers
    def get_x(d: datetime.date) -> float:
        if time_diff <= 0:
            return pad_left + plot_w / 2.0
        days = (d - min_date).days
        return pad_left + (days / time_diff) * plot_w

    def get_y(v: float) -> float:
        return (pad_top + plot_h) - ((v - min_val) / val_range) * plot_h

    # Build horizontal gridlines
    gridlines = []
    for i in range(5):
        y_val = min_val + val_range * i / 4.0
        y_pos = get_y(y_val)
        gridlines.append(
            f'<line x1="{pad_left}" y1="{y_pos}" x2="{width - pad_right}" y2="{y_pos}" '
            f'stroke="{grid_color}" stroke-width="1" stroke-dasharray="4,4" opacity="0.6" />'
        )
        gridlines.append(
            f'<text x="{pad_left - 10}" y="{y_pos + 4}" fill="{text_color}" '
            f'font-family="sans-serif" font-size="11" text-anchor="end">{int(round(y_val)):,}</text>'
        )

    # Build date ticks
    num_ticks = min(5, len(dates))
    tick_indices = [int(i * (len(dates) - 1) / (num_ticks - 1)) for i in range(num_ticks)] if num_ticks > 1 else [0]
    x_ticks = []
    for idx in tick_indices:
        d = dates[idx]
        x_pos = get_x(d)
        date_str = d.strftime("%b %d")
        x_ticks.append(
            f'<line x1="{x_pos}" y1="{pad_top}" x2="{x_pos}" y2="{pad_top + plot_h}" '
            f'stroke="{grid_color}" stroke-width="1" stroke-dasharray="4,4" opacity="0.3" />'
        )
        x_ticks.append(
            f'<text x="{x_pos}" y="{pad_top + plot_h + 22}" fill="{text_color}" '
            f'font-family="sans-serif" font-size="11" text-anchor="middle">{date_str}</text>'
        )

    # Build graph paths
    if len(dates) == 1:
        y0 = get_y(cumulative[0])
        path_data = f"M {pad_left},{y0} L {width - pad_right},{y0}"
        area_data = (
            f"M {pad_left},{y0} L {width - pad_right},{y0} "
            f"L {width - pad_right},{pad_top + plot_h} L {pad_left},{pad_top + plot_h} Z"
        )
        rolling_path_data = path_data
    else:
        points = [f"{get_x(d)},{get_y(v)}" for d, v in zip(dates, cumulative)]
        path_data = "M " + " L ".join(points)

        first_x = get_x(dates[0])
        last_x = get_x(dates[-1])
        area_data = f"{path_data} L {last_x},{pad_top + plot_h} L {first_x},{pad_top + plot_h} Z"

        rolling_points = [f"{get_x(d)},{get_y(rv)}" for d, rv in zip(dates, rolling)]
        rolling_path_data = "M " + " L ".join(rolling_points)

    # Legend in header area
    legend = f"""
    <text x="{pad_left}" y="24" fill="{text_color}" font-family="sans-serif" font-size="12" font-weight="bold">Cumulative Mature Reviews</text>
    <line x1="{width - pad_right - 250}" y1="20" x2="{width - pad_right - 228}" y2="20" stroke="{accent}" stroke-width="3" stroke-linecap="round" />
    <text x="{width - pad_right - 222}" y="24" fill="{text_color}" font-family="sans-serif" font-size="11">Cumulative</text>
    <line x1="{width - pad_right - 135}" y1="20" x2="{width - pad_right - 113}" y2="20" stroke="{secondary}" stroke-width="2.2" stroke-dasharray="4,4" stroke-linecap="round" />
    <text x="{width - pad_right - 107}" y="24" fill="{text_color}" font-family="sans-serif" font-size="11">7d Rolling Avg</text>
    """

    # Annotation for latest value (bubble tooltip style)
    latest_x = get_x(dates[-1])
    latest_y = get_y(cumulative[-1])
    val_label = f"{int(cumulative[-1]):,}"
    box_w = max(56.0, len(val_label) * 7.5 + 16.0)
    box_x = min(width - pad_right - box_w, max(pad_left, latest_x - box_w - 5.0))
    box_y = max(4.0, latest_y - 36.0)
    annotation = f"""
    <circle cx="{latest_x}" cy="{latest_y}" r="6" fill="{accent}" stroke="#ffffff" stroke-width="2" />
    <rect x="{box_x}" y="{box_y}" width="{box_w}" height="24" rx="4" fill="{accent}" opacity="0.95" />
    <text x="{box_x + box_w / 2.0}" y="{box_y + 16.0}" fill="#ffffff" font-family="sans-serif" font-size="11" font-weight="bold" text-anchor="middle">{val_label}</text>
    """

    # Assemble final SVG
    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" class="report-graph" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="background:{bg_color};">',
        '<!-- Legend -->',
        legend,
        '<!-- Gridlines -->',
        "\n".join(gridlines),
        '<!-- Date ticks -->',
        "\n".join(x_ticks),
        '<!-- Area fill under line -->',
        f'<path d="{area_data}" fill="{accent}" opacity="0.12" />',
        '<!-- Trend line -->',
        f'<path d="{path_data}" fill="none" stroke="{accent}" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />',
        '<!-- Rolling average line -->',
        f'<path d="{rolling_path_data}" fill="none" stroke="{secondary}" stroke-width="2.2" stroke-dasharray="5,5" stroke-linecap="round" stroke-linejoin="round" />',
        '<!-- Latest point annotation -->',
        annotation,
        '</svg>'
    ]
    return "\n".join(svg_parts)


# ---------------------------------------------------------------------------
# Graph 2 — Daily Review Volume Bar Chart
# ---------------------------------------------------------------------------

def render_volume_graph(growth_history: list[dict], config: dict) -> Optional[str]:
    """
    Render a bar chart of daily review volume as an inline SVG string.

    Args:
        growth_history: list of {"date": datetime.date, "count": int}
        config: the add-on config dict.

    Returns:
        Inline SVG string, or None if the input data is empty.
    """
    if not growth_history:
        return None

    # Sort history by date
    history = sorted(growth_history, key=lambda x: x["date"])
    dates = [entry["date"] for entry in history]
    counts = [entry["count"] for entry in history]

    # Theme colors
    theme = config.get("graph_theme", "dark")
    accent = _safe_color(config.get("graph_accent_color"), "#7C6AF7")
    secondary = _safe_color(config.get("graph_secondary_color"), "#F7A76C")

    bg_color = "transparent"
    text_color = "#a0a5cc" if theme == "dark" else "#4a4b63"
    grid_color = "#2a2b4e" if theme == "dark" else "#e8e8e8"

    # Dimensions
    width, height = 900.0, 300.0
    pad_left, pad_right, pad_top, pad_bottom = 70.0, 30.0, 44.0, 60.0
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    # Ranges
    min_date = dates[0]
    max_date = dates[-1]
    time_diff = (max_date - min_date).days

    max_count = max(counts)
    if max_count == 0:
        max_count = 10

    num_days = max(1, time_diff + 1)
    bar_w = min(42.0, max(2.0, (plot_w / num_days) * 0.72))
    usable_w = max(1.0, plot_w - bar_w)
    x_start = pad_left + bar_w / 2.0

    # Mapping helpers
    def get_x(d: datetime.date) -> float:
        if time_diff <= 0:
            return pad_left + plot_w / 2.0
        days = (d - min_date).days
        return x_start + (days / time_diff) * usable_w

    # Horizontal gridlines
    gridlines = []
    for i in range(4):
        y_val = max_count * i / 3.0
        y_pos = (pad_top + plot_h) - (i / 3.0) * plot_h
        gridlines.append(
            f'<line x1="{pad_left}" y1="{y_pos}" x2="{width - pad_right}" y2="{y_pos}" '
            f'stroke="{grid_color}" stroke-width="1" stroke-dasharray="4,4" opacity="0.6" />'
        )
        gridlines.append(
            f'<text x="{pad_left - 10}" y="{y_pos + 4}" fill="{text_color}" '
            f'font-family="sans-serif" font-size="11" text-anchor="end">{int(round(y_val)):,}</text>'
        )

    # Date ticks (vertical grids)
    num_ticks = min(5, len(dates))
    tick_indices = [int(i * (len(dates) - 1) / (num_ticks - 1)) for i in range(num_ticks)] if num_ticks > 1 else [0]
    x_ticks = []
    for idx in tick_indices:
        d = dates[idx]
        x_pos = get_x(d)
        date_str = d.strftime("%b %d")
        x_ticks.append(
            f'<text x="{x_pos}" y="{pad_top + plot_h + 22}" fill="{text_color}" '
            f'font-family="sans-serif" font-size="11" text-anchor="middle">{date_str}</text>'
        )

    # Render bars
    bars = []
    for d, count in zip(dates, counts):
        x_pos = get_x(d)
        bar_h = (count / max_count) * plot_h
        bar_y = (pad_top + plot_h) - bar_h
        bar_x = x_pos - bar_w / 2.0

        # Color: Highlight the most recent day
        color = secondary if d == dates[-1] else accent

        # Rounded corner dynamic cap
        rx = min(3.0, bar_h / 2.0) if bar_h > 0 else 0.0

        bars.append(
            f'<rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" '
            f'rx="{rx}" fill="{color}" opacity="0.9" />'
        )

    header = (
        f'<text x="{pad_left}" y="24" fill="{text_color}" '
        f'font-family="sans-serif" font-size="12" font-weight="bold">Daily Mature Cards Reviewed</text>'
    )

    # Assemble final SVG
    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" class="report-graph" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="background:{bg_color};">',
        '<!-- Header -->',
        header,
        '<!-- Gridlines -->',
        "\n".join(gridlines),
        '<!-- Date ticks -->',
        "\n".join(x_ticks),
        '<!-- Bars -->',
        "\n".join(bars),
        '</svg>'
    ]
    return "\n".join(svg_parts)


# ---------------------------------------------------------------------------
# Graph 3 — Stability Distribution
# ---------------------------------------------------------------------------

def render_stability_distribution(distribution: dict[str, int], config: dict) -> Optional[str]:
    """
    Render a horizontal stacked bar showing the FSRS stability distribution.

    Args:
        distribution: dict of {"< 7 days": count, ...}
        config: the add-on config dict.

    Returns:
        Inline SVG string, or None if the distribution is empty or total is 0.
    """
    if not distribution:
        return None

    total = sum(distribution.values())
    if total == 0:
        return None

    labels = list(distribution.keys())
    values = [distribution[k] for k in labels]
    pcts = [v / total * 100 for v in values]

    palette = ["#f7786b", "#f7c26b", "#7C6AF7", "#6bcff7", "#6bf7a4"]
    theme = config.get("graph_theme", "dark")

    bg_color = "transparent"
    text_color = "#e0e0ff" if theme == "dark" else "#1a1a2e"

    width, height = 900.0, 120.0
    bar_x_start = 20.0
    bar_y = 45.0
    bar_w_total = 860.0
    bar_h = 40.0

    segments = []
    running_x = bar_x_start

    for label, pct, color in zip(labels, pcts, palette):
        if pct == 0:
            continue
        w = (pct / 100.0) * bar_w_total
        safe_label = escape(str(label))

        # Segment rectangle
        segments.append(
            f'<rect x="{running_x}" y="{bar_y}" width="{w}" height="{bar_h}" fill="{color}" />'
        )

        # Text label (if space permits)
        if pct > 6.0:
            text_x = running_x + w / 2.0
            segments.append(
                f'<text x="{text_x}" y="{bar_y + 18}" fill="#ffffff" '
                f'font-family="sans-serif" font-size="10.5" font-weight="bold" text-anchor="middle">{safe_label}</text>'
                f'<text x="{text_x}" y="{bar_y + 31}" fill="#ffffff" '
                f'font-family="sans-serif" font-size="10" text-anchor="middle" opacity="0.85">{pct:.1f}%</text>'
            )
        running_x += w

    # Assemble final SVG with a ClipPath to give the overall bar beautiful rounded corners
    svg_parts = [
        f'<svg viewBox="0 0 {width} {height}" class="report-graph" width="100%" height="100%" xmlns="http://www.w3.org/2000/svg" style="background:{bg_color};">',
        '<defs>',
        f'  <clipPath id="bar-clip">',
        f'    <rect x="{bar_x_start}" y="{bar_y}" width="{bar_w_total}" height="{bar_h}" rx="8" />',
        f'  </clipPath>',
        '</defs>',
        f'<text x="{width / 2.0}" y="24" fill="{text_color}" font-family="sans-serif" font-size="14" font-weight="bold" text-anchor="middle">🧠  FSRS Stability Distribution</text>',
        f'<g clip-path="url(#bar-clip)">',
        "\n".join(segments),
        '</g>',
        '</svg>'
    ]
    return "\n".join(svg_parts)


# ---------------------------------------------------------------------------
# Render all graphs at once
# ---------------------------------------------------------------------------

def render_all_graphs(metrics: dict, config: dict) -> dict[str, Optional[str]]:
    """
    Render all graphs and return a dict of inline SVG XML strings keyed by graph name.
    """
    growth_history = metrics.get("growth_history", [])
    distribution = metrics.get("stability_distribution", {})

    graphs: dict[str, Optional[str]] = {}

    if config.get("show_growth_graph", True):
        graphs["growth"] = render_growth_graph(growth_history, config)
        graphs["volume"] = render_volume_graph(growth_history, config)

    if config.get("show_fsrs_metrics", True) and distribution:
        graphs["stability_dist"] = render_stability_distribution(distribution, config)

    return graphs
