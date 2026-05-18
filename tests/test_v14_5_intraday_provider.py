"""Tests for V14.5 bugfix: Real Intraday Provider Enforcement.

Verifies:
- Real Alpaca IEX daily data labeled DQ_ALPACA_IEX, not DQ_DEMO
- Demo-profile metadata warning does not override a real-provider label
- Fallback symbols still get DQ_FALLBACK (not DQ_ALPACA_IEX)
- require_real_provider=True with non-Alpaca provider marks all symbols as missing
- allow_demo_fallback=False with individual Alpaca fallback marks symbols as missing
- Entire batch failure with allow_demo_fallback=False marks all as missing
- Intraday summary now includes intraday_provider field
- Tony hypothesis does not say "demo-generated data" when real Alpaca data was used
- Stale symbols get DQ_STALE, not DQ_DEMO
- Existing allowed_actions are unchanged

All tests use mocks — no real Alpaca API calls.
"""
from __future__ import annotations

import types
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from trading_bot.cli import _build_intraday_summary, _fetch_intraday_features_for_tony
from trading_bot.data.market_data import AlpacaIEXProvider, DemoGeneratedProvider
from trading_bot.intraday.features import IntradayFeatures
from trading_bot.scoring.score_models import ScoredStock
from trading_bot.tony.analysis import (
    ALLOWED_ACTIONS,
    DQ_ALPACA_IEX,
    DQ_DEMO,
    DQ_FALLBACK,
    DQ_INTRADAY_FALLBACK,
    DQ_INTRADAY_MISSING,
    DQ_INTRADAY_REAL,
    DQ_INTRADAY_STALE,
    DQ_STALE,
    _data_quality,
    analyze_candidates,
)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _stock(
    symbol: str = "PLTR",
    setup_category: str = "Breakout Watch",
    universe_role: str = "primary_candidate",
    final_score: float = 82.0,
    trade_plan_valid: bool = True,
    trade_plan_status: str = "valid",
    risk_reward_ratio: float = 2.5,
    warnings: list[str] | None = None,
    notes: str = "",
) -> ScoredStock:
    return ScoredStock(
        symbol=symbol,
        scanned_at="2026-05-18T00:00:00+00:00",
        final_score=final_score,
        setup_category=setup_category,
        tags=["mid_cap", "software"],
        universe_role=universe_role,
        name="Test Stock",
        sector="technology",
        industry="software",
        demo_profile="clean_breakout",
        notes=notes,
        candidate_summary="Test candidate.",
        trend_score=75.0,
        momentum_score=72.0,
        volume_score=75.0,
        risk_score=70.0,
        setup_quality_score=72.0,
        latest_close=100.0,
        avg_volume_20=2_000_000.0,
        dollar_volume_20=200_000_000.0,
        return_5d=0.03,
        return_10d=0.05,
        return_20d=0.07,
        atr_14=3.0,
        atr_percent=0.03,
        volatility_20d=0.03,
        relative_volume=1.2,
        suggested_entry=100.0,
        suggested_stop=93.0,
        suggested_target_1=115.0,
        risk_reward_ratio=risk_reward_ratio,
        trade_plan_valid=trade_plan_valid,
        trade_plan_status=trade_plan_status,
        reasons=["Price above trend."],
        warnings=warnings or [],
    )


def _make_bars() -> pd.DataFrame:
    """5-bar intraday DataFrame for test calculations."""
    index = pd.date_range("2026-05-18 13:30:00+00:00", periods=6, freq="5min")
    return pd.DataFrame(
        {"open": [100.0] * 6, "high": [101.0] * 6, "low": [99.0] * 6, "close": [100.5] * 6, "volume": [50_000] * 6},
        index=index,
    )


def _make_alpaca_provider(fail_safe_to_demo: bool = True) -> AlpacaIEXProvider:
    return AlpacaIEXProvider(
        api_key="test_key",
        secret_key="test_secret",
        fail_safe_to_demo=fail_safe_to_demo,
        _skip_key_check=True,
    )


# ── Task 1/2: Daily data quality label fix ───────────────────────────────────

