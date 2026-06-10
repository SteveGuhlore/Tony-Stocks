"""Tests for paper_trading config loading + fail-closed safety (subsystem phase 1).

The paper-trading subsystem is OFF by default and independent of
live_trading_enabled (which stays false and blocks any real-money path). A
misconfigured-but-enabled block must fail CLOSED (treated as disabled), and the
broker base URL must always be Alpaca's PAPER endpoint.
"""
from __future__ import annotations

import pytest

from trading_bot.execution.paper_config import (
    PAPER_BASE_URL,
    PaperTradingConfig,
    assert_paper_base_url,
    load_paper_trading_config,
)


class TestLoadDefaults:
    def test_none_returns_disabled_safe_defaults(self):
        cfg = load_paper_trading_config(None)
        assert isinstance(cfg, PaperTradingConfig)
        assert cfg.enabled is False
        assert cfg.risk_per_trade_pct == 1.0
        assert cfg.max_open_positions == 8
        assert cfg.max_notional_per_position == 5000.0
        assert cfg.max_daily_orders == 20
        assert cfg.bracket is True
        assert cfg.base_url == PAPER_BASE_URL

    def test_empty_dict_disabled(self):
        assert load_paper_trading_config({}).enabled is False

    def test_disabled_block_has_no_failure_reason(self):
        cfg = load_paper_trading_config({"enabled": False})
        assert cfg.enabled is False
        assert cfg.disabled_reason is None

    def test_locked_defaults(self):
        cfg = load_paper_trading_config(None)
        # GTC by default so bracket stop/target protection persists overnight
        # (the entry is a never-resting market order — "day" would only expire protection).
        assert cfg.time_in_force == "gtc"
        assert cfg.gate_on_command_center is False
        assert cfg.close_on_command_center_exit is True
        assert cfg.account_label == "tony"


class TestLoadEnabled:
    def _full(self, **over):
        base = {
            "enabled": True,
            "risk_per_trade_pct": 2.0,
            "max_open_positions": 5,
            "max_notional_per_position": 3000,
            "max_daily_orders": 10,
            "bracket": True,
            "time_in_force": "gtc",
            "gate_on_command_center": True,
            "close_on_command_center_exit": False,
            "account_label": "cc",
        }
        base.update(over)
        return base

    def test_full_block_parsed(self):
        cfg = load_paper_trading_config(self._full())
        assert cfg.enabled is True
        assert cfg.risk_per_trade_pct == 2.0
        assert cfg.max_open_positions == 5
        assert cfg.max_notional_per_position == 3000.0
        assert cfg.max_daily_orders == 10
        assert cfg.time_in_force == "gtc"
        assert cfg.gate_on_command_center is True
        assert cfg.close_on_command_center_exit is False
        assert cfg.account_label == "cc"
        assert cfg.disabled_reason is None

    def test_partial_overrides_keep_defaults(self):
        cfg = load_paper_trading_config({"enabled": True, "risk_per_trade_pct": 0.5})
        assert cfg.enabled is True
        assert cfg.risk_per_trade_pct == 0.5
        assert cfg.max_open_positions == 8  # default preserved

    def test_time_in_force_normalized_lowercase(self):
        assert load_paper_trading_config({"enabled": True, "time_in_force": "DAY"}).time_in_force == "day"
        assert load_paper_trading_config({"enabled": True, "time_in_force": "Gtc"}).time_in_force == "gtc"

    def test_max_positions_per_sector_parsed(self):
        cfg = load_paper_trading_config(self._full(max_positions_per_sector=8))
        assert cfg.max_positions_per_sector == 8

    def test_max_positions_per_sector_defaults_to_zero(self):
        # Absent -> 0 (disabled), so the cap is opt-in and never silently engages.
        assert load_paper_trading_config({"enabled": True}).max_positions_per_sector == 0
        assert load_paper_trading_config(None).max_positions_per_sector == 0

    def test_negative_sector_cap_clamps_to_zero(self):
        cfg = load_paper_trading_config(self._full(max_positions_per_sector=-3))
        assert cfg.max_positions_per_sector == 0

    def test_zero_sector_cap_does_not_fail_closed(self):
        # 0 is a valid "disabled" value, NOT a misconfiguration -> stays enabled.
        cfg = load_paper_trading_config(self._full(max_positions_per_sector=0))
        assert cfg.enabled is True
        assert cfg.disabled_reason is None

    def test_invalid_time_in_force_defaults_to_gtc(self):
        # Invalid TIF falls back to the safe default (gtc = persistent protection).
        assert load_paper_trading_config({"enabled": True, "time_in_force": "ioc"}).time_in_force == "gtc"


class TestFailClosed:
    def test_zero_risk_pct_fails_closed(self):
        cfg = load_paper_trading_config({"enabled": True, "risk_per_trade_pct": 0})
        assert cfg.enabled is False
        assert cfg.disabled_reason

    def test_negative_risk_pct_fails_closed(self):
        cfg = load_paper_trading_config({"enabled": True, "risk_per_trade_pct": -1})
        assert cfg.enabled is False

    def test_risk_pct_over_100_fails_closed(self):
        cfg = load_paper_trading_config({"enabled": True, "risk_per_trade_pct": 150})
        assert cfg.enabled is False

    def test_zero_max_open_positions_fails_closed(self):
        cfg = load_paper_trading_config({"enabled": True, "max_open_positions": 0})
        assert cfg.enabled is False

    def test_zero_max_daily_orders_fails_closed(self):
        cfg = load_paper_trading_config({"enabled": True, "max_daily_orders": 0})
        assert cfg.enabled is False

    def test_nonpaper_base_url_fails_closed(self):
        cfg = load_paper_trading_config(
            {"enabled": True, "base_url": "https://api.alpaca.markets"}
        )
        assert cfg.enabled is False
        assert cfg.disabled_reason

    def test_paper_base_url_override_accepted(self):
        cfg = load_paper_trading_config(
            {"enabled": True, "base_url": "https://paper-api.alpaca.markets"}
        )
        assert cfg.enabled is True


class TestAssertPaperBaseUrl:
    def test_accepts_paper_url(self):
        assert_paper_base_url("https://paper-api.alpaca.markets")  # must not raise

    def test_rejects_live_url(self):
        with pytest.raises(ValueError):
            assert_paper_base_url("https://api.alpaca.markets")

    def test_rejects_empty(self):
        with pytest.raises(ValueError):
            assert_paper_base_url("")
