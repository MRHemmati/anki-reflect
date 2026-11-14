# -*- coding: utf-8 -*-
"""
report/insights.py — Narrative Insight Engine
===============================================
Converts raw numeric metrics into human-readable, conversational insight
strings. The engine uses **conditional Python logic** (no LLM by default)
so the add-on works fully offline and deterministically.

Architecture:
    InsightEngine.generate(metrics, config)
        → dict of insight strings consumed by the Jinja2 template

Optional LLM mode: if ``config["llm_enabled"]`` is True and a valid API key
is present, the engine will attempt to call the configured provider to
generate the main narrative paragraph, falling back to the template engine
if the call fails.
"""

from __future__ import annotations

import datetime
from html import escape
from typing import Optional


# ---------------------------------------------------------------------------
# Threshold constants (tunable without touching logic)
# ---------------------------------------------------------------------------

class Thresholds:
    """Centralised numeric thresholds for insight categorisation."""
    # Session volume
    HIGH_VOLUME    = 200
    MEDIUM_VOLUME  = 100
    LOW_VOLUME     = 30

    # Speed (seconds/card)
    FAST_PACE      = 6.0
    NORMAL_PACE    = 10.0

    # Retention
    EXCELLENT_RET  = 90.0
    GOOD_RET       = 80.0
    FAIR_RET       = 70.0

    # Lapse rate
    LOW_LAPSE      = 10.0
    HIGH_LAPSE     = 20.0

    # Stability (days)
    HIGH_STABILITY = 60.0   # > 2 months
    LOW_STABILITY  = 14.0   # < 2 weeks

    # Mature percentage
    HIGH_MATURE    = 70.0
    LOW_MATURE     = 40.0


# ---------------------------------------------------------------------------
# Core insight engine
# ---------------------------------------------------------------------------

