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
