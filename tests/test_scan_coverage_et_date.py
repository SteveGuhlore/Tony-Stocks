"""Regression tests for scan-coverage ET-market-date bucketing (roadmap item 2).

Bug guarded: after-hours scans run past UTC midnight (e.g. 22:00 ET == 02:00 UTC the
next calendar day) must bucket into the *Eastern* market date, not the UTC date, so
the EOD report for that ET date does not show ``Universe:0/Scored:0``.

Both code paths the coverage builder relies on are exercised:
  * ``_events_on_date`` — filters today's tony_events (the scan_completed payloads)
  * the internal ``list_scan_runs`` filter — buckets scan runs for the scored fallback

Each must convert the stored UTC timestamp to America/New_York before comparing.
"""
from __future__ import annotations

import json

import pandas as pd

from trading_bot import cli

# 2026-06-04T02:00Z is 2026-06-03 22:00 in America/New_York (EDT, -04:00) — an
# after-hours scan whose UTC calendar date (06-04) differs from its ET date (06-03).
AFTER_HOURS_UTC = "2026-06-04T02:00:00Z"
ET_MARKET_DATE = "2026-06-03"


class _FakeSettings:
    universe_config_path = None  # _configured_universe_size -> None (percent stays None)


class _FakeRepo:
    """Minimal duck-typed repo: a single after-hours scan run + its scored results."""

    def __init__(self, scored_symbols: list[str]):
        self._scored = scored_symbols

    def list_scan_runs(self, limit: int = 500):
        return [{"id": 1, "created_at": AFTER_HOURS_UTC}]

    def list_scan_results_for_run_ids(self, run_ids):
        if not run_ids:
            return pd.DataFrame()
        return pd.DataFrame({"symbol": self._scored})


def test_events_on_date_buckets_after_hours_utc_into_et_date():
    events = pd.DataFrame(
        [{"created_at": AFTER_HOURS_UTC, "event_type": "scan_completed", "payload_json": "{}"}]
    )
    # Buckets into the ET date, not the UTC date.
    assert cli._events_on_date(events, ET_MARKET_DATE)  # non-empty -> included
    assert cli._events_on_date(events, "2026-06-04") == []  # the UTC date does NOT match


def test_scan_coverage_counts_after_hours_scan_for_et_date_via_events():
    payload = {
        "symbols_loaded": 10,
        "symbols_scored": 8,
        "selected_symbols": [f"S{i}" for i in range(10)],
        "scored_symbols": [f"S{i}" for i in range(8)],
    }
    events = pd.DataFrame(
        [{"created_at": AFTER_HOURS_UTC, "event_type": "scan_completed",
          "payload_json": json.dumps(payload)}]
    )
    today_events = cli._events_on_date(events, ET_MARKET_DATE)

    summary = cli._build_scan_coverage_summary(
        ET_MARKET_DATE, _FakeRepo(scored_symbols=[]), _FakeSettings(), today_events
    )
    # Not 0/0 — the after-hours scan is attributed to its ET market date.
    assert summary["unique_symbols_scanned_today"] == 10
    assert summary["unique_symbols_scored_today"] == 8


def test_scan_coverage_scan_runs_filter_uses_et_market_date():
    # No scan_completed events -> forces the scored fallback that reads scan_results
    # for run_ids bucketed by the internal ET scan-runs filter.
    scored = [f"S{i}" for i in range(8)]
    summary = cli._build_scan_coverage_summary(
        ET_MARKET_DATE, _FakeRepo(scored_symbols=scored), _FakeSettings(), today_events=[]
    )
    # The after-hours run (02:00 UTC = 22:00 ET prev day) is included for ET 06-03.
    assert summary["unique_symbols_scored_today"] == 8


def test_scan_coverage_excludes_run_from_wrong_et_date():
    # Same run, but the report asks for the UTC date (06-04) which is NOT its ET date.
    scored = [f"S{i}" for i in range(8)]
    summary = cli._build_scan_coverage_summary(
        "2026-06-04", _FakeRepo(scored_symbols=scored), _FakeSettings(), today_events=[]
    )
    # The run belongs to ET 06-03, so it must not leak into the 06-04 report.
    assert summary["unique_symbols_scored_today"] in (None, 0)
