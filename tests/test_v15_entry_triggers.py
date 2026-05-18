"""V15 intraday entry trigger simulation tests — mocked bars only, no live API."""

from __future__ import annotations

import pandas as pd
import pytest

from trading_bot.intraday.features import IntradayFeatures
from trading_bot.snapshots.entry_triggers import (
    ENTRY_STATUS_MISSING_REAL_DATA,
    ENTRY_STATUS_NO_INTRADAY_TRIGGER,
    ENTRY_STATUS_PENDING,
    ENTRY_STATUS_TRIGGERED,
    RULE_BREAKOUT,
    compute_planned_entry_at_snapshot,
    simulate_entry_trigger,
)
from trading_bot.snapshots.followup import OUTCOME_ENTRY_NOT_TRIGGERED, calculate_snapshot_followup
from trading_bot.storage.repositories import ScannerRepository
from tests.test_database import sample_scored_stock


def _intraday_features(high: float = 102.0, vwap: float = 100.5, above_vwap: bool = True) -> IntradayFeatures:
    return IntradayFeatures(
        symbol="PLTR",
        timeframe="5Min",
        data_available=True,
        status="ok",
        latest_close=101.0,
        high_of_day=high,
        low_of_day=98.0,
        vwap=vwap,
        price_above_vwap=above_vwap,
    )


def _bars_5min(start: str, highs: list[float], lows: list[float] | None = None) -> pd.DataFrame:
    idx = pd.date_range(start, periods=len(highs), freq="5min")
    lows = lows or [h - 0.5 for h in highs]
    closes = [(h + l) / 2 for h, l in zip(highs, lows)]
    return pd.DataFrame(
        {"open": closes, "high": highs, "low": lows, "close": closes, "volume": [1000] * len(highs)},
        index=idx,
    )


def test_breakout_planned_entry_above_snapshot_price():
    plan = compute_planned_entry_at_snapshot(
        {"setup_category": "Breakout Watch", "close": 100.0, "intraday_close": 101.0},
        _intraday_features(high=102.0),
        None,
        default_buffer_pct=0.001,
    )
    assert plan.planned_entry_price is not None
    assert plan.planned_entry_price > plan.snapshot_price
    assert plan.planned_entry_rule == RULE_BREAKOUT
    assert plan.entry_status == ENTRY_STATUS_PENDING


def test_entry_no_longer_equals_close_at_snapshot():
    plan = compute_planned_entry_at_snapshot(
        {"setup_category": "Breakout Watch", "close": 100.0, "intraday_close": 100.0},
        _intraday_features(high=101.5),
        None,
        default_buffer_pct=0.001,
    )
    assert plan.snapshot_price == 100.0
    assert plan.planned_entry_price != plan.snapshot_price


def test_trigger_only_uses_bars_after_snapshot_time():
    snapshot_time = "2026-05-18T14:30:00"
    bars = _bars_5min("2026-05-18T14:25:00", [99.0, 99.5, 103.0, 104.0])
    snapshot = {
        "snapshot_time": snapshot_time,
        "snapshot_bar_time": snapshot_time,
        "planned_entry_price": 102.5,
        "entry_status": ENTRY_STATUS_PENDING,
    }
    result = simulate_entry_trigger(snapshot, bars, expire_after_trading_days=1)
    assert result.entry_status == ENTRY_STATUS_TRIGGERED
    assert result.actual_entry_time is not None
    assert pd.Timestamp(result.actual_entry_time) > pd.Timestamp(snapshot_time)


def test_no_lookahead_before_snapshot_time():
    snapshot_time = "2026-05-18T14:40:00"
    bars = _bars_5min("2026-05-18T14:25:00", [105.0, 105.0, 99.0, 99.0])
    snapshot = {
        "snapshot_time": snapshot_time,
        "planned_entry_price": 102.0,
        "entry_status": ENTRY_STATUS_PENDING,
    }
    result = simulate_entry_trigger(
        snapshot,
        bars,
        expire_after_trading_days=1,
        now=pd.Timestamp("2026-05-19T10:00:00"),
    )
    assert result.entry_status != ENTRY_STATUS_TRIGGERED
    assert result.actual_entry_time is None


def test_actual_entry_time_is_first_valid_trigger_bar():
    snapshot_time = "2026-05-18T14:30:00"
    bars = _bars_5min("2026-05-18T14:35:00", [101.0, 103.5, 104.0])
    snapshot = {
        "snapshot_time": snapshot_time,
        "planned_entry_price": 103.0,
        "entry_status": ENTRY_STATUS_PENDING,
    }
    result = simulate_entry_trigger(snapshot, bars, expire_after_trading_days=1)
    assert result.entry_status == ENTRY_STATUS_TRIGGERED
    assert result.actual_entry_time == pd.Timestamp("2026-05-18T14:40:00").isoformat()


def test_no_trigger_stays_pending_same_day():
    snapshot = {
        "snapshot_time": "2026-05-18T14:30:00",
        "planned_entry_price": 110.0,
        "entry_status": ENTRY_STATUS_PENDING,
    }
    bars = _bars_5min("2026-05-18T14:35:00", [101.0, 102.0])
    result = simulate_entry_trigger(
        snapshot,
        bars,
        expire_after_trading_days=2,
        now=pd.Timestamp("2026-05-18T16:00:00"),
    )
    assert result.entry_status == ENTRY_STATUS_PENDING
    assert not result.entry_triggered


