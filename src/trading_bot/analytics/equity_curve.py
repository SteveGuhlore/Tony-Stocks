"""Normalized paper equity curve (roadmap item 7 backend).

Publishes the bot's realized paper-equity series indexed to 100 so it can be overlaid
against the Command Center's Tony series for a clean head-to-head: unequal capital
($1M Tony vs $100k bot) collapses to a pure %-return comparison. Each side publishes
its own curve; either dashboard fetches both and overlays them.

Realized only (deterministic, no live prices): a point per closed position in
close-time order, plus a baseline 100. The live "now" / marked-to-market point is added
by the frontend, which already has live prices — keeping this builder pure + testable.
Research only; no profitability claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EquityPoint:
    t: str
    equity: float
    index: float  # equity normalized so the baseline == 100

    def to_dict(self) -> dict[str, Any]:
        return {"t": self.t, "equity": self.equity, "index": self.index}


@dataclass
class EquityCurve:
    label: str
    base_equity: float
    points: list[EquityPoint]
    return_pct: float
    research_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "base_equity": self.base_equity,
            "points": [p.to_dict() for p in self.points],
            "return_pct": self.return_pct,
            "research_only": self.research_only,
            "note": "Realized paper equity indexed to 100. Research only; not a profitability claim.",
        }


def _to_float(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def open_positions_unrealized_pl(
    open_positions: list[dict[str, Any]],
    live_prices: dict[str, float] | None,
) -> float:
    """Sum the mark-to-market unrealized P/L of OPEN paper positions.

    Pure: prices are injected (no network). For each open row with a usable qty,
    fill price (``entry_price``), and a live price for its symbol, add
    ``qty * (live - fill)``. Rows missing any of those — or whose symbol has no live
    price — contribute 0. Returns 0.0 when ``live_prices`` is None/empty.
    """
    if not live_prices:
        return 0.0
    prices = {str(s).upper(): p for s, p in live_prices.items()}
    total = 0.0
    for r in open_positions:
        symbol = str(r.get("symbol", "")).upper()
        live = _to_float(prices.get(symbol))
        qty = _to_float(r.get("qty"))
        fill = _to_float(r.get("entry_price"))
        if live is None or qty is None or fill is None:
            continue
        total += qty * (live - fill)
    return total


def build_paper_equity_curve(
    closed_positions: list[dict[str, Any]],
    *,
    base_equity: float,
    label: str = "bot",
    open_positions: list[dict[str, Any]] | None = None,
    live_prices: dict[str, float] | None = None,
) -> EquityCurve:
    """Build a normalized realized-equity curve from closed paper positions.

    Rows missing ``closed_at`` or ``realized_pl`` are skipped. Points are emitted in
    ascending close-time order, prefixed with a baseline point at index 100. With no
    valid closed trades the curve is empty (the frontend shows "collecting…").

    When ``open_positions`` and a non-empty ``live_prices`` map are supplied, the
    unrealized P/L of the open book (each position marked to its live price) is folded
    into the LATEST point only — so the bot's curve compares like-for-like against the
    Command Center, which marks its open positions live. When ``live_prices`` is
    None/empty the result is unchanged (realized-only). Pure: prices are injected.
    """
    rows = [
        r for r in closed_positions
        if r.get("closed_at") and _to_float(r.get("realized_pl")) is not None
    ]
    rows.sort(key=lambda r: str(r["closed_at"]))

    points: list[EquityPoint] = []
    if not rows or base_equity <= 0:
        return EquityCurve(label=label, base_equity=base_equity, points=points, return_pct=0.0)

    points.append(EquityPoint(t=str(rows[0]["closed_at"]), equity=round(base_equity, 2), index=100.0))
    cumulative = 0.0
    for r in rows:
        cumulative += _to_float(r["realized_pl"]) or 0.0
        equity = base_equity + cumulative
        points.append(EquityPoint(
            t=str(r["closed_at"]),
            equity=round(equity, 2),
            index=round(equity / base_equity * 100.0, 4),
        ))

    unrealized = open_positions_unrealized_pl(open_positions or [], live_prices)
    if unrealized:
        last = points[-1]
        equity = base_equity + cumulative + unrealized
        points[-1] = EquityPoint(
            t=last.t,
            equity=round(equity, 2),
            index=round(equity / base_equity * 100.0, 4),
        )

    return_pct = round(points[-1].index - 100.0, 4)
    return EquityCurve(label=label, base_equity=base_equity, points=points, return_pct=return_pct)
