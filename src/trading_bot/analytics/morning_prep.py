"""Morning-prep assembler — pure deterministic core (off-hours research engine).

Consumes scan results + catalyst tags (Task 3) and produces a ranked shortlist
+ morning action plan. No I/O, no network, no LLM, no trading side-effects.

Column name notes (confirmed against repositories.py):
  - scan_results table: score field is ``final_score``; price levels are
    ``suggested_entry`` / ``suggested_stop`` / ``suggested_target_1``.
  - candidate_snapshots table: score field is ``total_score``; price levels are
    ``planned_entry_price`` / ``stop`` / ``target``.
  - scored_rows fed to this function use the names specified in the Task 4 contract
    (``total_score``, ``setup_category``, ``planned_entry_price``, ``stop_price``,
    ``target_price``), matching the candidate_snapshots schema with the stop/target
    renamed to ``stop_price`` / ``target_price`` for the dict representation.

Unused forward-compat parameters:
  - ``open_positions``: accepted but not used — reserved for future position-aware
    filtering (e.g. skip symbols already held).
  - ``calibration_proposals``: accepted but not used — reserved for future
    score-weight adjustment signals.
  - ``premarket``: accepted but not used — reserved for future pre-market price
    context (gap-up/gap-down signals).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from trading_bot.analytics.catalyst_enrichment import CatalystTags


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _to_float(value: Any) -> float | None:
    """Safely coerce value to float; return None on failure or NaN."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def _conviction_from_score(normalized_score: float) -> str:
    """Map a 0–1 normalized score to a conviction band."""
    if normalized_score >= 0.80:
        return "high"
    if normalized_score >= 0.60:
        return "medium"
    return "low"


def _downgrade_conviction(conviction: str) -> str:
    """Downgrade conviction by one band (high→medium, medium→low, low→low)."""
    if conviction == "high":
        return "medium"
    if conviction == "medium":
        return "low"
    return "low"


def _compute_rr(
    entry: float | None,
    stop: float | None,
    target: float | None,
) -> float | None:
    """Return risk/reward ratio or None when inputs are missing/invalid."""
    if entry is None or stop is None or target is None:
        return None
    risk = entry - stop
    if risk <= 0:
        # Zero or negative risk (stop at/above entry) is a data error, not a
        # tradeable setup — degrade to None rather than emit a meaningless R:R.
        return None
    return round((target - entry) / risk, 4)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PrepCandidate:
    """Immutable candidate entry in the morning shortlist."""

    symbol: str
    score: float           # normalized 0–1 (raw total_score / 100)
    setup: str
    entry: float | None
    stop: float | None
    target: float | None
    rr: float | None
    conviction: str        # "high" | "medium" | "low" (post-blackout-downgrade)
    catalysts: dict[str, Any]  # CatalystTags.to_dict() or {} if not present
    warnings: list[str]        # human-readable; includes "earnings blackout" when relevant

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "score": self.score,
            "setup": self.setup,
            "entry": self.entry,
            "stop": self.stop,
            "target": self.target,
            "rr": self.rr,
            "conviction": self.conviction,
            "catalysts": self.catalysts,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class MorningPrep:
    """Assembled morning prep package — pure, immutable, JSON-serializable."""

    generated_at: str           # ISO-8601 with UTC offset (now_et.isoformat())
    et_date: str                # YYYY-MM-DD derived from now_et
    phase: str                  # e.g. "pre_open", "overnight"
    shortlist: list[PrepCandidate]
    what_changed_overnight: str
    plan_for_open: str

    def to_dict(self) -> dict[str, Any]:
        """Return a fully JSON-serializable dict matching the spec shape."""
        return {
            "generated_at": self.generated_at,
            "et_date": self.et_date,
            "phase": self.phase,
            "shortlist": [c.to_dict() for c in self.shortlist],
            "what_changed_overnight": self.what_changed_overnight,
            "plan_for_open": self.plan_for_open,
        }


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------

def _build_what_changed(learning_facts: dict | None) -> str:
    """Deterministic overnight-changes summary.

    Assumptions on learning_facts structure (keys used with safe defaults):
      - ``dimensions``: list of dimension dicts — len() = number of "lessons" produced.
      - ``summary``: dict potentially containing ``win_rate`` (float) used to infer
        calibration state — "on-track" when win_rate >= 0.5, "needs-review" when
        below, "unknown" when absent.
    """
    if not learning_facts:
        return "No overnight changes."

    # n = number of dimension/lesson entries produced
    dimensions = learning_facts.get("dimensions") or []
    n = len(dimensions)

    # calibration state from summary.win_rate (safe fallback: unknown)
    summary = learning_facts.get("summary") or {}
    win_rate = _to_float(summary.get("win_rate"))
    if win_rate is None:
        calibration_state = "unknown"
    elif win_rate >= 0.50:
        calibration_state = "on-track"
    else:
        calibration_state = "needs-review"

    return f"{n} new lessons; calibration: {calibration_state}"


