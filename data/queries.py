# -*- coding: utf-8 -*-
"""
data/queries.py — Anki SQLite Query Layer
==========================================
All database reads go through this module. Every function accepts an Anki
`DB` connection object (``mw.col.db``) and a configuration dict, and returns
plain Python primitives — no Anki internals leak beyond this layer, which
makes the module independently testable against a fixture database.

Anki revlog schema (relevant columns):
  id     INTEGER  — epoch milliseconds of the review (primary key)
  cid    INTEGER  — card id (foreign key → cards.id)
  ease   INTEGER  — 1=Again, 2=Hard, 3=Good, 4=Easy
  time   INTEGER  — review duration in milliseconds
  type   INTEGER  — 0=learn, 1=review, 2=relearn, 3=filtered/cram, 4=manual

Anki cards schema (relevant columns):
  id     INTEGER  — card id
  did    INTEGER  — deck id
  ivl    INTEGER  — current interval in days (negative = seconds for learning)
  queue  INTEGER  — -3=sched buried, -2=user buried, -1=suspended, 0=new,
                    1=learn, 2=review, 3=day-learn, 4=preview
  data   TEXT     — JSON blob; FSRS state stored here in Anki ≥ 23.10
"""

from __future__ import annotations

import time
import datetime
import statistics
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _today_cutoff_ms() -> int:
    """Return epoch-ms for midnight of the current local day."""
    now = datetime.datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(midnight.timestamp() * 1000)


def _days_ago_cutoff_ms(days: int) -> int:
    """Return epoch-ms for midnight ``days`` ago."""
    now = datetime.datetime.now()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    delta = datetime.timedelta(days=days)
    return int((midnight - delta).timestamp() * 1000)


def _scope_cutoff_ms(scope: str) -> int:
    """Convert a report scope string into an epoch-ms cutoff timestamp."""
    mapping = {
        "today": 0,
        "week": 7,
        "month": 30,
    }
    days = mapping.get(scope, 0)
    if days == 0:
        return _today_cutoff_ms()
    return _days_ago_cutoff_ms(days)


def _deck_id_clause(db: Any, deck_filter: str) -> tuple[str, list[int]]:
    """
    Build a SQL ``IN (...)`` clause and a list of deck IDs based on the filter.

    Returns:
        A tuple of (clause_str, [deck_id, ...]) where clause_str is either
        '' (no filter, all decks) or 'AND c.did IN (?,?,...)'.
    """
    if deck_filter == "all":
        return "", []

    # Fetch all decks and filter by name prefix
    rows = db.all("SELECT id, name FROM decks")
    matching_ids = [
        row[0] for row in rows
        if row[1] == deck_filter or row[1].startswith(deck_filter + "::")
    ]
    if not matching_ids:
        return "", []

    placeholders = ",".join("?" * len(matching_ids))
    clause = f"AND c.did IN ({placeholders})"
    return clause, matching_ids


# ---------------------------------------------------------------------------
# Public query functions
# ---------------------------------------------------------------------------

def get_session_overview(db: Any, config: dict) -> dict:
    """
    Fetch the core session metrics: review count, time spent, and speed.

    Returns a dict with keys:
        total_reviews   int   — number of reviews in the scope window
        total_time_ms   int   — total review time in milliseconds
        total_time_min  float — total review time in minutes
        avg_time_sec    float — average seconds per card
    """
    scope_cutoff = _scope_cutoff_ms(config.get("report_scope", "today"))
    deck_clause, deck_ids = _deck_id_clause(db, config.get("deck_filter", "all"))

    # Build query — join revlog → cards only when a deck filter is active
    if deck_ids:
        sql = f"""
            SELECT COUNT(*), SUM(r.time), AVG(r.time)
            FROM revlog r
            JOIN cards c ON r.cid = c.id
            WHERE r.id >= ?
              AND r.type IN (0, 1, 2, 3)
              {deck_clause}
        """
        params = [scope_cutoff] + deck_ids
    else:
        sql = """
            SELECT COUNT(*), SUM(time), AVG(time)
            FROM revlog
            WHERE id >= ?
              AND type IN (0, 1, 2, 3)
        """
        params = [scope_cutoff]

    row = db.first(sql, *params)
    count = row[0] if (row and row[0]) else 0
    total_ms = row[1] if (row and row[1]) else 0
    avg_ms = row[2] if (row and row[2]) else 0

    return {
        "total_reviews": count,
        "total_time_ms": total_ms,
        "total_time_min": round(total_ms / 60_000, 2),
        "avg_time_sec": round(avg_ms / 1000, 2),
    }


