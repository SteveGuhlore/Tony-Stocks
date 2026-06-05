from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Optional

_INSIGHTS_FILE = Path(__file__).parents[2] / "reports" / "agent_insights.json"


def record_agent_insight(
    insight: str,
    category: str = "general",
    confidence: str = "low",
    symbols: Optional[list[str]] = None,
) -> None:
    """Write an agent-generated insight to reports/agent_insights.json for dashboard display."""
    entries = _load_all()
    entries.append({
        "date": str(date.today()),
        "category": category,
        "insight": insight,
        "confidence": confidence,
        "symbols": symbols or [],
        "status": "new",
    })
    _INSIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _INSIGHTS_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def load_agent_insights(limit: int = 20) -> list[dict]:
    """Return the most recent agent insights (newest last)."""
    return _load_all()[-limit:]


def _load_all() -> list[dict]:
    if not _INSIGHTS_FILE.exists():
        return []
    try:
        return json.loads(_INSIGHTS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def record_agent_insights_batch(rows: list[dict], on_date: Optional[str] = None) -> int:
    """Append many insights at once, deduped by (date, insight). Returns the number
    actually added. Used by the nightly learner to publish its lesson lines without
    creating duplicates on re-runs of the same date."""
    d = on_date or str(date.today())
    entries = _load_all()
    existing = {(e.get("date"), e.get("insight")) for e in entries}
    added = 0
    for r in rows:
        text = str(r.get("insight") or "").strip()
        if not text or (d, text) in existing:
            continue
        entries.append({
            "date": d,
            "category": str(r.get("category") or "general"),
            "insight": text,
            "confidence": str(r.get("confidence") or "low"),
            "symbols": list(r.get("symbols") or []),
            "status": "new",
        })
        existing.add((d, text))
        added += 1
    if added:
        _INSIGHTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _INSIGHTS_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return added