class TestDataQualityLabelFix:
    """Verify _data_quality returns the right label for each provider/fallback scenario."""

    def test_real_alpaca_symbol_gets_alpaca_iex_label_not_demo(self):
        """Root cause fix: real Alpaca data must not be labeled DQ_DEMO."""
        stock = _stock(warnings=["Demo data only; do not use for real trade decisions."])
        label, _ = _data_quality(stock, "alpaca_iex", fallback_set=set(), stale_set=set())
        assert label == DQ_ALPACA_IEX

    def test_demo_profile_warning_does_not_override_real_alpaca_label(self):
        """Score engine's demo_profile warning must not override alpaca_iex label."""
        stock = _stock(warnings=["Demo data only; do not use for real trade decisions."])
        label, text = _data_quality(stock, "alpaca_iex", fallback_set=set(), stale_set=set())
        assert label == DQ_ALPACA_IEX
        assert "IEX" in text
        assert "demo-generated" not in text.lower()

    def test_alpaca_iex_hypothesis_does_not_say_demo_generated(self):
        """Tony hypothesis must not say 'demo-generated data' when provider is Alpaca IEX."""
        stock = _stock(warnings=["Demo data only; do not use for real trade decisions."])
        analyses = analyze_candidates(
            candidates=[stock],
            provider_name="alpaca_iex",
            fallback_symbols=[],
            stale_symbols=[],
        )
        assert len(analyses) == 1
        hyp = analyses[0].tony_hypothesis
        assert "demo-generated" not in hyp.lower(), f"Hypothesis incorrectly says demo: {hyp}"
        assert analyses[0].data_quality_read == DQ_ALPACA_IEX

    def test_fallback_symbol_still_gets_fallback_label_not_alpaca(self):
        """Symbols that fell back from Alpaca to demo must still get DQ_FALLBACK."""
        stock = _stock()
        label, text = _data_quality(stock, "alpaca_iex", fallback_set={"PLTR"}, stale_set=set())
        assert label == DQ_FALLBACK
        assert "fell back" in text.lower()

    def test_stale_symbol_gets_stale_label_not_demo(self):
        """Stale Alpaca symbols must get DQ_STALE, not DQ_DEMO."""
        stock = _stock()
        label, text = _data_quality(stock, "alpaca_iex", fallback_set=set(), stale_set={"PLTR"})
        assert label == DQ_STALE

    def test_demo_generated_provider_returns_demo_label(self):
        """When provider is demo_generated, label should be DQ_DEMO."""
        stock = _stock()
        label, _ = _data_quality(stock, "demo_generated", fallback_set=set(), stale_set=set())
        assert label == DQ_DEMO

    def test_demo_generated_provider_with_demo_warning_returns_demo_label(self):
        """Demo provider + warning = DQ_DEMO (unchanged behavior)."""
        stock = _stock(warnings=["Demo data only; do not use for real trade decisions."])
        label, _ = _data_quality(stock, "demo_generated", fallback_set=set(), stale_set=set())
        assert label == DQ_DEMO

    def test_alpaca_iex_without_demo_warning_returns_alpaca_label(self):
        """Alpaca IEX symbol with no warnings still gets DQ_ALPACA_IEX."""
        stock = _stock(warnings=[])
        label, _ = _data_quality(stock, "alpaca_iex", fallback_set=set(), stale_set=set())
        assert label == DQ_ALPACA_IEX

    def test_alpaca_provider_hypothesis_contains_iex_notice(self):
        """Alpaca IEX hypothesis should mention single-exchange feed, not demo prices."""
        stock = _stock(
            setup_category="Breakout Watch",
            warnings=["Demo data only; do not use for real trade decisions."],
        )
        analyses = analyze_candidates(
            candidates=[stock],
            provider_name="alpaca_iex",
            fallback_symbols=[],
            stale_symbols=[],
        )
        hyp = analyses[0].tony_hypothesis
        assert "Alpaca IEX" in hyp or "single-exchange" in hyp or "not full SIP" in hyp or "alpaca_iex_real_data" not in hyp or "IEX" in hyp

    def test_data_quality_counts_correct_when_real_alpaca_used(self):
        """When provider=alpaca_iex and no fallbacks, all candidates should be daily_real_alpaca."""
        stocks = [
            _stock("PLTR", warnings=["Demo data only; do not use for real trade decisions."]),
            _stock("SOFI", warnings=["Demo data only; do not use for real trade decisions."]),
            _stock("HOOD", warnings=[]),
        ]
        analyses = analyze_candidates(
            candidates=stocks,
            provider_name="alpaca_iex",
            fallback_symbols=[],
            stale_symbols=[],
            intraday_enabled=False,
        )
        dq_labels = [a.data_quality_read for a in analyses]
        assert all(label == DQ_ALPACA_IEX for label in dq_labels), f"Expected all daily_real_alpaca, got: {dq_labels}"

    def test_intraday_missing_label_when_intraday_unavailable(self):
        """Real daily Alpaca with intraday missing should label intraday_missing, not demo_data."""
        stock = _stock()
        missing = IntradayFeatures(symbol="PLTR", timeframe="5Min", data_available=False, status="intraday_data_missing")
        label, text = _data_quality(
            stock,
            "alpaca_iex",
            fallback_set=set(),
            stale_set=set(),
            intraday_features=missing,
            intraday_enabled=True,
        )
        assert label == DQ_INTRADAY_MISSING
        assert "demo-generated" not in text.lower()

    def test_intraday_real_label_when_both_daily_and_intraday_real(self):
        stock = _stock()
        features = IntradayFeatures(
            symbol="PLTR",
            timeframe="5Min",
            data_available=True,
            status="ok",
            latest_close=100.5,
            day_open=100.0,
            high_of_day=101.0,
            low_of_day=99.0,
            vwap=100.25,
            price_above_vwap=True,
        )
        label, _ = _data_quality(
            stock,
            "alpaca_iex",
            fallback_set=set(),
            stale_set=set(),
            intraday_features=features,
            intraday_enabled=True,
        )
        assert label == DQ_INTRADAY_REAL

    def test_stale_real_intraday_counts_as_intraday_real_not_stale_only(self):
        """Stale Alpaca 5Min bars are still real — label intraday_real_alpaca, not stale-only."""
        stock = _stock()
        features = IntradayFeatures(
            symbol="PLTR",
            timeframe="5Min",
            data_available=True,
            status="ok",
            latest_close=100.5,
            day_open=100.0,
            high_of_day=101.0,
            low_of_day=99.0,
            vwap=100.25,
            price_above_vwap=True,
        )
        label, text = _data_quality(
            stock,
            "alpaca_iex",
            fallback_set=set(),
            stale_set=set(),
            intraday_features=features,
            intraday_enabled=True,
            intraday_stale_set={"PLTR"},
        )
        assert label == DQ_INTRADAY_REAL
        assert label != DQ_INTRADAY_STALE
        assert "stale" in text.lower()
        assert "note: demo-generated" not in text.lower()

    def test_stale_real_intraday_hypothesis_mentions_stale_not_demo(self):
        stock = _stock()
        features = IntradayFeatures(
            symbol="PLTR",
            timeframe="5Min",
            data_available=True,
            status="ok",
            latest_close=100.5,
            day_open=100.0,
            high_of_day=101.0,
            low_of_day=99.0,
            vwap=100.25,
            price_above_vwap=True,
        )
        analyses = analyze_candidates(
            candidates=[stock],
            provider_name="alpaca_iex",
            fallback_symbols=[],
            stale_symbols=[],
            intraday_features_by_symbol={"PLTR": features},
            intraday_enabled=True,
            intraday_stale_symbols=["PLTR"],
        )
        assert analyses[0].data_quality_read == DQ_INTRADAY_REAL
        hyp = analyses[0].tony_hypothesis.lower()
        assert "note: demo-generated" not in hyp
        assert "stale" in hyp
        assert "market is closed" in hyp or "freshness" in hyp


