"""Tests for vault/writer.py — daily notes, ticker pages, vault index."""
from __future__ import annotations

from pathlib import Path

import pytest

from trading_bot.vault.writer import update_vault_index, upsert_ticker_page, write_daily_note


def _minimal_eod_result() -> dict:
    return {
        "report_date": "2026-05-22",
        "scan_coverage": {
            "universe_size": 349,
            "scored_count": 12,
            "coverage_pct": 3.4,
            "cycles_completed": 2,
            "real_data_count": 10,
        },
        "signal_scorecard": {},
        "terminal_outcome_summary": {
            "target_hits": 1,
            "stop_hits": 0,
            "active_count": 3,
            "avg_terminal_pl": 2.1,
        },
        "tony_self_review": {
            "strongest_setup": "Breakout Watch",
            "weakest_setup": "Pullback Watch",
            "rule_suggestions": [
                {"confidence": "medium", "suggestion": "Prioritize Breakout Watch"},
            ],
        },
        "strategy_version_report": {"current_version": "v1"},
        "rotation_diagnostics": {
            "unique_symbols_scanned": 12,
            "fresh_discoveries": 5,
            "repeat_scans": 7,
            "universe_coverage_pct": 3.4,
        },
        "skip_reasons": {"not_enough_bars": 5, "avg_volume_below_minimum": 3},
    }


def _snapshots() -> list[dict]:
    return [
        {
            "symbol": "GTLB",
            "score": 87,
            "setup_category": "Breakout Watch",
            "status": "active",
            "days_active": 4,
            "latest_close": 58.20,
            "target_price": 63.50,
            "stop_price": 55.80,
        },
        {
            "symbol": "ZETA",
            "score": 82,
            "setup_category": "Momentum Continuation",
            "status": "waiting_alert",
            "days_active": 3,
            "latest_close": 18.10,
            "target_price": 20.50,
            "stop_price": 16.80,
        },
    ]


class TestWriteDailyNote:
    def test_creates_file(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        assert (tmp_path / "daily" / "2026-05-22.md").exists()

    def test_frontmatter_fields(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "date: 2026-05-22" in content
        assert "tags: [daily, eod]" in content
        assert "strategy_version: v1" in content
        assert "universe_size: 349" in content
        assert "scored_count: 12" in content

    def test_ten_sections_present(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        for n in range(1, 11):
            assert f"## {n}." in content

    def test_snapshots_in_scored_table(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "GTLB" in content
        assert "ZETA" in content

    def test_skip_reasons_section(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "not_enough_bars" in content

    def test_wikilinks_in_scored_table(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "[[GTLB]]" in content

    def test_nav_links(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path)
        content = (tmp_path / "daily" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "[[index]]" in content

    def test_idempotent_overwrite(self, tmp_path):
        eod = _minimal_eod_result()
        write_daily_note("2026-05-22", eod, tmp_path)
        write_daily_note("2026-05-22", eod, tmp_path)
        assert len(list((tmp_path / "daily").iterdir())) == 1

    def test_missing_optional_keys_no_crash(self, tmp_path):
        write_daily_note("2026-05-22", {"report_date": "2026-05-22"}, tmp_path)
        assert (tmp_path / "daily" / "2026-05-22.md").exists()

    def test_no_snapshots_no_crash(self, tmp_path):
        write_daily_note("2026-05-22", _minimal_eod_result(), tmp_path, snapshots=[])
        assert (tmp_path / "daily" / "2026-05-22.md").exists()


class TestUpsertTickerPage:
    def _snap(self, **kwargs) -> dict:
        base = {"symbol": "GTLB", "score": 87, "setup_category": "Breakout Watch",
                "status": "active", "days_active": 4}
        return {**base, **kwargs}

    def test_creates_file_on_first_call(self, tmp_path):
        upsert_ticker_page("2026-05-22", self._snap(), tmp_path)
        assert (tmp_path / "signals" / "GTLB.md").exists()

    def test_frontmatter_ticker_field(self, tmp_path):
        upsert_ticker_page("2026-05-22", self._snap(), tmp_path)
        content = (tmp_path / "signals" / "GTLB.md").read_text(encoding="utf-8")
        assert "ticker: GTLB" in content
        assert "first_seen: 2026-05-22" in content

    def test_signal_history_row_appended(self, tmp_path):
        upsert_ticker_page("2026-05-22", self._snap(), tmp_path)
        upsert_ticker_page("2026-05-23", self._snap(score=89, days_active=5), tmp_path)
        content = (tmp_path / "signals" / "GTLB.md").read_text(encoding="utf-8")
        assert "2026-05-22" in content
        assert "2026-05-23" in content
        assert content.count("| [[2026-05-") == 2

    def test_no_duplicate_row_on_same_date(self, tmp_path):
        snap = self._snap()
        upsert_ticker_page("2026-05-22", snap, tmp_path)
        upsert_ticker_page("2026-05-22", snap, tmp_path)
        content = (tmp_path / "signals" / "GTLB.md").read_text(encoding="utf-8")
        assert content.count("| [[2026-05-22]]") == 1


class TestUpdateVaultIndex:
    def test_creates_index(self, tmp_path):
        update_vault_index("2026-05-22", [], tmp_path)
        assert (tmp_path / "index.md").exists()

    def test_index_links_to_daily(self, tmp_path):
        update_vault_index("2026-05-22", [], tmp_path)
        content = (tmp_path / "index.md").read_text(encoding="utf-8")
        assert "[[daily/2026-05-22]]" in content

    def test_index_lists_active_snapshots(self, tmp_path):
        snapshots = [
            {"symbol": "GTLB", "status": "active", "score": 87},
            {"symbol": "ZETA", "status": "active", "score": 82},
            {"symbol": "CVS", "status": "closed", "score": 71},
        ]
        update_vault_index("2026-05-22", snapshots, tmp_path)
        content = (tmp_path / "index.md").read_text(encoding="utf-8")
        assert "GTLB" in content
        assert "ZETA" in content
        assert "CVS" not in content
