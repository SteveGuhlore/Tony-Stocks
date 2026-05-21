"""V15.2 symbol quarantine tests — no live API, no demo provider."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from trading_bot.data.symbol_quarantine import (
    apply_symbol_quarantine,
    load_symbol_quarantine_config,
    quarantine_active,
)
from trading_bot.data.universe import load_universe
from trading_bot.settings import load_scanner_settings
from tests.test_database import sample_scored_stock


@pytest.fixture
def quarantine_config_path(tmp_path: Path) -> Path:
    universe = tmp_path / "universe.yaml"
    universe.write_text(
        """
symbols:
  - symbol: PLTR
    name: Palantir
    tags: [software]
    sector: technology
    universe_role: primary_candidate
  - symbol: HCP
    name: HashiCorp
    tags: [software]
    sector: technology
    universe_role: primary_candidate
  - symbol: SQ
    name: Block
    tags: [fintech]
    sector: financials
    universe_role: primary_candidate
""",
        encoding="utf-8",
    )
    config = tmp_path / "default_config.yaml"
    config.write_text(
        f"""
provider: alpaca_iex
real_data_only: true
database_path: {(tmp_path / "db").as_posix()}
outputs_dir: {(tmp_path / "outputs").as_posix()}
cache_dir: {(tmp_path / "cache").as_posix()}
log_dir: {(tmp_path / "logs").as_posix()}
universe_config_path: {universe.as_posix()}
symbol_quarantine:
  enabled: true
  apply_during_real_data_only: true
  symbols:
    - symbol: HCP
      reason: test quarantine HCP
    - symbol: SQ
      reason: test quarantine SQ
  replacement_symbols: []
""",
        encoding="utf-8",
    )
    return config


def test_quarantine_active_only_when_real_data_only(quarantine_config_path: Path) -> None:
    settings = load_scanner_settings(quarantine_config_path)
    assert quarantine_active(settings, True) is True
    assert quarantine_active(settings, False) is False


def test_apply_quarantine_filters_known_symbols(quarantine_config_path: Path) -> None:
    settings = load_scanner_settings(quarantine_config_path)
    kept, excluded = apply_symbol_quarantine(["PLTR", "HCP", "SQ", "SOFI"], settings, True)
    assert kept == ["PLTR", "SOFI"]
    assert {entry.symbol for entry in excluded} == {"HCP", "SQ"}
    assert all(entry.reason for entry in excluded)


def test_universe_yaml_still_contains_quarantined_symbols(quarantine_config_path: Path) -> None:
    settings = load_scanner_settings(quarantine_config_path)
    symbols = load_universe(settings.universe_config_path)
    assert "HCP" in symbols
    assert "SQ" in symbols


def test_quarantine_disabled_keeps_all_symbols(quarantine_config_path: Path) -> None:
    disabled_path = quarantine_config_path.parent / "disabled_config.yaml"
    disabled_path.write_text(
        quarantine_config_path.read_text(encoding="utf-8").replace("enabled: true", "enabled: false"),
        encoding="utf-8",
    )
    settings = load_scanner_settings(disabled_path)
    kept, excluded = apply_symbol_quarantine(["HCP", "SQ"], settings, True)
    assert kept == ["HCP", "SQ"]
    assert excluded == []


def test_real_scan_excludes_quarantined_from_scoring(quarantine_config_path: Path, tmp_path: Path) -> None:
    """Quarantined symbols must not be passed to provider fetch when real_data_only."""
    settings = load_scanner_settings(quarantine_config_path)
    fetched: list[str] = []

    class FakeProvider:
        name = "alpaca_iex"
        fallback_symbols: list[str] = []
        missing_symbols: list[str] = []
        stale_symbols: list[str] = []
        batch_requests_enabled = False

        def reset_cycle_state(self) -> None:
            return None

        def fetch_ohlcv(self, symbol: str, lookback_days: int, timeframe: str = "daily"):
            fetched.append(symbol.upper())
            import pandas as pd

            idx = pd.date_range("2024-01-01", periods=80, freq="B")
            return pd.DataFrame(
                {
                    "open": [50.0] * 80,
                    "high": [51.0] * 80,
                    "low": [49.0] * 80,
                    "close": [50.0] * 80,
                    "volume": [2_000_000] * 80,
                },
                index=idx,
            )

        def get_cycle_stats(self) -> dict:
            return {}

    with patch("trading_bot.cli.build_market_data_provider", return_value=FakeProvider()), patch(
        "trading_bot.cli.ScoreEngine"
    ) as score_engine_cls, patch("trading_bot.cli.TonyStocksService") as tony_cls, patch(
        "trading_bot.cli.ScannerRepository"
    ) as repo_cls:
        repo_cls.return_value.create_scan_run.return_value = 1
        repo_cls.return_value.save_scan_results.return_value = None
        score_engine_cls.return_value.score.side_effect = lambda symbol, *a, **k: sample_scored_stock(symbol)
        tony_cls.return_value.enabled = False
        tony_cls.return_value.start_cycle.return_value = None
        from trading_bot.cli import run_scan

        run_scan(
            SimpleNamespace(
                config=str(quarantine_config_path),
                symbols="",
                save_snapshots=False,
            )
        )

    assert "HCP" not in fetched
    assert "SQ" not in fetched
    assert "PLTR" in fetched


def test_configured_quarantine_lists_hcp_smar_samsf_sq() -> None:
    settings = load_scanner_settings("config/default_config.yaml")
    cfg = load_symbol_quarantine_config(settings)
    symbols = set(cfg.symbols)
    assert {"HCP", "SAMSF", "SMAR", "SQ"}.issubset(symbols)


def test_no_broker_fields_in_quarantine_module() -> None:
    import trading_bot.data.symbol_quarantine as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "place_order" not in source
    assert "live_trading" not in source
    assert "demo_generated" not in source