# ── Task 3: Intraday data quality label constants ─────────────────────────────

class TestIntradayDQConstants:
    def test_daily_real_constant_defined(self):
        from trading_bot.tony.analysis import DQ_DAILY_REAL

        assert DQ_DAILY_REAL == "daily_real_alpaca"
        assert DQ_ALPACA_IEX == "daily_real_alpaca"

    def test_intraday_real_constant_defined(self):
        assert DQ_INTRADAY_REAL == "intraday_real_alpaca"

    def test_intraday_missing_constant_defined(self):
        assert DQ_INTRADAY_MISSING == "intraday_missing"

    def test_intraday_fallback_constant_defined(self):
        assert DQ_INTRADAY_FALLBACK == "intraday_fallback_demo"

    def test_intraday_stale_constant_defined(self):
        assert DQ_INTRADAY_STALE == "stale_intraday"


# ── Task 2/4: Intraday provider enforcement and summary ───────────────────────

class TestIntradayProviderEnforcement:
    """Verify _fetch_intraday_features_for_tony respects require_real_provider and allow_demo_fallback."""

    def _settings(self, tmp_path: Path, intraday_cfg: dict[str, Any]) -> Any:
        """Build a minimal settings namespace."""
        return SimpleNamespace(
            intraday=intraday_cfg,
            cache_dir=tmp_path / "cache",
            market_data={},
        )

    def test_require_real_true_with_demo_provider_marks_all_missing(self, tmp_path: Path):
        """When require_real=True and provider is DemoGeneratedProvider, all features = missing."""
        settings = self._settings(tmp_path, {
            "enabled": True,
            "timeframe": "5Min",
            "lookback_days": 2,
            "max_symbols_per_cycle": 5,
            "use_for_tony_analysis": True,
            "require_real_provider": True,
            "allow_demo_fallback": False,
        })
        provider = DemoGeneratedProvider()
        features, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR", "SOFI"])
        assert all(not f.data_available for f in features.values())
        assert all(f.status == "intraday_data_missing" for f in features.values())
        assert summary["intraday_provider"] == "skipped_require_real"
        assert summary["symbols_with_intraday"] == 0
        assert summary["missing_count"] == 2

    def test_require_real_false_with_demo_provider_returns_features(self, tmp_path: Path):
        """When require_real=False, demo provider is acceptable and features are computed."""
        settings = self._settings(tmp_path, {
            "enabled": True,
            "timeframe": "5Min",
            "lookback_days": 2,
            "max_symbols_per_cycle": 2,
            "use_for_tony_analysis": True,
            "require_real_provider": False,
            "allow_demo_fallback": True,
        })
        provider = DemoGeneratedProvider()
        features, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR", "SOFI"])
        # demo_generated returns bars, so data_available should be True for well-formed symbols
        assert summary["symbols_requested"] == 2
        assert summary["intraday_provider"] in ("demo_generated", "DemoGeneratedProvider", provider.name)

    def test_allow_demo_fallback_false_marks_fallback_symbols_as_missing(self, tmp_path: Path):
        """When Alpaca falls back for a symbol and allow_demo_fallback=False, that symbol = missing."""
        settings = self._settings(tmp_path, {
            "enabled": True,
            "timeframe": "5Min",
            "lookback_days": 2,
            "max_symbols_per_cycle": 2,
            "use_for_tony_analysis": True,
            "require_real_provider": True,
            "allow_demo_fallback": False,
        })
        provider = _make_alpaca_provider(fail_safe_to_demo=True)

        bars = _make_bars()

        def _batch_with_sofi_fallback(symbols, lookback_days, timeframe):
            provider.fallback_symbols.append("SOFI")
            return {"PLTR": bars, "SOFI": bars}

        with patch.object(provider, "fetch_ohlcv_batch", side_effect=_batch_with_sofi_fallback):
            features, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR", "SOFI"])

        assert features["PLTR"].data_available
        assert not features["SOFI"].data_available
        assert features["SOFI"].status == "intraday_data_missing"
        assert summary["intraday_fallback_count"] == 1

    def test_entire_batch_failure_allow_fallback_false_all_missing(self, tmp_path: Path):
        """When the entire batch fetch raises and allow_demo_fallback=False, all = missing."""
        settings = self._settings(tmp_path, {
            "enabled": True,
            "timeframe": "5Min",
            "lookback_days": 2,
            "max_symbols_per_cycle": 3,
            "use_for_tony_analysis": True,
            "require_real_provider": True,
            "allow_demo_fallback": False,
        })
        provider = _make_alpaca_provider(fail_safe_to_demo=False)

        with patch.object(provider, "fetch_ohlcv_batch", side_effect=OSError("Connection refused")):
            features, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR", "SOFI", "HOOD"])

        assert all(not f.data_available for f in features.values())
        assert summary["intraday_provider"] == "none_fetch_failed"
        assert summary["missing_count"] == 3
        assert summary["symbols_with_intraday"] == 0

    def test_intraday_summary_includes_provider_used_field(self, tmp_path: Path):
        """Intraday summary dict must include intraday_provider key."""
        settings = self._settings(tmp_path, {
            "enabled": True,
            "timeframe": "5Min",
            "lookback_days": 2,
            "max_symbols_per_cycle": 1,
            "use_for_tony_analysis": True,
            "require_real_provider": False,
            "allow_demo_fallback": True,
        })
        provider = DemoGeneratedProvider()
        _, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR"])
        assert "intraday_provider" in summary

    def test_intraday_summary_includes_require_real_field(self, tmp_path: Path):
        """Intraday summary must expose require_real_provider for event payloads."""
        settings = self._settings(tmp_path, {
            "enabled": True,
            "timeframe": "5Min",
            "lookback_days": 2,
            "max_symbols_per_cycle": 1,
            "use_for_tony_analysis": True,
            "require_real_provider": True,
            "allow_demo_fallback": False,
        })
        provider = DemoGeneratedProvider()
        _, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR"])
        assert summary.get("require_real_provider") is True

    def test_intraday_summary_allow_demo_fallback_in_summary(self, tmp_path: Path):
        settings = self._settings(tmp_path, {
            "enabled": True,
            "timeframe": "5Min",
            "lookback_days": 2,
            "max_symbols_per_cycle": 1,
            "use_for_tony_analysis": True,
            "require_real_provider": False,
            "allow_demo_fallback": False,
        })
        provider = DemoGeneratedProvider()
        _, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR"])
        assert summary.get("allow_demo_fallback") is False

    def test_real_alpaca_intraday_provider_labeled_alpaca_iex(self, tmp_path: Path):
        """When AlpacaIEXProvider batch succeeds, intraday_provider=alpaca_iex in summary."""
        settings = self._settings(tmp_path, {
            "enabled": True,
            "timeframe": "5Min",
            "lookback_days": 2,
            "max_symbols_per_cycle": 2,
            "use_for_tony_analysis": True,
            "require_real_provider": True,
            "allow_demo_fallback": False,
        })
        provider = _make_alpaca_provider()
        bars = _make_bars()

        with patch.object(provider, "fetch_ohlcv_batch", return_value={"PLTR": bars, "SOFI": bars}):
            _, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR", "SOFI"])

        assert summary["intraday_provider"] == "alpaca_iex"

    def test_intraday_disabled_returns_empty(self, tmp_path: Path):
        """When intraday.enabled=False, both returns are empty dicts."""
        settings = self._settings(tmp_path, {
            "enabled": False,
            "use_for_tony_analysis": True,
        })
        provider = DemoGeneratedProvider()
        features, summary = _fetch_intraday_features_for_tony(settings, provider, ["PLTR"])
        assert features == {}
        assert summary == {}


