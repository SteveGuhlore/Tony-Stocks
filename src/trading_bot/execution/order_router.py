"""Pure paper-trading order router (phase 2).

Decides whether a triggered pick becomes a paper order and how it is sized. Pure:
no network, no I/O — all account state is passed in as a ``PortfolioState``. Every
gate fails closed and a rejection carries a human-readable reason. Long equity only.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from trading_bot.execution.paper_config import PaperTradingConfig

#: Sector buckets that are never concentration-capped. A risk gate must not reject a
#: trade merely because we cannot classify it (fail-open on unknown), and benchmarks/
#: ETFs are references, not a concentrated cohort. Values are normalized (lowercased).
_UNCAPPED_SECTORS = frozenset({"", "unknown", "benchmark", "market"})


@dataclass(frozen=True)
class PortfolioState:
    """Account snapshot the router needs to apply capacity + dedup gates."""

    equity: float
    open_symbols: frozenset[str] = frozenset()
    open_positions: int = 0
    orders_today: int = 0
    exited_today: frozenset[str] = frozenset()  # symbols already closed today (no same-day re-entry)
    # Normalized sector -> count of currently-open positions in that sector. Built by the
    # impure caller (paper_engine) so this router stays pure. Default empty -> sector cap no-ops.
    open_sector_counts: Mapping[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class OrderDecision:
    """Router verdict. ``quantity`` is 0 on any rejection."""

    approved: bool
    quantity: int
    reason: str


def _to_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
    except (TypeError, ValueError):
        return None
    # NaN must fail closed here: it slips through every comparison gate (NaN >= x is
    # False) and then int(risk // NaN) raises, killing the whole cycle's pick loop.
    return None if f != f else f


def size_position(*, entry: Any, stop: Any, equity: Any, config: PaperTradingConfig) -> int:
    """Risk-% share count: floor((equity * risk%/100) / (entry-stop)), capped by max notional.

    Returns 0 when inputs are missing/invalid or the size rounds to zero (a long
    requires stop strictly below entry).
    """
    e = _to_float(entry)
    s = _to_float(stop)
    eq = _to_float(equity)
    if e is None or s is None or eq is None:
        return 0
    if e <= 0 or eq <= 0:
        return 0
    risk_per_share = e - s
    if risk_per_share <= 0:  # stop must be below entry for a long
        return 0
    dollar_risk = eq * (config.risk_per_trade_pct / 100.0)
    shares = int(dollar_risk // risk_per_share)
    if config.max_notional_per_position > 0:
        max_shares_by_notional = int(config.max_notional_per_position // e)
        shares = min(shares, max_shares_by_notional)
    # No-leverage ceiling: never size a long beyond available equity. This also bounds
    # the qty-explosion case where a vanishingly small (entry-stop) and a disabled
    # max_notional (==0) would otherwise yield an enormous share count.
    max_shares_by_equity = int(eq // e)
    shares = min(shares, max_shares_by_equity)
    return max(shares, 0)


def should_trade(
    *,
    symbol: str,
    entry: Any,
    stop: Any,
    target: Any = None,
    sector: str = "",
    state: PortfolioState,
    config: PaperTradingConfig,
    kill_switch: bool = False,
    market_open: bool = True,
) -> OrderDecision:
    """Apply every safety/capacity gate and size the order. Fails closed."""
    sym = str(symbol or "").upper()

    if not config.enabled:
        return OrderDecision(False, 0, "paper trading disabled")
    if kill_switch:
        return OrderDecision(False, 0, "kill switch engaged")
    if not market_open:
        return OrderDecision(False, 0, "market closed")
    if sym in {str(s).upper() for s in state.open_symbols}:
        return OrderDecision(False, 0, f"duplicate: already an open position for {sym}")
    if config.block_same_day_reentry and sym in {str(s).upper() for s in state.exited_today}:
        return OrderDecision(False, 0, f"no same-day re-entry: {sym} already exited today")
    if state.open_positions >= config.max_open_positions:
        return OrderDecision(False, 0, f"max_open_positions reached ({config.max_open_positions})")
    sec = (sector or "").strip().lower()
    sector_cap = config.max_positions_per_sector
    if sector_cap > 0 and sec and sec not in _UNCAPPED_SECTORS:
        if state.open_sector_counts.get(sec, 0) >= sector_cap:
            return OrderDecision(
                False, 0, f"sector cap reached for {sec} ({sector_cap} open)"
            )
    if state.orders_today >= config.max_daily_orders:
        return OrderDecision(False, 0, f"max daily orders reached ({config.max_daily_orders})")

    e = _to_float(entry)
    s = _to_float(stop)
    if e is None or s is None or s >= e:
        return OrderDecision(False, 0, "invalid plan: stop must be below entry")

    qty = size_position(entry=e, stop=s, equity=state.equity, config=config)
    if qty <= 0:
        return OrderDecision(False, 0, "position size rounds to 0")

    return OrderDecision(True, qty, f"approved: {qty} shares of {sym} (risk ~{config.risk_per_trade_pct}% of equity)")
