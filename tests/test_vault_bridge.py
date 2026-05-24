"""Tests for vault/bridge.py — analyst brief export to Command Center."""
from __future__ import annotations

from pathlib import Path

import pytest

from trading_bot.vault.bridge import _build_sector_etf_snapshot, _detect_clusters, write_bridge_export


def _eod_result() -> dict:
    return {
        "report_date": "2026-05-22",
        "scan_coverage": {"universe_size": 349, "scored_count": 175, "coverage_pct": 50.1, "cycles_completed": 12},
        "strategy_version_report": {"current_version": "v1"},
        "tony_self_review": {
            "rule_suggestions": [{"confidence": "medium", "suggestion": "Prioritize Breakout Watch"}],
        },
        "terminal_outcome_summary": {"active_count": 7},
        "signal_scorecard": {
            "Breakout Watch": {"triggered": 14, "target_rate": 0.64, "stop_rate": 0.21},
        },
        "outcomes_since_last_brief": [
            {"symbol": "ORCL", "result": "target_hit", "entry_date": "2026-05-20",
             "days_held": 2, "pl_pct": 4.2},
        ],
    }


def _snapshots() -> list[dict]:
    return [
        {"symbol": "GTLB", "score": 87, "setup_category": "Breakout Watch",
         "status": "active", "days_active": 4,
         "latest_close": 58.20, "target_price": 63.50, "stop_price": 55.80},
        {"symbol": "ZETA", "score": 82, "setup_category": "Momentum Continuation",
         "status": "waiting_alert", "days_active": 3,
         "latest_close": 18.10, "target_price": 20.50, "stop_price": 16.80},
        {"symbol": "CVS", "score": 71, "setup_category": "Breakout Watch",
         "status": "waiting", "days_active": 2,
         "latest_close": 62.10, "target_price": 67.20, "stop_price": 58.90},
        {"symbol": "ANET", "score": 61, "setup_category": "Breakout Watch",
         "status": "watching", "days_active": 1,
         "latest_close": 312.40, "target_price": 340.0, "stop_price": 298.0},
        {"symbol": "XLK", "score": 72, "setup_category": "Breakout Watch",
         "status": "watching", "days_active": 1,
         "latest_close": 200.0, "target_price": None, "stop_price": None},
    ]


class TestWriteBridgeExport:
    def test_creates_file(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        assert (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").exists()

    def test_frontmatter_present(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "date: 2026-05-22" in content
        assert "source: TradingBotAgentProject" in content
        assert "export_type: eod-bridge" in content

    def test_tier1_block_present(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Tier 1" in content
        assert "GTLB" in content
        assert "ZETA" in content

    def test_tier2_table_present(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Tier 2" in content
        assert "CVS" in content

    def test_tier3_present(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Tier 3" in content
        assert "ANET" in content

    def test_outcomes_section(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Outcomes Since Last Brief" in content
        assert "ORCL" in content

    def test_scorecard_section(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Signal Scorecard" in content
        assert "Breakout Watch" in content

    def test_rule_suggestions_section(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## Rule Suggestions" in content
        assert "medium" in content

    def test_for_tony_section(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=_snapshots())
        content = (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").read_text(encoding="utf-8")
        assert "## For Tony" in content

    def test_empty_eod_no_crash(self, tmp_path):
        write_bridge_export("2026-05-22", {"report_date": "2026-05-22"}, tmp_path)
        assert (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").exists()

    def test_no_snapshots_no_crash(self, tmp_path):
        write_bridge_export("2026-05-22", _eod_result(), tmp_path, snapshots=[])
        assert (tmp_path / "bridge" / "tony-stocks" / "2026-05-22.md").exists()


class TestDetectClusters:
    def test_flags_cluster_of_three(self):
        snapshots = [
            {"symbol": "GTLB", "days_active": 4},
            {"symbol": "ANET", "days_active": 2},
            {"symbol": "CRM", "days_active": 1},
            {"symbol": "ORCL", "days_active": 3},
        ]
        clusters = _detect_clusters(snapshots, threshold=3)
        assert any(c["sector"] == "Technology" for c in clusters)

    def test_no_cluster_below_threshold(self):
        snapshots = [
            {"symbol": "GTLB", "days_active": 4},
            {"symbol": "XOM", "days_active": 2},
        ]
        clusters = _detect_clusters(snapshots, threshold=3)
        assert clusters == []


class TestBuildSectorEtfSnapshot:
    def test_returns_known_etfs(self):
        snapshots = [
            {"symbol": "XLK", "score": 72, "setup_category": "Breakout Watch"},
            {"symbol": "XLE", "score": 58, "setup_category": "Pullback Watch"},
        ]
        result = _build_sector_etf_snapshot(snapshots)
        etfs = [r["etf"] for r in result]
        assert "XLK" in etfs
        assert "XLE" in etfs

    def test_score_and_setup_carried(self):
        snapshots = [{"symbol": "XLK", "score": 72, "setup_category": "Breakout Watch"}]
        result = _build_sector_etf_snapshot(snapshots)
        xlk = next(r for r in result if r["etf"] == "XLK")
        assert xlk["score"] == 72
        assert xlk["setup"] == "Breakout Watch"
