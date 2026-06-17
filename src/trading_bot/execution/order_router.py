"""Pure paper-trading order router (phase 2).

Decides whether a triggered pick becomes a paper order and how it is sized. Pure:
no network, no I/O — all account state is passed in as a ``PortfolioState``. Every
gate fails closed and a rejection carries a human-readable reason. Long equity only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_bot.execution.paper_config import PaperTradingConfig


@dataclass(frozen=True)
class PortfolioState:
    """Account snapshot the router needs to apply capacity + dedup gates."""

    equity: float
    open_symbols: frozenset[str] = frozenset()
    open_positions: int = 0
    orders_today: int = 0


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
        return float(val)
    except (TypeError, ValueError):
        return None


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
    if state.open_positions >= config.max_open_positions:
        return OrderDecision(False, 0, f"max_open_positions reached ({config.max_open_positions})")
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