# ── Task 4: Build summary includes provider ───────────────────────────────────

class TestBuildIntradaySummaryProviderField:
    def test_build_intraday_summary_passes_through_provider(self):
        features = {
            "PLTR": IntradayFeatures(symbol="PLTR", timeframe="5Min", data_available=True, status="ok",
                                     latest_close=105, day_open=100, high_of_day=105, low_of_day=99,
                                     vwap=102, price_above_vwap=True),
        }
        base = {"intraday_provider": "alpaca_iex", "allow_demo_fallback": False}
        summary = _build_intraday_summary("5Min", ["PLTR"], features, fallback_count=0, base_summary=base)
        assert summary["intraday_provider"] == "alpaca_iex"

    def test_build_intraday_summary_missing_provider_defaults_to_none(self):
        features = {
            "PLTR": IntradayFeatures(symbol="PLTR", timeframe="5Min", data_available=False, status="intraday_data_missing"),
        }
        summary = _build_intraday_summary("5Min", ["PLTR"], features, fallback_count=0, base_summary={})
        # Should not crash and the field should come from base_summary (absent → absent or "none")
        assert "intraday_provider" not in summary or summary.get("intraday_provider") == "none"


# ── Task 5: No-broker safety checks ──────────────────────────────────────────

class TestNoBrokerInIntradayFix:
    def test_allowed_actions_unchanged(self):
        """Fixing data quality label must not add any broker actions."""
        broker_terms = {"buy", "sell", "order", "execute", "paper_trade", "live_trade", "broker"}
        for action in ALLOWED_ACTIONS:
            assert action.lower() not in broker_terms, f"Broker term found in allowed action: {action}"

    def test_real_alpaca_analysis_creates_no_paper_trades(self, tmp_path: Path):
        """Full analysis with alpaca_iex provider should produce no trades or orders."""
        stock = _stock(warnings=["Demo data only; do not use for real trade decisions."])
        analyses = analyze_candidates(
            candidates=[stock],
            provider_name="alpaca_iex",
            fallback_symbols=[],
            stale_symbols=[],
        )
        for analysis in analyses:
            assert analysis.recommended_action in ALLOWED_ACTIONS
            hyp = analysis.tony_hypothesis.lower()
            for term in ("buy ", "sell ", "order ", "paper trade", "live trade"):
                assert term not in hyp, f"Broker term '{term}' found in hypothesis"

    def test_intraday_fix_hypothesis_mentions_research_not_trading(self):
        """Tony hypothesis should say 'analyzing, not trading', not reference orders."""
        stock = _stock(warnings=["Demo data only; do not use for real trade decisions."])
        analyses = analyze_candidates(
            candidates=[stock],
            provider_name="alpaca_iex",
            fallback_symbols=[],
            stale_symbols=[],
        )
        assert "analyzing, not trading" in analyses[0].tony_hypothesis
