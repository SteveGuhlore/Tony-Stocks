"""Tests for the pure paper-trading order router (phase 2).

The router decides whether a triggered pick becomes a paper order and how it is
sized. It is pure (no network, no I/O): all account state is passed in. Every gate
fails closed — a reject must carry a human-readable reason.
"""
from __future__ import annotations

import pytest

from trading_bot.execution.order_router import OrderDecision, PortfolioState, should_trade, size_position
from trading_bot.execution.paper_config import PaperTradingConfig


def _cfg(**over) -> PaperTradingConfig:
    base = dict(
        enabled=True,
        risk_per_trade_pct=1.0,
        max_open_positions=8,
        max_notional_per_position=5000.0,
        max_daily_orders=20,
    )
    base.update(over)
    return PaperTradingConfig(**base)


def _state(**over) -> PortfolioState:
    base = dict(equity=100_000.0, open_symbols=frozenset(), open_positions=0, orders_today=0)
    base.update(over)
    return PortfolioState(**base)


class TestSizePosition:
    def test_risk_pct_sizing(self):
        # 1% of 100k = $1000 risk; entry-stop = $5 => 200 shares (notional 20000),
        # capped by max_notional 5000 / entry 100 = 50 shares.
        assert size_position(entry=100.0, stop=95.0, equity=100_000.0, config=_cfg()) == 50

    def test_risk_pct_sizing_uncapped(self):
        # entry-stop = $5, 1% of 100k = $1000 -> 200 shares; notional cap 100k allows it.
        cfg = _cfg(max_notional_per_position=100_000.0)
        assert size_position(entry=100.0, stop=95.0, equity=100_000.0, config=cfg) == 200

    def test_rounds_down(self):
        # $1000 risk / $3 = 333.3 -> 333 shares; notional cap high.
        cfg = _cfg(max_notional_per_position=1_000_000.0)
        assert size_position(entry=50.0, stop=47.0, equity=100_000.0, config=cfg) == 333

    def test_stop_at_or_above_entry_is_zero(self):
        assert size_position(entry=100.0, stop=100.0, equity=100_000.0, config=_cfg()) == 0
        assert size_position(entry=100.0, stop=105.0, equity=100_000.0, config=_cfg()) == 0

    def test_zero_or_negative_equity_is_zero(self):
        assert size_position(entry=100.0, stop=95.0, equity=0.0, config=_cfg()) == 0

    def test_none_inputs_are_zero(self):
        assert size_position(entry=None, stop=95.0, equity=100_000.0, config=_cfg()) == 0
        assert size_position(entry=100.0, stop=None, equity=100_000.0, config=_cfg()) == 0

    def test_tiny_account_rounds_to_zero(self):
        # 1% of $100 = $1 risk / $5 = 0 shares.
        assert size_position(entry=100.0, stop=95.0, equity=100.0, config=_cfg()) == 0


