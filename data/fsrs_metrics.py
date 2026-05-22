# -*- coding: utf-8 -*-
"""
data/fsrs_metrics.py — FSRS State Parser & Metrics Calculator
==============================================================
Parses the JSON blobs stored in ``cards.data`` (Anki ≥ 23.10 with FSRS
enabled) and computes aggregate metrics used in the report.

FSRS v5 state fields stored in cards.data:
    s  (float) — Stability in days: how long before retrievability drops to 90 %
    d  (float) — Difficulty on a 1–10 scale (higher = harder)
    r  (float) — Retrievability at time of last review (0–1)

Note: older Anki versions or cards that have never been reviewed with FSRS
      will have empty or non-FSRS data blobs. We handle this gracefully.
"""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import dataclass, field
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

def parse_fsrs_states(raw_blobs: list[str]) -> list[FSRSState]:
    """
    Parse a list of raw JSON strings from ``cards.data`` into FSRSState objects.
    Silently skips any blobs that are missing required fields or are malformed.

    Args:
        raw_blobs: List of JSON strings, e.g. ['{"s":8.25,"d":5.1,"r":0.9}', ...]

    Returns:
        A list of valid FSRSState instances. May be shorter than the input.
    """
    states: list[FSRSState] = []
    for blob in raw_blobs:
        if not blob or blob in ("{}", "null"):
            continue
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            continue

        s = data.get("s")
        d = data.get("d")
        r = data.get("r")

        # All three fields are required and must be positive numbers
        if s is None or d is None or r is None:
            continue
        try:
            s, d, r = float(s), float(d), float(r)
        except (TypeError, ValueError):
            continue

        if s <= 0 or not (0 <= r <= 1) or not (0 < d <= 10):
            continue

        states.append(FSRSState(stability=s, difficulty=d, retrievability=r))

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
    etk = sum(retrievabilities)  # Expected Total Knowledge
    struggling = sum(1 for r in retrievabilities if r < 0.70)
    mastered = sum(1 for s in stabilities if s >= 30)

    return {
        "has_fsrs": True,
        "fsrs_card_count": n,
        "median_stability_days": round(median_s, 2),
        "median_stability_mo": round(median_s / 30.5, 2),
        "mean_difficulty": round(mean_d, 2),
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


def enrich_metrics_with_fsrs(metrics: dict, raw_blobs: list[str]) -> dict:
    """
    Top-level convenience: parse FSRS blobs, compute metrics, merge into
    the main metrics dict that came from ``queries.get_all_metrics()``.

    Modifies ``metrics`` in-place and returns it.
    """
    states = parse_fsrs_states(raw_blobs)
    fsrs = compute_fsrs_metrics(states)
    distribution = get_stability_distribution(states) if states else {}

    metrics.update(fsrs)
    metrics["stability_distribution"] = distribution
    # Remove the raw blob list — not needed downstream
    metrics.pop("_fsrs_raw", None)

    return metrics
