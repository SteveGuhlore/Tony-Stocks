"""Time-aligned, indexed equity comparison for two paper accounts (bot vs Tony).

Pure transforms over Alpaca portfolio-history payloads ({timestamp[], equity[]}). The
route fetches BOTH accounts with the SAME period+timeframe so the timestamp grids line
up; these helpers index each series to 100 at its first real value and emit ISO-stamped
points the dashboard can plot on one shared time axis. Research only — not a
profitability claim.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def _index(equity: list[float]) -> tuple[list[float], float | None]:
    """Index an equity series to 100 at its first positive value. Returns (index, base)."""
    base = next((e for e in equity if e and e > 0), None)
    if base is None:
        return [100.0 for _ in equity], None
    return [round(e / base * 100.0, 4) if e else 100.0 for e in equity], base


def build_account_curve(hist: dict[str, Any] | None, label: str) -> dict[str, Any]:
    """One account's Alpaca portfolio-history → indexed, ISO-stamped points + return_pct.

    Empty-safe: a missing/malformed payload yields an empty curve (the dashboard shows
    "awaiting") instead of raising.
    """
    if not isinstance(hist, dict):
        return {"label": label, "points": [], "return_pct": None, "base_value": None}
    ts_raw = hist.get("timestamp") or []
    eq_raw = hist.get("equity") or []
    n = min(len(ts_raw), len(eq_raw))
    timestamps = [int(t) for t in ts_raw[:n]]
    equity = [float(e) if e is not None else 0.0 for e in eq_raw[:n]]
    index, base = _index(equity)
    points: list[dict[str, Any]] = []
    for ts, ix, eq in zip(timestamps, index, equity):
        points.append({
            "t": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            "ts": ts,
            "equity": ix,      # plotted value = the index (so both accounts share a ~100 scale)
            "index": ix,
            "value": round(eq, 2),
        })
    return {
        "label": label,
        "points": points,
        "return_pct": round(index[-1] - 100.0, 3) if index else None,
        "base_value": base,
    }


def align_common(bot: dict[str, Any], tony: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Trim both curves to their common timestamps and RE-index each to 100 at the first
    shared instant, so the comparison is over one identical window/clock. No-op when there
    is no overlap (returns the inputs unchanged)."""
    common = {p["ts"] for p in bot.get("points", [])} & {p["ts"] for p in tony.get("points", [])}
    if not common:
        return bot, tony

    def _rebase(curve: dict[str, Any]) -> dict[str, Any]:
        pts = [p for p in curve.get("points", []) if p["ts"] in common]
        pts.sort(key=lambda p: p["ts"])
        base = next((p["value"] for p in pts if p["value"] and p["value"] > 0), None)
        rebased: list[dict[str, Any]] = []
        for p in pts:
            ix = round(p["value"] / base * 100.0, 4) if base else 100.0
            rebased.append({**p, "equity": ix, "index": ix})
        return {
            **curve,
            "points": rebased,
            "return_pct": round(rebased[-1]["index"] - 100.0, 3) if rebased else None,
            "base_value": base,
        }

    return _rebase(bot), _rebase(tony)