def get_mature_stats(db: Any, config: dict) -> dict:
    """
    Fetch mature card count and today's retention rate on mature cards.

    "Mature" = cards with ivl >= mature_threshold_days and queue >= 0
    (i.e., not suspended/buried).

    Returns a dict with keys:
        mature_count        int   — total mature cards in collection
        total_cards         int   — total non-suspended cards
        mature_pct          float — mature_count / total_cards * 100
        mature_correct      int   — correct reviews on mature cards in scope
        mature_total        int   — total reviews on mature cards in scope
        mature_retention    float — mature_correct / mature_total * 100
    """
    threshold = config.get("mature_threshold_days", 21)
    scope_cutoff = _scope_cutoff_ms(config.get("report_scope", "today"))
    deck_clause, deck_ids = _deck_id_clause(db, config.get("deck_filter", "all"))

    # --- Total non-suspended cards ---
    if deck_ids:
        total_sql = f"""
            SELECT COUNT(*) FROM cards
            WHERE queue >= 0 {deck_clause.replace('c.did', 'did')}
        """
        total_cards = db.scalar(total_sql, *deck_ids) or 0
    else:
        total_cards = db.scalar(
            "SELECT COUNT(*) FROM cards WHERE queue >= 0"
        ) or 0

    # --- Mature card count ---
    if deck_ids:
        mature_count_sql = f"""
            SELECT COUNT(*) FROM cards
            WHERE queue >= 0 AND ivl >= ?
            {deck_clause.replace('c.did', 'did')}
        """
        mature_count_params = [threshold] + deck_ids
    else:
        mature_count_sql = "SELECT COUNT(*) FROM cards WHERE queue >= 0 AND ivl >= ?"
        mature_count_params = [threshold]
    mature_count = db.scalar(mature_count_sql, *mature_count_params) or 0

    # --- Retention: reviews on mature cards in scope window ---
    if deck_ids:
        ret_sql = f"""
            SELECT
                SUM(CASE WHEN r.ease > 1 THEN 1 ELSE 0 END),
                COUNT(*)
            FROM revlog r
            JOIN cards c ON r.cid = c.id
            WHERE r.id >= ?
              AND r.type IN (1, 2)
              AND c.ivl >= ?
              AND c.queue >= 0
              {deck_clause}
        """
        ret_params = [scope_cutoff, threshold] + deck_ids
    else:
        ret_sql = """
            SELECT
                SUM(CASE WHEN r.ease > 1 THEN 1 ELSE 0 END),
                COUNT(*)
            FROM revlog r
            JOIN cards c ON r.cid = c.id
            WHERE r.id >= ?
              AND r.type IN (1, 2)
              AND c.ivl >= ?
              AND c.queue >= 0
        """
        ret_params = [scope_cutoff, threshold]

    ret_row = db.first(ret_sql, *ret_params)
    correct = ret_row[0] if (ret_row and ret_row[0]) else 0
    ret_total = ret_row[1] if (ret_row and ret_row[1]) else 0
    retention = round(correct / ret_total * 100, 2) if ret_total > 0 else 0.0

    return {
        "mature_count": mature_count,
        "total_cards": total_cards,
        "mature_pct": round(mature_count / total_cards * 100, 2) if total_cards else 0.0,
        "mature_correct": correct,
        "mature_total": ret_total,
        "mature_retention": retention,
    }


