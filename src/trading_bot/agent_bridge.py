from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Optional

_INSIGHTS_FILE = Path(__file__).parents[2] / "reports" / "agent_insights.json"


def _atomic_write(path: Path, text: str) -> None:
    """Write-temp + os.replace so a concurrent reader / crash can't see a torn file.
    (Prevents corruption; full lost-update protection still needs a lock.)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


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
    _atomic_write(_INSIGHTS_FILE, json.dumps(entries, indent=2))


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


def record_agent_insights_batch(rows: list[dict], on_date: Optional[str] = None,
                                path: Optional[object] = None) -> int:
    """Append many insights at once, deduped by (date, insight). Returns the number
    actually added. Used by the nightly learner to publish its lesson lines without
    creating duplicates on re-runs of the same date. ``path`` overrides the default
    insights file (defaults to reports/agent_insights.json — what the dashboard reads)."""
    from pathlib import Path as _Path
    target = _Path(path) if path is not None else _INSIGHTS_FILE
    try:
        entries = json.loads(target.read_text(encoding="utf-8")) if target.exists() else []
    except (json.JSONDecodeError, OSError):
        entries = []
    d = on_date or str(date.today())
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
        _atomic_write(target, json.dumps(entries, indent=2))
    return added
