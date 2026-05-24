"""Tests for near_entry and stop_violation event detection in PriceCache."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import patch

import pandas as pd

from trading_bot.storage.database import initialize_database


def _make_cache(tmp_path, monkeypatch):
    from trading_bot.api.live_prices import PriceCache
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "secret")
    db = tmp_path / "test.db"
    initialize_database(str(db))
    cache = PriceCache(str(db))
    q = asyncio.Queue()
    cache.set_event_queue(q)
    return cache, q


def _quote(symbol: str, price: float):
    from trading_bot.api.live_prices import LiveQuote
    return LiveQuote(
        symbol=symbol, price=price, bid=None, ask=None,
        prev_close=price - 1.0, change_pct=0.01,
        day_open=price - 0.5, day_high=price + 1.0, day_low=price - 1.0,
        day_volume=1_000_000, asof=datetime.now(timezone.utc), is_live=True,
    )


def _snapshot_df(*, symbol="AAPL", entry=100.0, stop=95.0, target=110.0,
                 entry_triggered=False, outcome_label=None, snap_id=1):
    return pd.DataFrame([{
        "id": snap_id, "symbol": symbol,
        "entry": entry, "stop": stop, "target": target,
        "entry_triggered": entry_triggered,
        "outcome_label": outcome_label,
    }])


def test_near_entry_fires_on_crossing(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)
    cache._previous_prices = {"AAPL": 101.0}   # was outside 0.5%

    with patch.object(ScannerRepository, "list_candidate_snapshots",
                      return_value=_snapshot_df(entry=100.0)):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 100.3)}))

    assert not q.empty()
    evt = q.get_nowait()
    assert evt["alert_type"] == "near_entry"
    assert evt["symbol"] == "AAPL"
    assert evt["entry"] == 100.0


def test_near_entry_does_not_fire_when_already_inside(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)
    cache._previous_prices = {"AAPL": 100.2}

    with patch.object(ScannerRepository, "list_candidate_snapshots",
                      return_value=_snapshot_df(entry=100.0)):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 100.3)}))

    assert q.empty()


def test_near_entry_cooldown_prevents_spam(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)
    cache._previous_prices = {"AAPL": 101.0}
    cache._near_entry_cooldown["AAPL"] = datetime.now(timezone.utc)

    with patch.object(ScannerRepository, "list_candidate_snapshots",
                      return_value=_snapshot_df(entry=100.0)):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 100.3)}))

    assert q.empty()


def test_near_entry_skips_triggered_snapshots(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)
    cache._previous_prices = {"AAPL": 101.0}

    with patch.object(ScannerRepository, "list_candidate_snapshots",
                      return_value=_snapshot_df(entry=100.0, entry_triggered=True)):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 100.3)}))

    assert q.empty()


def test_stop_violation_fires_once(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)

    df = _snapshot_df(entry=100.0, stop=95.0, entry_triggered=True, outcome_label=None, snap_id=42)

    with patch.object(ScannerRepository, "list_candidate_snapshots", return_value=df):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 94.0)}))

    assert not q.empty()
    evt = q.get_nowait()
    assert evt["alert_type"] == "stop_violation"
    assert evt["symbol"] == "AAPL"

    with patch.object(ScannerRepository, "list_candidate_snapshots", return_value=df):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 93.0)}))

    assert q.empty()


def test_stop_violation_skips_closed_outcomes(tmp_path, monkeypatch):
    from trading_bot.storage.repositories import ScannerRepository
    cache, q = _make_cache(tmp_path, monkeypatch)

    df = _snapshot_df(entry=100.0, stop=95.0, entry_triggered=True,
                      outcome_label="target_hit", snap_id=7)

    with patch.object(ScannerRepository, "list_candidate_snapshots", return_value=df):
        asyncio.run(cache._detect_events({"AAPL": _quote("AAPL", 94.0)}))

    assert q.empty()