def get_lapse_stats(db: Any, config: dict) -> dict:
    """
    Fetch lapse ("Again") rate for the scope window.

    Returns a dict with keys:
        again_count     int   — number of "Again" (ease=1) presses
        total_reviews   int   — total reviews
        lapse_rate      float — again_count / total_reviews * 100
    """
    scope_cutoff = _scope_cutoff_ms(config.get("report_scope", "today"))
    deck_clause, deck_ids = _deck_id_clause(db, config.get("deck_filter", "all"))

    if deck_ids:
        sql = f"""
            SELECT
                SUM(CASE WHEN r.ease = 1 THEN 1 ELSE 0 END),
                COUNT(*)
            FROM revlog r
            JOIN cards c ON r.cid = c.id
            WHERE r.id >= ?
              AND r.type IN (0, 1, 2, 3)
              {deck_clause}
        """
        params = [scope_cutoff] + deck_ids
    else:
        sql = """
            SELECT
                SUM(CASE WHEN ease = 1 THEN 1 ELSE 0 END),
                COUNT(*)
            FROM revlog
            WHERE id >= ?
              AND type IN (0, 1, 2, 3)
        """
        params = [scope_cutoff]

    row = db.first(sql, *params)
    again = row[0] if (row and row[0]) else 0
    total = row[1] if (row and row[1]) else 0
    return {
        "again_count": again,
        "total_reviews": total,
        "lapse_rate": round(again / total * 100, 2) if total else 0.0,
    }


def get_previous_period_stats(db: Any, config: dict) -> dict:
    """
    Fetch equivalent metrics for the previous period (for the comparison table).

    Returns the same structure as ``get_session_overview`` but for the period
    immediately preceding the current scope window.
    """
    scope = config.get("report_scope", "today")
    scope_days = {"today": 1, "week": 7, "month": 30}.get(scope, 1)

    current_start = _scope_cutoff_ms(scope)
    prev_end = current_start
    prev_start = _days_ago_cutoff_ms(scope_days * 2)  # one period back

    # Simple query (no deck filter for previous period to keep it fast)
    sql = """
        SELECT COUNT(*), SUM(time), AVG(time)
        FROM revlog
        WHERE id >= ? AND id < ?
          AND type IN (0, 1, 2, 3)
    """
    row = db.first(sql, prev_start, prev_end)
    count = row[0] if (row and row[0]) else 0
    total_ms = row[1] if (row and row[1]) else 0
    avg_ms = row[2] if (row and row[2]) else 0

    return {
        "total_reviews": count,
        "total_time_min": round(total_ms / 60_000, 2),
        "avg_time_sec": round(avg_ms / 1000, 2),
    }


def get_growth_history(db: Any, config: dict) -> list[dict]:
    """
    Fetch daily mature card counts over the configured history window.

    Because revlog doesn't track "maturity at time of review" directly, we
    approximate: for each day, count distinct card IDs in revlog that had a
    positive review (ease > 1) up to that day and whose *current* interval
    is >= mature_threshold. This is a fast approximation that matches what
    Anki's native stats show.

    Returns a list of dicts: [{"date": datetime.date, "mature_count": int}, ...]
    sorted ascending by date.
    """
    history_days = config.get("history_days", 90)
    threshold = config.get("mature_threshold_days", 21)
    cutoff = _days_ago_cutoff_ms(history_days)

    sql = """
        SELECT
            CAST(r.id / 86400000 AS INTEGER) AS day_epoch,
            COUNT(DISTINCT r.cid)            AS reviews_on_day
        FROM revlog r
        JOIN cards c ON r.cid = c.id
        WHERE r.id >= ?
          AND r.type IN (1, 2)
          AND c.ivl >= ?
          AND c.queue >= 0
        GROUP BY day_epoch
        ORDER BY day_epoch ASC
    """
    rows = db.all(sql, cutoff, threshold)

    # Convert Unix day epoch → datetime.date and build cumulative counts
    result = []
    cumulative = 0
    for row in rows:
        day_epoch, count = row
        date = datetime.date.fromtimestamp(day_epoch * 86400)
        cumulative += count
        result.append({"date": date, "count": count})

    return result


def get_all_fsrs_data(db: Any, config: dict) -> list[dict]:
    """
    Return the raw FSRS state blobs for all non-suspended cards.

    Each row in ``cards.data`` is a JSON string like::

        {"s": 8.25, "d": 5.1, "r": 0.9, ...}

    We return the raw strings; parsing is handled by ``fsrs_metrics.py``.

    Returns a list of raw JSON strings (may include empty strings / '{}').
    """
    deck_clause, deck_ids = _deck_id_clause(db, config.get("deck_filter", "all"))

    if deck_ids:
        sql = f"""
            SELECT data FROM cards
            WHERE queue >= 0 AND data IS NOT NULL AND data != ''
            {deck_clause.replace('c.did', 'did')}
        """
        rows = db.list(sql, *deck_ids)
    else:
        rows = db.list(
            "SELECT data FROM cards WHERE queue >= 0 AND data IS NOT NULL AND data != ''"
        )

    return [row for row in rows if row]


