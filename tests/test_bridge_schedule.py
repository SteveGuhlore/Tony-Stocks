"""Tests for intraday bridge scheduling + slot-tagged bridge filenames.

The bot drops intraday bridges so the Command Center can re-analyze Tony's picks
during the session, not just at EOD. Intraday slots use a timestamped filename
(YYYY-MM-DDTHHMM.md) so they never overwrite the canonical daily (EOD) file.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from trading_bot.vault.bridge import write_bridge_export
from trading_bot.vault.bridge_schedule import BRIDGE_CHECKPOINTS, due_bridge_slots

ET = ZoneInfo("America/New_York")


def _et(hour: int, minute: int, *, day: int = 2) -> datetime:
    # 2026-06-02 is a Tuesday (a trading day); 2026-06-06 is a Saturday.
    return datetime(2026, 6, day, hour, minute, tzinfo=ET)


class TestDueBridgeSlots:
    def test_checkpoint_labels_and_order(self):
        labels = [label for label, _ in BRIDGE_CHECKPOINTS]
        assert labels == ["1030", "1300", "1530", "eod"]

    def test_before_first_checkpoint_none_due(self):
        assert due_bridge_slots(_et(9, 45), set()) == []

    def test_after_open_checkpoint_due(self):
        assert due_bridge_slots(_et(10, 31), set()) == ["1030"]

    def test_exact_checkpoint_time_is_due(self):
        assert due_bridge_slots(_et(10, 30), set()) == ["1030"]

    def test_midday_returns_all_passed_not_emitted(self):
        assert due_bridge_slots(_et(13, 5), set()) == ["1030", "1300"]

    def test_already_emitted_excluded(self):
        assert due_bridge_slots(_et(13, 5), {"1030"}) == ["1300"]

    def test_eod_due_after_close(self):
        assert due_bridge_slots(_et(16, 1), set()) == ["1030", "1300", "1530", "eod"]

    def test_all_emitted_returns_empty(self):
        assert due_bridge_slots(_et(16, 30), {"1030", "1300", "1530", "eod"}) == []

    def test_weekend_returns_empty(self):
        # 2026-06-06 is a Saturday.
        assert due_bridge_slots(_et(13, 0, day=6), set()) == []


def _eod_result() -> dict:
    return {
        "scan_coverage": {"universe_size": 100, "scored_count": 50, "coverage_pct": 50.0, "cycles_completed": 3},
        "strategy_version_report": {"current_version": "v1"},
        "terminal_outcome_summary": {"active_count": 2},
    }


def _snaps() -> list[dict]:
    return [{"symbol": "ZETA", "score": 80, "setup_category": "Breakout Watch",
             "status": "active", "days_active": 3, "latest_close": 18.0,
             "target_price": 20.0, "stop_price": 16.0}]


class TestSlotFilenames:
    def test_intraday_slot_uses_timestamped_filename(self, tmp_path):
        path = write_bridge_export("2026-06-02", _eod_result(), tmp_path, snapshots=_snaps(), slot="1030")
        assert path.name == "2026-06-02T1030.md"
        assert path.exists()

    def test_intraday_frontmatter_marks_export_type(self, tmp_path):
        path = write_bridge_export("2026-06-02", _eod_result(), tmp_path, snapshots=_snaps(), slot="1300")
        content = path.read_text(encoding="utf-8")
        assert "export_type: intraday-bridge" in content
        assert "slot: 1300" in content

    def test_eod_slot_uses_daily_filename(self, tmp_path):
        path = write_bridge_export("2026-06-02", _eod_result(), tmp_path, snapshots=_snaps(), slot="eod")
        assert path.name == "2026-06-02.md"
        assert "export_type: eod-bridge" in path.read_text(encoding="utf-8")

    def test_default_no_slot_is_daily_eod(self, tmp_path):
        path = write_bridge_export("2026-06-02", _eod_result(), tmp_path, snapshots=_snaps())
        assert path.name == "2026-06-02.md"
        assert "export_type: eod-bridge" in path.read_text(encoding="utf-8")