class InsightEngine:
    """
    Generates narrative insight strings from a metrics dict.

    Usage::

        engine = InsightEngine()
        insights = engine.generate(metrics, config)
        # insights is a plain dict of strings, used in the Jinja2 template
    """

    def generate(self, metrics: dict, config: dict) -> dict:
        """
        Run all insight generators and return a combined dict.

        Args:
            metrics: The fully enriched metrics dict from ``builder.py``.
            config:  The add-on config dict.

        Returns:
            A dict where every value is a string (or None) safe to embed in HTML.
        """
        insights: dict[str, Optional[str]] = {}

        insights["report_date"] = self._report_date(config)
        insights["headline"] = self._headline(metrics)
        insights["volume_note"] = self._volume_note(metrics)
        insights["speed_note"] = self._speed_note(metrics)
        insights["retention_note"] = self._retention_note(metrics)
        insights["lapse_note"] = self._lapse_note(metrics)
        insights["mature_note"] = self._mature_note(metrics)
        insights["leech_note"] = self._leech_note(metrics)
        insights["fsrs_note"] = self._fsrs_note(metrics)
        insights["etk_note"] = self._etk_note(metrics)
        insights["overall_emoji"] = self._overall_emoji(metrics)
        insights["session_title"] = self._session_title(metrics)
        insights["closing_message"] = self._closing_message(metrics)

        # Optionally replace the main narrative via LLM
        if config.get("llm_enabled", False) and config.get("llm_api_key", ""):
            narrative = self._try_llm_narrative(metrics, config)
            if narrative:
                insights["llm_narrative"] = narrative

        return insights

    # ------------------------------------------------------------------
    # Individual insight generators
    # ------------------------------------------------------------------

    def _report_date(self, config: dict) -> str:
        scope = config.get("report_scope", "today")
        now = datetime.datetime.now()
        month_day_year = f"{now.strftime('%B')} {now.day}, {now.year}"
        scope_label = {
            "today": f"Today — {now.strftime('%A')}, {month_day_year}",
            "week":  f"This Week — ending {month_day_year}",
            "month": f"This Month — {now.strftime('%B %Y')}",
        }.get(scope, month_day_year)
        return scope_label

    def _headline(self, m: dict) -> str:
        n = m.get("total_reviews", 0)
        if n >= Thresholds.HIGH_VOLUME:
            return "Another High-Volume Speedrun"
        elif n >= Thresholds.MEDIUM_VOLUME:
            return "Solid Session — Consistent Effort"
        elif n >= Thresholds.LOW_VOLUME:
            return "Short But Focused"
        elif n > 0:
            return "Keeping the Streak Alive"
        else:
            return "No Reviews Yet Today"

    def _session_title(self, m: dict) -> str:
        n = m.get("total_reviews", 0)
        ret = m.get("mature_retention", 0.0)
        if n == 0:
            return "Ready When You Are"
        if n >= Thresholds.HIGH_VOLUME and ret >= Thresholds.GOOD_RET:
            return "Holding Steady at High Speeds"
        elif n >= Thresholds.HIGH_VOLUME:
            return "High Volume — Watch Your Retention"
        elif ret >= Thresholds.EXCELLENT_RET:
            return "Peak Precision"
        elif ret >= Thresholds.GOOD_RET:
            return "Steady Progress"
        else:
            return "Room to Grow"

    def _volume_note(self, m: dict) -> str:
        n = m.get("total_reviews", 0)
        t = m.get("total_time_min", 0.0)
        s = m.get("avg_time_sec", 0.0)
        streak = m.get("streak_days", 0)
        if n == 0:
            if streak > 0:
                return (
                    f"No reviews recorded in this period yet — review today to extend your "
                    f"<strong>{streak:,}-day streak</strong>."
                )
            return "No reviews recorded in this period."
        streak_str = (
            f" You're on a <strong>{streak:,}-day study streak</strong>!"
            if streak > 1
            else ""
        )
        time_prep = "in just" if s <= Thresholds.NORMAL_PACE else "over"
        return (
            f"You tackled a {'heavy' if n >= Thresholds.HIGH_VOLUME else 'solid'} load of "
            f"<strong>{n:,} cards</strong> and cleared them {time_prep} "
            f"<strong>{t:.2f} minutes</strong> "
            f"({s:.2f} seconds per card).{streak_str}"
        )

    def _speed_note(self, m: dict) -> str:
        if m.get("total_reviews", 0) == 0:
            return ""
        s = m.get("avg_time_sec", 0.0)
        prev_s = m.get("prev_avg_time_sec", 0.0)
        delta = s - prev_s if prev_s else 0
        direction = "faster" if delta < 0 else "slower"
        delta_str = (
            f" That's <strong>{abs(delta):.2f}s {direction}</strong> than your previous period."
            if prev_s and abs(delta) >= 0.01 else ""
        )
        if s <= Thresholds.FAST_PACE:
            note = f"Blazing pace at {s:.2f}s/card — you're in the zone."
        elif s <= Thresholds.NORMAL_PACE:
            note = f"Comfortable pace at {s:.2f}s/card — steady and deliberate."
        else:
            note = f"Taking your time at {s:.2f}s/card — perhaps some tricky cards today?"
        return note + delta_str

    def _retention_note(self, m: dict) -> str:
        ret = m.get("mature_retention", 0.0)
        correct = m.get("mature_correct", 0)
        total = m.get("mature_total", 0)
        if total == 0:
            return "No mature card reviews in this period."
        if ret >= Thresholds.EXCELLENT_RET:
            adj = "Outstanding"
        elif ret >= Thresholds.GOOD_RET:
            adj = "Solid"
        elif ret >= Thresholds.FAIR_RET:
            adj = "Acceptable"
        else:
            adj = "Struggling"
        return (
            f"{adj} retention — mature card accuracy hit "
            f"<strong>{ret:.2f}%</strong> "
            f"({correct:,} out of {total:,} correct)."
        )

    def _lapse_note(self, m: dict) -> str:
        lr = m.get("lapse_rate", 0.0)
        again = m.get("again_count", 0)
        total = m.get("total_reviews", 0)
        ret = m.get("mature_retention", 0.0)
        if total == 0:
            return ""
        if lr <= Thresholds.LOW_LAPSE:
            verdict = "Very low — excellent memory recall."
        elif lr <= Thresholds.HIGH_LAPSE:
            verdict = "Moderate — within the normal range."
        elif ret >= Thresholds.EXCELLENT_RET and m.get("mature_total", 0) > 0:
            verdict = "High — mostly on new or learning cards while your mature retention stayed strong."
        else:
            verdict = "High — consider reviewing your difficult cards more frequently."
        return (
            f"Lapse Rate: <strong>&quot;Again&quot; count was {lr:.2f}%</strong> "
            f"({again:,} cards). {verdict}"
        )

    def _leech_note(self, m: dict) -> str:
        hotspots = m.get("leech_hotspots", [])
        if not hotspots or hotspots[0]["leech_count_7d"] == 0:
            return "No major leech hotspots detected in your active decks. Great job maintaining memory stability!"

        top = hotspots[0]
        deck_name = escape(str(top["deck_name"]))
        leech_count = top["leech_count_7d"]
        rate = top["leeches_per_100_reviews"]

        return (
            f"Your highest leech density is in <strong>{deck_name}</strong>, yielding "
            f"<strong>{leech_count:,} leech cards</strong> ({rate:.2f} per 100 reviews) this week. "
            f"Focusing targeted review sessions or editing these cards could help resolve these persistent lapses."
        )

    def _mature_note(self, m: dict) -> str:
        count = m.get("mature_count", 0)
        pct = m.get("mature_pct", 0.0)
        total = m.get("total_cards", 0)
        if total == 0:
            return ""
        if pct >= Thresholds.HIGH_MATURE:
            milestone = "Your collection is predominantly mature — impressive long-term retention."
        elif pct >= Thresholds.LOW_MATURE:
            milestone = "A healthy mix of new and mature material."
        else:
            milestone = "Still building your mature card base — keep the daily reviews going."
        return (
            f"Total mature cards: <strong>{count:,}</strong> "
            f"({pct:.1f}% of {total:,} total). {milestone}"
        )

    def _fsrs_note(self, m: dict) -> str:
        if not m.get("has_fsrs", False):
            raw_count = m.get("fsrs_raw_blob_count", 0)
            if raw_count:
                return (
                    f"FSRS metrics were not parsed from the "
                    f"<strong>{raw_count:,}</strong> active-deck card data blobs found. "
                    "This usually means the stored card data does not match the "
                    "expected FSRS state format yet."
                )
            return (
                "FSRS metrics are not available for the active decks in this report yet. "
                "Enable FSRS scheduling in Anki preferences for deeper insights."
            )
        med_mo = m.get("median_stability_mo", 0.0)
        diff = m.get("mean_difficulty", 0.0)
        pct_struggling = m.get("pct_struggling", 0.0)

        stability_comment = (
            "Excellent long-term retention across your collection." if med_mo >= 2.0
            else "Cards are still building momentum — keep reviewing." if med_mo < 0.5
            else "Solid stability — the algorithm is working for you."
        )
        return (
            f"Median Stability hit <strong>{med_mo:.2f} months</strong>. "
            f"Mean Difficulty: <strong>{diff:.2f}/10</strong>. "
            f"{pct_struggling:.1f}% of cards have retrievability below 70%. "
            f"{stability_comment}"
        )

    def _etk_note(self, m: dict) -> str:
        if not m.get("has_fsrs", False):
            return ""
        etk = m.get("estimated_knowledge", 0.0)
        fsrs_count = m.get("fsrs_card_count", 0)
        return (
            f"Estimated Total Knowledge: <strong>{etk:,.0f} cards</strong> "
            f"(expected recall across your {fsrs_count:,} FSRS-tracked cards "
            f"right now)."
        )

    def _overall_emoji(self, m: dict) -> str:
        ret = m.get("mature_retention", 0.0)
        lr = m.get("lapse_rate", 100.0)
        if ret >= Thresholds.EXCELLENT_RET and lr <= Thresholds.LOW_LAPSE:
            return "🌟"
        elif ret >= Thresholds.GOOD_RET:
            return "✅"
        elif ret >= Thresholds.FAIR_RET:
            return "📈"
        else:
            return "💪"

    def _closing_message(self, m: dict) -> str:
        n = m.get("total_reviews", 0)
        ret = m.get("mature_retention", 0.0)
        if n == 0:
            return "Open your decks and start your session — consistency is everything."
        if ret >= Thresholds.EXCELLENT_RET:
            return "Phenomenal session. Your future self is thanking you. 🚀"
        elif ret >= Thresholds.GOOD_RET:
            return "Great work today. Keep the momentum going tomorrow."
        elif ret >= Thresholds.FAIR_RET:
            return (
                "Decent session. Identify the cards you're struggling with "
                "and give them extra attention."
            )
        else:
            return (
                "Tough session — that's okay. Difficult reviews now mean "
                "stronger memories later. Keep going. 💪"
            )

    # ------------------------------------------------------------------
    # Optional LLM integration
    # ------------------------------------------------------------------

    def _try_llm_narrative(self, metrics: dict, config: dict) -> Optional[str]:
        """
        Attempt to generate a narrative paragraph using the configured LLM.
        Returns None on any failure (network error, invalid key, etc.).
        """
        try:
            provider = config.get("llm_provider", "openai")
            if provider == "openai":
                return self._call_openai(metrics, config)
            elif provider == "anthropic":
                return self._call_anthropic(metrics, config)
        except Exception:
            pass
        return None

    def _build_llm_prompt(self, m: dict) -> str:
        """Build the prompt sent to the LLM."""
        return f"""You are a warm, encouraging Anki study coach. Write a 3-4 sentence
narrative reflection for a user's study session. Be specific about the numbers,
conversational, and motivating. Do NOT use bullet points.

Session data:
- Cards reviewed: {m.get('total_reviews', 0)}
- Time spent: {m.get('total_time_min', 0):.1f} minutes
- Avg speed: {m.get('avg_time_sec', 0):.2f}s/card
- Mature retention: {m.get('mature_retention', 0):.1f}%
- Lapse rate: {m.get('lapse_rate', 0):.1f}%
- Mature cards: {m.get('mature_count', 0):,} ({m.get('mature_pct', 0):.1f}% of collection)
- Median stability: {m.get('median_stability_mo', 0):.2f} months
- Estimated knowledge: {m.get('estimated_knowledge', 0):,.0f} cards

Write the reflection now:"""

    def _call_openai(self, metrics: dict, config: dict) -> Optional[str]:
        import urllib.request
        import json as _json

        api_key = config["llm_api_key"]
        model = config.get("llm_model", "gpt-4o-mini")
        prompt = self._build_llm_prompt(metrics)

        payload = _json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": config.get("llm_temperature", 0.7),
            "max_tokens": 300,
        }).encode()

        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        return data["choices"][0]["message"]["content"].strip()

    def _call_anthropic(self, metrics: dict, config: dict) -> Optional[str]:
        import urllib.request
        import json as _json

        api_key = config["llm_api_key"]
        model = config.get("llm_model", "claude-3-haiku-20240307")
        prompt = self._build_llm_prompt(metrics)

        payload = _json.dumps({
            "model": model,
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = _json.loads(resp.read())
        return data["content"][0]["text"].strip()
