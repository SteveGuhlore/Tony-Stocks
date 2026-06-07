"""Tests for off_hours config block loading.

The off-hours research engine is DEFAULT OFF. This test verifies:
- The default config loads correctly and off_hours is disabled.
- All required keys are present with correct types/values.
- The block can be loaded via a minimal YAML snippet.
"""
from __future__ import annotations

from trading_bot.settings import load_scanner_settings


def test_default_config_off_hours_disabled():
    """off_hours.enabled must be False in the default config (safety gate)."""
    s = load_scanner_settings("config/default_config.yaml")
    assert s.off_hours is not None
    assert s.off_hours["enabled"] is False


def test_default_config_off_hours_required_keys():
    """All required keys are present in the default off_hours block."""
    s = load_scanner_settings("config/default_config.yaml")
    block = s.off_hours
    assert "cadence_minutes" in block
    assert "earnings_blackout_days" in block
    assert "shortlist_size" in block
    assert "full_universe_scan" in block
    assert "premarket_provider" in block
    assert "enrich_budget" in block


def test_default_config_off_hours_premarket_provider_null():
    """premarket_provider must be the string 'null' by default (no live provider)."""
    s = load_scanner_settings("config/default_config.yaml")
    assert s.off_hours["premarket_provider"] == "null"


def test_off_hours_block_loads_from_yaml(tmp_path):
    """Minimal YAML with an off_hours block is loaded correctly."""
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "off_hours:\n"
        "  enabled: false\n"
        "  cadence_minutes: 30\n"
        "  earnings_blackout_days: 5\n"
        "  shortlist_size: 20\n"
        "  full_universe_scan: true\n"
        '  premarket_provider: "null"\n'
        "  enrich_budget: 25\n",
        encoding="utf-8",
    )
    s = load_scanner_settings(str(cfg))
    assert s.off_hours["enabled"] is False
    assert s.off_hours["cadence_minutes"] == 30
    assert s.off_hours["earnings_blackout_days"] == 5
    assert s.off_hours["shortlist_size"] == 20
    assert s.off_hours["full_universe_scan"] is True
    assert s.off_hours["premarket_provider"] == "null"
    assert s.off_hours["enrich_budget"] == 25
