"""Unit tests for the /api/cockpit pure assembler (no DB/network needed)."""
from __future__ import annotations

from types import SimpleNamespace

from trading_bot.api.routes.cockpit import build_cockpit_rows


def _pick(score, verdict, reasoning="why", returned_at="2026-06-07T00:00:00Z"):
    return SimpleNamespace(score=score, verdict=verdict, reasoning=reasoning, returned_at=returned_at)


def test_dedup_keeps_newest_row_per_symbol():
    snaps = [
        {"symbol": "NVDA", "entry": 183.0, "total_score": 91},   # newest (repo orders DESC)
        {"symbol": "NVDA", "entry": 180.0, "total_score": 70},   # older — dropped
    ]
    rows = build_cockpit_rows(snaps, {}, {}, {})
    assert len(rows) == 1
    assert rows[0].score == 91
    assert rows[0].entry == 183.0


def test_status_triggered_when_entry_triggered():
    snaps = [{"symbol": "HOOD", "entry": 60.0, "entry_triggered": 1}]
    rows = build_cockpit_rows(snaps, {}, {}, {"HOOD": {"price": 61.0, "change_pct": 3.4, "status": "live"}})
    assert rows[0].status == "triggered"
    assert rows[0].entry_triggered is True


def test_status_near_when_price_just_below_entry():
    # last 182.6 vs entry 183.0 → within 0.5% below → near
    snaps = [{"symbol": "NVDA", "entry": 183.0}]
    rows = build_cockpit_rows(snaps, {}, {}, {"NVDA": {"price": 182.6, "change_pct": 2.1, "status": "live"}})
    assert rows[0].status == "near"
    assert rows[0].distance_to_entry_pct is not None


def test_status_watching_when_far_from_entry():
    snaps = [{"symbol": "COIN", "entry": 318.0}]
    rows = build_cockpit_rows(snaps, {}, {}, {"COIN": {"price": 312.9, "change_pct": -1.2, "status": "live"}})
    assert rows[0].status == "watching"


def test_subscores_merged_from_scan_results():
    snaps = [{"symbol": "AMD", "entry": 165.0, "total_score": 82}]
    subs = {"AMD": {"trend_score": 74, "momentum_score": 62, "volume_score": 80, "risk_score": 50, "setup_quality_score": 84}}
    rows = build_cockpit_rows(snaps, subs, {}, {})
    assert rows[0].sub_scores.trend == 74
    assert rows[0].sub_scores.volume == 80
    assert rows[0].sub_scores.risk == 50


def test_tony_read_attached_with_score():
    snaps = [{"symbol": "NVDA", "entry": 183.0}]
    picks = {"NVDA": _pick(88.0, "reaffirm")}
    rows = build_cockpit_rows(snaps, {}, picks, {})
    assert rows[0].tony is not None
    assert rows[0].tony.score == 88.0
    assert rows[0].tony.verdict == "reaffirm"


def test_tony_none_when_no_pick():
    rows = build_cockpit_rows([{"symbol": "MU", "entry": 100.0}], {}, {}, {})
    assert rows[0].tony is None


def test_price_unavailable_degrades_safely():
    # No price entry → unavailable, no crash, last_price None
    rows = build_cockpit_rows([{"symbol": "MSTR", "entry": None}], {}, {}, {})
    assert rows[0].price_status == "unavailable"
    assert rows[0].last_price is None
    assert rows[0].status == "watching"


def test_nan_and_bad_values_coerced_to_none():
    snaps = [{"symbol": "X", "entry": "not-a-number", "total_score": float("nan"), "risk_reward": None}]
    rows = build_cockpit_rows(snaps, {}, {}, {})
    assert rows[0].entry is None
    assert rows[0].score is None
    assert rows[0].rr is None


def test_unknown_verdict_passed_through_as_string():
    # Codex #10: transport keeps unknown verdicts verbatim; frontend degrades.
    rows = build_cockpit_rows([{"symbol": "DAL", "entry": 48.0}], {}, {"DAL": _pick(76.0, "pass")}, {})
    assert rows[0].tony.verdict == "pass"
