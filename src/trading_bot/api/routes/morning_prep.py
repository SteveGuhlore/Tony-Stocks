"""GET /api/morning-prep — off-hours research engine morning-prep output.

Reads the most recent ``reports/morning_prep/<date>.json`` file (written by
Task 5's ``write_morning_prep_report``) and maps it to ``MorningPrepResponse``
for the dashboard's morning-prep tab.

Resilient by design: a missing dir, missing file, empty file, or corrupt JSON
all degrade to an empty 200 response — the dashboard tab shows "awaiting" rather
than erroring.  NEVER 500.

Dir resolution: identical to command_center.py — reads ``app.state.reports_dir``
(set from the ``REPORTS_DIR`` env var in main.py's lifespan) so that both
production and tests use the same wiring.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request

from trading_bot.api.schemas import MorningPrepResponse, PrepCandidateResponse

LOGGER = logging.getLogger(__name__)

router = APIRouter(tags=["morning-prep"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _morning_prep_dir(reports_dir: Path) -> Path:
    return reports_dir / "morning_prep"


def _latest_report(morning_prep_dir: Path) -> dict[str, Any] | None:
    """Return the parsed JSON of the lexicographically latest *.json in the dir.

    Returns None when:
    - the directory does not exist,
    - there are no .json files,
    - the latest file is empty or not valid JSON.
    """
    try:
        if not morning_prep_dir.is_dir():
            return None
        files = sorted(morning_prep_dir.glob("*.json"))
        if not files:
            return None
        latest = files[-1]
        text = latest.read_text(encoding="utf-8").strip()
        if not text:
            return None
        return json.loads(text)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        # Degrade to an empty response (never 500), but leave a breadcrumb so an
        # operator can see that a present-but-unreadable report was skipped.
        LOGGER.warning("morning-prep: skipping unreadable report (%s)", exc)
        return None


def _map_candidate(raw: Any) -> PrepCandidateResponse:
    """Map a raw dict to PrepCandidateResponse with safe defaults."""
    if not isinstance(raw, dict):
        return PrepCandidateResponse()
    return PrepCandidateResponse(
        symbol=str(raw.get("symbol") or ""),
        score=float(raw.get("score") or 0.0),
        setup=str(raw.get("setup") or ""),
        entry=_to_float_or_none(raw.get("entry")),
        stop=_to_float_or_none(raw.get("stop")),
        target=_to_float_or_none(raw.get("target")),
        rr=_to_float_or_none(raw.get("rr")),
        conviction=str(raw.get("conviction") or ""),
        catalysts=raw.get("catalysts") if isinstance(raw.get("catalysts"), dict) else {},
        warnings=raw.get("warnings") if isinstance(raw.get("warnings"), list) else [],
    )


def _to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_morning_prep_response(raw: dict[str, Any] | None) -> MorningPrepResponse:
    """Map a raw report dict to MorningPrepResponse.

    None / wrong type / missing fields all yield well-formed defaults.
    """
    if not isinstance(raw, dict):
        return MorningPrepResponse()

    raw_shortlist = raw.get("shortlist")
    shortlist: list[PrepCandidateResponse] = []
    if isinstance(raw_shortlist, list):
        shortlist = [_map_candidate(c) for c in raw_shortlist]

    return MorningPrepResponse(
        generated_at=str(raw.get("generated_at") or ""),
        et_date=str(raw.get("et_date") or ""),
        phase=str(raw.get("phase") or ""),
        shortlist=shortlist,
        what_changed_overnight=str(raw.get("what_changed_overnight") or ""),
        plan_for_open=str(raw.get("plan_for_open") or ""),
    )


# ── Route ─────────────────────────────────────────────────────────────────────

@router.get("/morning-prep", response_model=MorningPrepResponse)
def get_morning_prep(request: Request) -> MorningPrepResponse:
    reports_dir = Path(getattr(request.app.state, "reports_dir", "reports"))
    raw = _latest_report(_morning_prep_dir(reports_dir))
    return build_morning_prep_response(raw)
