"""Tests for build_resolved_outcome_records — assembles resolved tracked positions
from candidate snapshots into per-episode records feeding the Tony outcomes emitter.

Research only: reads snapshot history, computes terminal exit/PL from stored
stop/target levels. No trading.
"""
from __future__ import annotations

import pandas as pd

from trading_bot.analytics import build_resolved_outcome_records
from trading_bot.vault.outcomes_bridge import build_tony_outcomes


def _row(**kw):
    """One snapshot row with sensible non-terminal defaults; override per test."""
    base = {
        "symbol": "AAA",
        "snapshot_time": "2026-05-20T20:00:00+00:00",
        "entry_status": "pending",
        "outcome_label": "still_open",
        "tracking_status": "",  # empty => non-terminal (active)
        "original_entry_price": None,
        "original_target_price": None,
        "original_stop_price": None,
        "target": None,
        "stop": None,
        "current_price": None,
        "intraday_close": None,
        "close": None,
        "research_unrealized_pl_pct": None,
        "actual_entry_price": None,
        "actual_entry_time": None,
        "time_active_minutes": None,
        "last_checked_at": None,
    }
    base.update(kw)
    return base


def _df(rows):
    return pd.DataFrame(rows)


class TestBuildResolvedOutcomeRecords:
    def test_empty_df_returns_empty(self):
        assert build_resolved_outcome_records(_df([])) == []

    def test_active_only_symbol_excluded(self):
        rows = _df([
            _row(snapshot_time="2026-05-20T20:00:00+00:00"),
            _row(snapshot_time="2026-05-21T20:00:00+00:00", tracking_status="active"),
        ])
        assert build_resolved_outcome_records(rows) == []

    def test_single_resolved_position_one_record(self):
        rows = _df([
            _row(symbol="ZETA", snapshot_time="2026-05-20T20:00:00+00:00"),
            _row(symbol="ZETA", snapshot_time="2026-05-21T20:00:00+00:00"),
            _row(
                symbol="ZETA",
                snapshot_time="2026-05-22T20:00:00+00:00",
                tracking_status="target_hit",
                outcome_label="target_hit",
                original_entry_price=100.0,
                original_target_price=110.0,
                original_stop_price=95.0,
                actual_entry_time="2026-05-21T13:30:00",
                time_active_minutes=1440,
            ),
        ])
        out = build_resolved_outcome_records(rows)
        assert len(out) == 1
        rec = out[0]
        assert rec["symbol"] == "ZETA"
        assert rec["pick_date"] == "2026-05-20"  # day-1 of the episode
        assert rec["result"] == "target_hit"
        assert rec["entry"] == 100.0
        assert rec["exit"] == 110.0
        assert rec["return_pct"] == 10.0
        assert rec["entry_date"] == "2026-05-21"

    def test_stop_hit_exit_and_negative_pl(self):
        rows = _df([
            _row(symbol="SLB", snapshot_time="2026-05-22T20:00:00+00:00"),
            _row(
                symbol="SLB",
                snapshot_time="2026-05-26T20:00:00+00:00",
                tracking_status="stop_hit",
                outcome_label="stop_hit",
                original_entry_price=100.0,
                original_stop_price=95.0,
                original_target_price=110.0,
            ),
        ])
        rec = build_resolved_outcome_records(rows)[0]
        assert rec["result"] == "stop_hit"
        assert rec["exit"] == 95.0
        assert rec["return_pct"] == -5.0

    def test_consecutive_terminal_echoes_collapse_to_one(self):
        # A resolved position keeps reporting target_hit on later refresh rows.
        rows = _df([
            _row(symbol="ORCL", snapshot_time="2026-05-20T20:00:00+00:00"),
            _row(symbol="ORCL", snapshot_time="2026-05-21T20:00:00+00:00",
                 tracking_status="target_hit", outcome_label="target_hit",
                 original_entry_price=200.0, original_target_price=220.0),
            _row(symbol="ORCL", snapshot_time="2026-05-22T20:00:00+00:00",
                 tracking_status="target_hit", outcome_label="target_hit",
                 original_entry_price=200.0, original_target_price=220.0),
        ])
        out = build_resolved_outcome_records(rows)
        assert len(out) == 1
        assert out[0]["pick_date"] == "2026-05-20"

    def test_two_episodes_same_symbol_distinct_pick_dates(self):
        rows = _df([
            # Episode 1: picked 05-20, target 05-21
            _row(symbol="NVDA", snapshot_time="2026-05-20T20:00:00+00:00"),
            _row(symbol="NVDA", snapshot_time="2026-05-21T20:00:00+00:00",
                 tracking_status="target_hit", outcome_label="target_hit",
                 original_entry_price=100.0, original_target_price=110.0),
            # Episode 2: re-picked 05-28, stopped 05-29
            _row(symbol="NVDA", snapshot_time="2026-05-28T20:00:00+00:00"),
            _row(symbol="NVDA", snapshot_time="2026-05-29T20:00:00+00:00",
                 tracking_status="stop_hit", outcome_label="stop_hit",
                 original_entry_price=120.0, original_stop_price=114.0),
        ])
        out = sorted(build_resolved_outcome_records(rows), key=lambda r: r["pick_date"])
        assert len(out) == 2
        assert out[0]["pick_date"] == "2026-05-20"
        assert out[0]["result"] == "target_hit"
        assert out[1]["pick_date"] == "2026-05-28"
        assert out[1]["result"] == "stop_hit"

    def test_partial_move_normalizes_to_closed_via_emitter(self):
        rows = _df([
            _row(symbol="DKNG", snapshot_time="2026-05-20T20:00:00+00:00"),
            _row(symbol="DKNG", snapshot_time="2026-05-23T20:00:00+00:00",
                 tracking_status="partial_move", outcome_label="partial_move",
                 original_entry_price=40.0, current_price=42.0),
        ])
        records = build_resolved_outcome_records(rows)
        assert len(records) == 1
        emitted = build_tony_outcomes(records, eod_date="2026-05-30")
        assert emitted[0]["result"] == "closed"
        assert emitted[0]["pick_date"] == "2026-05-20"

    def test_days_held_from_time_active_minutes(self):
        rows = _df([
            _row(symbol="AAA", snapshot_time="2026-05-20T20:00:00+00:00"),
            _row(symbol="AAA", snapshot_time="2026-05-24T20:00:00+00:00",
                 tracking_status="stop_hit", outcome_label="stop_hit",
                 original_entry_price=10.0, original_stop_price=9.0,
                 time_active_minutes=5760),  # 4 days
        ])
        rec = build_resolved_outcome_records(rows)[0]
        assert rec["days_held"] == 4

    def test_records_feed_emitter_to_full_cc_schema(self):
        rows = _df([
            _row(symbol="ZETA", snapshot_time="2026-05-20T20:00:00+00:00"),
            _row(symbol="ZETA", snapshot_time="2026-05-22T20:00:00+00:00",
                 tracking_status="target_hit", outcome_label="target_hit",
                 original_entry_price=100.0, original_target_price=110.0,
                 actual_entry_time="2026-05-21T13:30:00", time_active_minutes=1440),
        ])
        emitted = build_tony_outcomes(build_resolved_outcome_records(rows), eod_date="2026-05-30")
        assert emitted == [
            {
                "symbol": "ZETA",
                "pick_date": "2026-05-20",
                "result": "target_hit",
                "entry": 100.0,
                "exit": 110.0,
                "return_pct": 10.0,
                "days_held": 1,
                "resolved_date": "2026-05-22",
            }
        ]
