"""Tests for the normalized paper equity curve (roadmap item 7 backend).

Pure + deterministic. Builds a realized-equity series from closed paper positions,
indexed to 100 at the baseline so unequal capital ($1M Tony vs $100k bot) compares as
a pure % return — the same normalization the Command Center curve uses. Research only.
"""
from __future__ import annotations

from trading_bot.analytics.equity_curve import build_paper_equity_curve


def _closed(symbol, closed_at, realized_pl):
    return {"symbol": symbol, "status": "closed", "closed_at": closed_at, "realized_pl": realized_pl}


def test_empty_history_has_no_points():
    curve = build_paper_equity_curve([], base_equity=100_000)
    assert curve.points == []
    assert curve.return_pct == 0.0
    d = curve.to_dict()
    assert d["label"] == "bot"
    assert d["points"] == []


def test_single_trade_indexes_to_baseline_then_gain():
    curve = build_paper_equity_curve(
        [_closed("AAA", "2026-06-04T15:00:00Z", 1400.0)], base_equity=100_000
    )
    # baseline point at 100, then +1.4% after the realized gain
    assert curve.points[0].index == 100.0
    assert curve.points[-1].index == 101.4
    assert curve.points[-1].equity == 101_400.0
    assert curve.return_pct == 1.4


def test_cumulative_and_sorted_by_close_time():
    rows = [
        _closed("BBB", "2026-06-04T16:00:00Z", -500.0),   # later
        _closed("AAA", "2026-06-04T15:00:00Z", 1000.0),   # earlier
    ]
    curve = build_paper_equity_curve(rows, base_equity=100_000)
    # baseline + 2 trades = 3 points; applied in close-time order (gain then loss)
    idxs = [p.index for p in curve.points]
    assert idxs == [100.0, 101.0, 100.5]
    assert curve.return_pct == 0.5


def test_ignores_rows_without_close_time_or_realized():
    rows = [
        _closed("AAA", "2026-06-04T15:00:00Z", 1000.0),
        {"symbol": "OPEN", "status": "open", "realized_pl": None, "closed_at": None},
        {"symbol": "NOCLOSE", "realized_pl": 999.0, "closed_at": None},
    ]
    curve = build_paper_equity_curve(rows, base_equity=100_000)
    assert len(curve.points) == 2  # baseline + the one valid closed trade
    assert curve.return_pct == 1.0


def test_label_is_carried_through():
    curve = build_paper_equity_curve([], base_equity=100_000, label="trading-bot")
    assert curve.label == "trading-bot"
    assert curve.to_dict()["label"] == "trading-bot"


def test_base_equity_scales_percent_not_absolute():
    # Same $ gain on a bigger book is a smaller % move.
    small = build_paper_equity_curve([_closed("A", "t1", 1000.0)], base_equity=100_000)
    big = build_paper_equity_curve([_closed("A", "t1", 1000.0)], base_equity=1_000_000)
    assert small.return_pct == 1.0
    assert big.return_pct == 0.1