def get_leech_hotspots(db: Any, config: dict) -> list[dict[str, Any]]:
    """
    Find decks with high leech card activity.
    Consider decks that:
      (a) had at least one review in the last 7 days.
      (b) have at least 50 reviews in the last 30 days.

    Returns:
        A list of dicts: [
            {
                "deck_id": int,
                "deck_name": str,
                "total_reviews_7d": int,
                "leech_count_7d": int,
                "leeches_per_100_reviews": float,
            }, ...
        ] sorted by leeches_per_100_reviews descending.
    """
    cutoff_7d = _days_ago_cutoff_ms(7)
    cutoff_30d = _days_ago_cutoff_ms(30)
    deck_clause, deck_ids = _deck_id_clause(db, config.get("deck_filter", "all"))

    # We join cards, notes, and decks to get the relevant metrics
    sql = f"""
        SELECT
            c.did,
            d.name,
            COUNT(CASE WHEN r.id >= ? THEN 1 END) AS reviews_7d,
            COUNT(*) AS reviews_30d,
            COUNT(DISTINCT CASE WHEN r.id >= ? AND ' ' || COALESCE(n.tags, '') || ' ' LIKE '% leech %' THEN c.id END) AS leech_count_7d
        FROM revlog r
        JOIN cards c ON r.cid = c.id
        JOIN notes n ON c.nid = n.id
        LEFT JOIN decks d ON c.did = d.id
        WHERE r.id >= ?
          AND r.type IN (0, 1, 2, 3)
          {deck_clause}
        GROUP BY c.did
        HAVING reviews_7d >= 1 AND reviews_30d >= 50
    """
    params = [cutoff_7d, cutoff_7d, cutoff_30d] + deck_ids
    rows = db.all(sql, *params)

    results = []
    for row in rows:
        did, name, reviews_7d, reviews_30d, leech_count_7d = row
        deck_name = name if name else f"Deck {did}"
        rate = round((leech_count_7d / reviews_7d) * 100, 2) if reviews_7d > 0 else 0.0
        results.append({
            "deck_id": did,
            "deck_name": deck_name,
            "total_reviews_7d": reviews_7d,
            "leech_count_7d": leech_count_7d,
            "leeches_per_100_reviews": rate,
        })

    results.sort(key=lambda x: x["leeches_per_100_reviews"], reverse=True)
    return results


def get_all_metrics(db: Any, config: dict) -> dict:
    """
    Convenience function: run all queries and return a single unified metrics dict.
    This is the primary entry point called by ``report/builder.py``.
    """
    overview = get_session_overview(db, config)
    mature = get_mature_stats(db, config)
    lapse = get_lapse_stats(db, config)
    previous = get_previous_period_stats(db, config)
    growth = get_growth_history(db, config)
    fsrs_raw = get_all_fsrs_data(db, config)
    leech_hotspots = get_leech_hotspots(db, config)

    return {
        # Session overview
        "total_reviews": overview["total_reviews"],
        "total_time_min": overview["total_time_min"],
        "avg_time_sec": overview["avg_time_sec"],
        # Mature stats
        "mature_count": mature["mature_count"],
        "total_cards": mature["total_cards"],
        "mature_pct": mature["mature_pct"],
        "mature_correct": mature["mature_correct"],
        "mature_total": mature["mature_total"],
        "mature_retention": mature["mature_retention"],
        # Lapse
        "again_count": lapse["again_count"],
        "lapse_rate": lapse["lapse_rate"],
        # Previous period (for comparison table)
        "prev_total_reviews": previous["total_reviews"],
        "prev_total_time_min": previous["total_time_min"],
        "prev_avg_time_sec": previous["avg_time_sec"],
        # History for graph
        "growth_history": growth,
        # Leech hotspots
        "leech_hotspots": leech_hotspots,
        # Raw FSRS data (parsed in fsrs_metrics.py)
        "_fsrs_raw": fsrs_raw,
    }