class TestShouldTrade:
    def _ok_args(self, **over):
        base = dict(symbol="ZETA", entry=100.0, stop=95.0, target=115.0,
                    state=_state(), config=_cfg())
        base.update(over)
        return base

    def test_happy_path_approves_with_quantity(self):
        d = should_trade(**self._ok_args())
        assert isinstance(d, OrderDecision)
        assert d.approved is True
        assert d.quantity == 50
        assert d.reason

    def test_disabled_config_rejects(self):
        d = should_trade(**self._ok_args(config=_cfg(enabled=False)))
        assert d.approved is False
        assert "disabled" in d.reason.lower()

    def test_kill_switch_rejects(self):
        d = should_trade(**self._ok_args(kill_switch=True))
        assert d.approved is False
        assert "kill" in d.reason.lower()

    def test_market_closed_rejects(self):
        d = should_trade(**self._ok_args(market_open=False))
        assert d.approved is False
        assert "market" in d.reason.lower()

    def test_duplicate_open_symbol_rejects(self):
        d = should_trade(**self._ok_args(state=_state(open_symbols=frozenset({"ZETA"}))))
        assert d.approved is False
        assert "duplicate" in d.reason.lower() or "open position" in d.reason.lower()

    def test_duplicate_check_is_case_insensitive(self):
        d = should_trade(**self._ok_args(symbol="zeta", state=_state(open_symbols=frozenset({"ZETA"}))))
        assert d.approved is False

    def test_same_day_reentry_rejects(self):
        # Stop-out -> position closed -> NOT in open_symbols, but in exited_today: block re-buy.
        d = should_trade(**self._ok_args(state=_state(exited_today=frozenset({"ZETA"}))))
        assert d.approved is False
        assert "re-entry" in d.reason.lower()
        assert d.quantity == 0

    def test_same_day_reentry_check_is_case_insensitive(self):
        d = should_trade(**self._ok_args(symbol="zeta", state=_state(exited_today=frozenset({"ZETA"}))))
        assert d.approved is False

    def test_same_day_reentry_allowed_when_disabled(self):
        d = should_trade(**self._ok_args(
            state=_state(exited_today=frozenset({"ZETA"})),
            config=_cfg(block_same_day_reentry=False),
        ))
        assert d.approved is True

    def test_exited_today_does_not_block_other_symbols(self):
        d = should_trade(**self._ok_args(symbol="ZETA", state=_state(exited_today=frozenset({"AAPL"}))))
        assert d.approved is True

    def test_max_open_positions_rejects(self):
        d = should_trade(**self._ok_args(state=_state(open_positions=8), config=_cfg(max_open_positions=8)))
        assert d.approved is False
        assert "max_open_positions" in d.reason or "open positions" in d.reason.lower()

    def test_max_daily_orders_rejects(self):
        d = should_trade(**self._ok_args(state=_state(orders_today=20), config=_cfg(max_daily_orders=20)))
        assert d.approved is False
        assert "daily" in d.reason.lower()

    def test_invalid_plan_stop_above_entry_rejects(self):
        d = should_trade(**self._ok_args(entry=100.0, stop=101.0))
        assert d.approved is False
        assert "stop" in d.reason.lower() or "plan" in d.reason.lower()

    def test_size_zero_rejects(self):
        d = should_trade(**self._ok_args(state=_state(equity=100.0)))
        assert d.approved is False
        assert "size" in d.reason.lower() or "0" in d.reason

    def test_rejected_decision_has_zero_quantity(self):
        d = should_trade(**self._ok_args(kill_switch=True))
        assert d.quantity == 0


class TestBoundaries:
    """Edge cases at the exact gate thresholds and on hostile inputs. Capacity gates use
    >= (the Nth slot fills, the N+1th is refused); bad numerics must fail CLOSED."""

    def _ok_args(self, **over):
        base = dict(symbol="ZETA", entry=100.0, stop=95.0, target=115.0,
                    state=_state(), config=_cfg())
        base.update(over)
        return base

    def test_last_position_slot_is_usable(self):
        d = should_trade(**self._ok_args(state=_state(open_positions=7), config=_cfg(max_open_positions=8)))
        assert d.approved is True

    def test_last_daily_order_slot_is_usable(self):
        d = should_trade(**self._ok_args(state=_state(orders_today=19), config=_cfg(max_daily_orders=20)))
        assert d.approved is True

    def test_string_numeric_plan_is_accepted(self):
        # Picks deserialized from JSON/DB can carry numerics as strings.
        d = should_trade(**self._ok_args(entry="100.0", stop="95.0"))
        assert d.approved is True and d.quantity == 50

    def test_non_numeric_plan_fails_closed(self):
        for entry, stop in ((float("nan"), 95.0), ("oops", 95.0), (100.0, "oops")):
            d = should_trade(**self._ok_args(entry=entry, stop=stop))
            assert d.approved is False and d.quantity == 0

    def test_negative_prices_fail_closed(self):
        d = should_trade(**self._ok_args(entry=-100.0, stop=-105.0))
        assert d.approved is False and d.quantity == 0

    def test_penny_wide_stop_is_capped_by_notional(self):
        # 1% of 100k = $1000 risk / $0.01 = 100k shares -> notional cap must bite.
        d = should_trade(**self._ok_args(entry=100.0, stop=99.99))
        assert d.approved is True
        assert d.quantity == 50  # 5000 notional cap / 100 entry

    def test_zero_notional_cap_means_uncapped(self):
        qty = size_position(entry=100.0, stop=95.0, equity=100_000.0,
                            config=_cfg(max_notional_per_position=0.0))
        assert qty == 200  # pure risk sizing, no cap applied
