"""Resolved-outcome emitter for the AI Operations Command Center.

Emits ``reports/tony_stocks_outcomes.json`` (override with ``TONY_OUTCOMES_FILE``)
so the Command Center can grade Tony's verdicts against what actually happened.

This is research-only reporting: it reads already-resolved outcome records and
writes JSON. It does not score, trade, or place any orders.

Schema (one object per resolved pick)::

    {symbol, pick_date, result, entry, exit, return_pct, days_held, resolved_date}

where ``result`` is one of ``target_hit | stop_hit | closed | expired``.

``pick_date`` is the **originating bridge date** (day-1 of ``days_active`` — the
date the pick first appeared in ``bridge/tony-stocks/YYYY-MM-DD.md``), which is the
join key the Command Center keys its ``(symbol, date)`` verdicts on. It is NOT the
entry date (entry can trigger days after the pick first appears).
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_DEFAULT_OUTCOMES_PATH = "reports/tony_stocks_outcomes.json"

# Raw outcome label / tracking status -> normalized terminal bucket.
_RESULT_MAP = {
    "target_hit": "target_hit",
    "target_before_stop": "target_hit",
    "stop_hit": "stop_hit",
    "stop_before_target": "stop_hit",
    "failed_setup": "stop_hit",
    "expired_no_trigger": "expired",
    "entry_not_triggered": "expired",
    "partial_move": "closed",
    "invalidated": "closed",
    "closed": "closed",
}

# Raw values that mean "not yet resolved" — these records are skipped.
_NON_TERMINAL = {"still_open", "insufficient_future_data", "active", "missing_real_data", ""}

_TRAILING_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})$")


def _first(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first non-None value among ``keys`` in ``record``."""
    for key in keys:
        if key in record and record[key] is not None:
            return record[key]
    return None


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        result = float(val)
    except (TypeError, ValueError):
        return None
    # NaN/inf are not valid JSON — emit null instead.
    if math.isnan(result) or math.isinf(result):
        return None
    return result


def _to_int(val: Any) -> int | None:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _date_part(val: Any) -> str | None:
    """Return the ``YYYY-MM-DD`` portion of an ISO date/datetime, else None."""
    if not val:
        return None
    return str(val).split("T")[0].split(" ")[0]


def _normalize_result(record: dict[str, Any]) -> str | None:
    """Map a record's raw result to a terminal bucket, or None to skip it."""
    raw = _first(record, ("result", "outcome_label", "tracking_status", "terminal_exit_reason"))
    key = str(raw or "").strip().lower()
    if key in _NON_TERMINAL:
        return None
    return _RESULT_MAP.get(key)


def _derive_pick_date(record: dict[str, Any]) -> str | None:
    """Resolve the originating bridge date for a pick (day-1 of days_active).

    Priority: explicit ``pick_date`` -> date embedded in ``pick_id`` ->
    first-seen timestamp -> ``entry_date`` minus (``days_active`` - 1) days ->
    bare ``entry_date`` as a last resort.
    """
    explicit = _date_part(_first(record, ("pick_date",)))
    if explicit:
        return explicit

    pick_id = _first(record, ("pick_id",))
    if pick_id:
        match = _TRAILING_DATE_RE.search(str(pick_id))
        if match:
            return match.group(1)

    first_seen = _date_part(_first(record, ("first_seen", "first_seen_date", "snapshot_time")))
    if first_seen:
        return first_seen

    entry_date = _date_part(_first(record, ("entry_date",)))
    days_active = _first(record, ("days_active",))
    if entry_date and isinstance(days_active, (int, float)) and int(days_active) >= 1:
        try:
            anchor = datetime.strptime(entry_date, "%Y-%m-%d")
            return (anchor - timedelta(days=int(days_active) - 1)).strftime("%Y-%m-%d")
        except ValueError:
            pass

    return entry_date


def build_tony_outcomes(records: list[dict[str, Any]], *, eod_date: str) -> list[dict[str, Any]]:
    """Normalize resolved outcome records into the Command Center outcome schema.

    Records that are not yet resolved (active / insufficient data / missing real
    data) are skipped. Pure: no I/O.
    """
    outcomes: list[dict[str, Any]] = []
    for record in records or []:
        result = _normalize_result(record)
        if result is None:
            continue
        outcomes.append(
            {
                "symbol": str(_first(record, ("symbol",)) or "").upper(),
                "pick_date": _derive_pick_date(record),
                "result": result,
                "entry": _to_float(
                    _first(record, ("entry", "entry_price", "original_entry_price", "actual_entry_price"))
                ),
                "exit": _to_float(_first(record, ("exit", "exit_price", "terminal_exit_price"))),
                "return_pct": _to_float(
                    _first(record, ("return_pct", "pl_pct", "terminal_research_pl_pct"))
                ),
                "days_held": _to_int(_first(record, ("days_held",))),
                "resolved_date": _date_part(_first(record, ("resolved_date",))) or eod_date,
            }
        )
    return outcomes


def write_tony_outcomes(records: list[dict[str, Any]], path: str | Path | None = None) -> Path:
    """Write the (already-built) outcome list to JSON.

    Path resolution: explicit ``path`` -> ``TONY_OUTCOMES_FILE`` env var ->
    ``reports/tony_stocks_outcomes.json``. Parent directories are created.
    """
    if path is None:
        path = os.environ.get("TONY_OUTCOMES_FILE") or _DEFAULT_OUTCOMES_PATH
    out_path = Path(path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2), encoding="utf-8")
    return out_path.resolve()