def build_morning_prep(
    *,
    scored_rows: list[dict],
    catalyst_tags: dict[str, CatalystTags],
    open_positions: list[dict] | None = None,       # forward-compat; unused
    learning_facts: dict | None = None,
    calibration_proposals: list[dict] | None = None,  # forward-compat; unused
    premarket: dict | None = None,                   # forward-compat; unused
    now_et: datetime,
    phase: str,
    shortlist_size: int = 20,
) -> MorningPrep:
    """Assemble the morning prep package from scored rows + catalyst tags.

    Parameters
    ----------
    scored_rows:
        Dicts with fields: symbol, total_score (0–100 scale), setup_category,
        planned_entry_price, stop_price, target_price.  Any missing field degrades
        safely (None levels → rr None; missing total_score → score 0.0).
    catalyst_tags:
        Map of symbol → CatalystTags; symbols absent from the map get empty catalysts.
    open_positions:
        Accepted for forward-compatibility; not used in this version.
    learning_facts:
        Optional NightlyFacts.to_dict() result wired into what_changed_overnight.
    calibration_proposals:
        Accepted for forward-compatibility; not used in this version.
    premarket:
        Accepted for forward-compatibility; not used in this version.
    now_et:
        Timezone-aware datetime in ET (America/New_York).  Used for et_date and
        generated_at.  Must carry tzinfo.
    phase:
        Descriptive phase string stored verbatim (e.g. "pre_open", "overnight").
    shortlist_size:
        Maximum number of candidates in the shortlist (default 20).
    """
    candidates: list[PrepCandidate] = []

    for row in scored_rows:
        symbol = str(row.get("symbol") or "").strip()
        if not symbol:
            continue

        # --- score (normalize 0-100 → 0-1) ---
        raw_score = _to_float(row.get("total_score"))
        norm_score: float = (raw_score / 100.0) if raw_score is not None else 0.0

        # --- setup ---
        setup = str(row.get("setup_category") or "").strip()

        # --- price levels ---
        entry = _to_float(row.get("planned_entry_price"))
        stop = _to_float(row.get("stop_price"))
        target = _to_float(row.get("target_price"))

        # --- rr ---
        rr = _compute_rr(entry, stop, target)

        # --- catalysts ---
        cat_obj: CatalystTags | None = catalyst_tags.get(symbol)
        catalysts_dict: dict = cat_obj.to_dict() if cat_obj is not None else {}

        # --- conviction + blackout downgrade ---
        conviction = _conviction_from_score(norm_score)
        in_blackout = bool(cat_obj.earnings_blackout) if cat_obj is not None else False
        if in_blackout:
            conviction = _downgrade_conviction(conviction)

        # --- warnings ---
        warnings: list[str] = []
        if in_blackout:
            warnings.append("earnings blackout")

        candidates.append(PrepCandidate(
            symbol=symbol,
            score=norm_score,
            setup=setup,
            entry=entry,
            stop=stop,
            target=target,
            rr=rr,
            conviction=conviction,
            catalysts=catalysts_dict,
            warnings=warnings,
        ))

    # --- sort descending by score, dedupe to one row per symbol, truncate ---
    # scored_rows can carry several snapshot rows per symbol (multiple scan runs);
    # collapse to the single highest-scored row per symbol so the watchlist is N
    # distinct names, not N rows.
    candidates.sort(key=lambda c: c.score, reverse=True)
    seen_symbols: set[str] = set()
    deduped: list[PrepCandidate] = []
    for candidate in candidates:
        if candidate.symbol in seen_symbols:
            continue
        seen_symbols.add(candidate.symbol)
        deduped.append(candidate)
    shortlist = deduped[:shortlist_size]

    # --- what_changed_overnight ---
    what_changed = _build_what_changed(learning_facts)

    # --- plan_for_open ---
    count = len(shortlist)
    high_count = sum(1 for c in shortlist if c.conviction == "high")
    blackout_count = sum(1 for c in shortlist if "earnings blackout" in c.warnings)
    plan_for_open = (
        f"{count} names armed; {high_count} high-conviction; "
        f"{blackout_count} in earnings blackout."
    )

    # --- date strings ---
    et_date = now_et.strftime("%Y-%m-%d")
    generated_at = now_et.isoformat()

    return MorningPrep(
        generated_at=generated_at,
        et_date=et_date,
        phase=phase,
        shortlist=shortlist,
        what_changed_overnight=what_changed,
        plan_for_open=plan_for_open,
    )