def test_missing_real_data_does_not_create_fake_entry():
    plan = compute_planned_entry_at_snapshot(
        {"setup_category": "Breakout Watch", "close": 100.0},
        None,
        None,
        real_data_only=True,
        data_source="missing_real_data",
    )
    assert plan.entry_status == ENTRY_STATUS_MISSING_REAL_DATA
    assert plan.planned_entry_price is None
    result = simulate_entry_trigger(
        {"entry_status": ENTRY_STATUS_MISSING_REAL_DATA, "planned_entry_price": None},
        _bars_5min("2026-05-18T14:35:00", [120.0]),
    )
    assert not result.entry_triggered
    assert result.actual_entry_price is None


def test_no_intraday_context_marks_no_trigger():
    plan = compute_planned_entry_at_snapshot(
        {"setup_category": "Breakout Watch", "close": 100.0},
        IntradayFeatures(symbol="X", timeframe="5Min", data_available=False, status="intraday_data_missing"),
        None,
    )
    assert plan.entry_status == ENTRY_STATUS_NO_INTRADAY_TRIGGER


def test_legacy_snapshots_still_load(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "demo_generated", {"provider": "demo_generated"})
    created = repo.create_candidate_snapshots(
        run_id,
        [sample_scored_stock()],
        {"enabled": True, "min_score": 60, "include_roles": ["primary_candidate"], "include_categories": ["Breakout Watch"]},
    )
    row = repo.latest_candidate_snapshots().iloc[0]
    assert created
    assert row["symbol"] == "AAPL"
    assert row.get("planned_entry_price") is None or row["planned_entry_price"] == row.get("entry_trigger_price")


def test_followup_uses_actual_entry_time_after_trigger(tmp_path):
    snapshot = {
        "snapshot_time": "2026-01-01T00:00:00+00:00",
        "close": 100.0,
        "entry": 101.0,
        "stop": 95.0,
        "target": 110.0,
        "entry_status": "triggered",
        "actual_entry_time": "2026-01-03T00:00:00+00:00",
        "actual_entry_price": 102.0,
        "entry_triggered": 1,
    }
    daily = pd.DataFrame(
        {
            "open": [100, 101, 102, 111],
            "high": [100, 101, 102, 111],
            "low": [99, 100, 101, 110],
            "close": [100, 101, 102, 111],
            "volume": [1_000_000] * 4,
        },
        index=pd.bdate_range("2026-01-02", periods=4),
    )
    result = calculate_snapshot_followup(snapshot, daily)
    assert result.entry_triggered
    assert result.outcome_label != OUTCOME_ENTRY_NOT_TRIGGERED


def test_repository_stores_entry_trigger_fields(tmp_path):
    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    run_id = repo.create_scan_run(1, "alpaca_iex", {"provider": "alpaca_iex"})
    plan = compute_planned_entry_at_snapshot(
        {"setup_category": "Breakout Watch", "close": 100.0, "intraday_close": 101.0},
        _intraday_features(high=102.5),
        None,
    )
    repo.create_candidate_snapshots(
        run_id,
        [sample_scored_stock("PLTR")],
        {
            "enabled": True,
            "min_score": 60,
            "include_roles": ["primary_candidate"],
            "include_categories": ["Breakout Watch"],
        },
        entry_plans={"PLTR": plan.to_snapshot_fields()},
    )
    row = repo.latest_candidate_snapshots().iloc[0]
    assert row["snapshot_price"] == plan.snapshot_price
    assert row["planned_entry_price"] == plan.planned_entry_price
    assert row["planned_entry_rule"] == plan.planned_entry_rule
    assert row["entry_status"] == ENTRY_STATUS_PENDING


def test_tony_entry_trigger_summary_event(tmp_path):
    from trading_bot.tony.events import TonyStocksService

    db = tmp_path / "scanner.db"
    repo = ScannerRepository(db)
    tony = TonyStocksService(
        repo,
        {"enabled": True, "create_events_for": ["entry_trigger_summary"], "max_events_per_cycle": 10},
    )
    tony.record_entry_trigger_summary(
        {
            "planned_triggers": 3,
            "entry_triggered": 1,
            "pending_triggers": 2,
            "expired_no_trigger": 0,
            "missing_real_data_triggers": 0,
            "entry_status_counts": {"pending": 2, "triggered": 1},
        }
    )
    events = repo.list_tony_events(event_type="entry_trigger_summary", limit=5)
    assert len(events) == 1
    assert "Research-only" in events.iloc[0]["message"]


def test_no_broker_order_fields_in_snapshot_schema(tmp_path):
    db = tmp_path / "scanner.db"
    ScannerRepository(db)
    from trading_bot.storage.database import connect

    with connect(db) as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(candidate_snapshots)").fetchall()}
    forbidden = {"order_id", "broker_order", "paper_trade_id", "live_order"}
    assert forbidden.isdisjoint(columns)
    assert "planned_entry_price" in columns
    assert "entry_status" in columns
