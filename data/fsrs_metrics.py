# -*- coding: utf-8 -*-
"""
data/fsrs_metrics.py — FSRS State Parser & Metrics Calculator
==============================================================
Parses the JSON blobs stored in ``cards.data`` (Anki ≥ 23.10 with FSRS
enabled) and computes aggregate metrics used in the report.

FSRS v5 state fields stored in cards.data:
    s  (float) — Stability in days: how long before retrievability drops to 90 %
    d  (float) — Difficulty on a 1–10 scale (higher = harder)
    r  (float) — Retrievability, when available directly (0–1)

Newer Anki/FSRS-6 data may instead store:
    dr     (float) — desired retention, usually 0.9
    lrt    (int)   — last review timestamp, seconds since epoch
    decay  (float) — per-card FSRS-6 decay parameter

For those cards, current retrievability is computed from stability, elapsed
days since last review, and decay.

Note: older Anki versions or cards that have never been reviewed with FSRS
      will have empty or non-FSRS data blobs. We handle this gracefully.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------

@dataclass
class FSRSState:
    """Parsed FSRS state for a single card."""
    stability: float          # days
    difficulty: float         # 1–10
    retrievability: float     # 0–1

    @property
    def stability_months(self) -> float:
        """Convenience: stability expressed in months (÷ 30.5)."""
        return round(self.stability / 30.5, 2)


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------

def _timestamp_seconds(value: object) -> Optional[float]:
    """Parse Anki timestamp values, accepting seconds or milliseconds."""
    try:
        ts = float(value)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    if ts > 10_000_000_000:
        ts /= 1000.0
    return ts


def _forgetting_curve_retrievability(
    stability: float,
    elapsed_days: float,
    decay: float,
) -> Optional[float]:
    """Return FSRS power forgetting curve retrievability."""
    if stability <= 0 or elapsed_days < 0 or decay <= 0:
        return None
    factor = 0.9 ** (-1.0 / decay) - 1.0
    retrievability = (1.0 + factor * elapsed_days / stability) ** (-decay)
    return max(0.0, min(1.0, retrievability))


def parse_fsrs_states(
    raw_blobs: list[str],
    now_ts: Optional[float] = None,
) -> list[FSRSState]:
    """
    Parse a list of raw JSON strings from ``cards.data`` into FSRSState objects.
    Silently skips any blobs that are missing required fields or are malformed.

    Args:
        raw_blobs: List of JSON strings, e.g. ['{"s":8.25,"d":5.1,"r":0.9}', ...]
        now_ts: Optional Unix timestamp in seconds, used for deterministic tests.

    Returns:
        A list of valid FSRSState instances. May be shorter than the input.
    """
    now_ts = time.time() if now_ts is None else now_ts
    states: list[FSRSState] = []
    for blob in raw_blobs:
        if not blob or blob in ("{}", "null"):
            continue
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, ValueError, TypeError):
            continue

        if not isinstance(data, dict):
            continue

        s = data.get("s")
        d = data.get("d")
        r = data.get("r")

        # Stability and difficulty are required for any FSRS memory state.
        if s is None or d is None:
            continue
        try:
            s, d = float(s), float(d)
        except (TypeError, ValueError):
            continue

        if s <= 0 or not (0 < d <= 10):
            continue

        if r is not None:
            try:
                retrievability = float(r)
            except (TypeError, ValueError):
                continue
        else:
            lrt = _timestamp_seconds(data.get("lrt"))
            if lrt is None:
                continue
            try:
                decay = float(data.get("decay", 0.5))
            except (TypeError, ValueError):
                decay = 0.5
            elapsed_days = max(0.0, (now_ts - lrt) / 86_400.0)
            retrievability = _forgetting_curve_retrievability(
                stability=s,
                elapsed_days=elapsed_days,
                decay=decay,
            )
            if retrievability is None:
                continue

        if not (0 <= retrievability <= 1):
            continue

        states.append(
            FSRSState(
                stability=s,
                difficulty=d,
                retrievability=retrievability,
            )
        )

    return states


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------

def compute_fsrs_metrics(states: list[FSRSState]) -> dict:
    """
    Compute aggregate FSRS metrics from a list of parsed FSRSState objects.

    Returns a dict with keys:
        has_fsrs              bool  — False if no FSRS states were found
        fsrs_card_count       int   — number of cards with FSRS data
        median_stability_days float — median stability across all cards
        median_stability_mo   float — median stability in months
        mean_difficulty       float — mean difficulty (1–10)
        estimated_knowledge   float — Σ retrievability ≈ expected cards recalled
        pct_struggling        float — % of cards with retrievability < 0.70
        pct_mastered          float — % of cards with stability >= 30 days
    """
    if not states:
        return {
            "has_fsrs": False,
            "fsrs_card_count": 0,
            "median_stability_days": 0.0,
            "median_stability_mo": 0.0,
            "mean_difficulty": 0.0,
            "mean_retrievability": 0.0,
            "estimated_knowledge": 0.0,
            "pct_struggling": 0.0,
            "pct_mastered": 0.0,
        }

    stabilities = [s.stability for s in states]
    difficulties = [s.difficulty for s in states]
    retrievabilities = [s.retrievability for s in states]
    n = len(states)

    median_s = statistics.median(stabilities)
    mean_d = statistics.mean(difficulties)
    mean_r = statistics.mean(retrievabilities)
    etk = sum(retrievabilities)  # Expected Total Knowledge
    struggling = sum(1 for r in retrievabilities if r < 0.70)
    mastered = sum(1 for s in stabilities if s >= 30)

    return {
        "has_fsrs": True,
        "fsrs_card_count": n,
        "median_stability_days": round(median_s, 2),
        "median_stability_mo": round(median_s / 30.5, 2),
        "mean_difficulty": round(mean_d, 2),
        "mean_retrievability": round(mean_r * 100, 1),
        "estimated_knowledge": round(etk, 1),
        "pct_struggling": round(struggling / n * 100, 1),
        "pct_mastered": round(mastered / n * 100, 1),
    }


def get_stability_distribution(states: list[FSRSState]) -> dict[str, int]:
    """
    Bucket card stabilities into human-readable ranges for display.

    Returns a dict with keys:
        "< 7 days"    — very young / learning phase
        "7–30 days"   — young mature
        "1–6 months"  — medium-term
        "6–24 months" — long-term
        "> 24 months" — extremely stable
    """
    buckets: dict[str, int] = {
        "< 7 days": 0,
        "7–30 days": 0,
        "1–6 months": 0,
        "6–24 months": 0,
        "> 24 months": 0,
    }
    for s in states:
        days = s.stability
        if days < 7:
            buckets["< 7 days"] += 1
        elif days < 30:
            buckets["7–30 days"] += 1
        elif days < 183:
            buckets["1–6 months"] += 1
        elif days < 730:
            buckets["6–24 months"] += 1
        else:
            buckets["> 24 months"] += 1
    return buckets


def enrich_metrics_with_fsrs(
    metrics: dict,
    raw_blobs: list[str],
    now_ts: Optional[float] = None,
) -> dict:
    """
    Top-level convenience: parse FSRS blobs, compute metrics, merge into
    the main metrics dict that came from ``queries.get_all_metrics()``.

    Modifies ``metrics`` in-place and returns it.
    """
    raw_blob_count = len(raw_blobs)
    states = parse_fsrs_states(raw_blobs, now_ts=now_ts)
    fsrs = compute_fsrs_metrics(states)
    distribution = get_stability_distribution(states) if states else {}

    metrics.update(fsrs)
    metrics["fsrs_raw_blob_count"] = raw_blob_count
    metrics["fsrs_parse_skipped_count"] = max(0, raw_blob_count - len(states))
    metrics["stability_distribution"] = distribution
    # Remove the raw blob list — not needed downstream
    metrics.pop("_fsrs_raw", None)

    return metrics
