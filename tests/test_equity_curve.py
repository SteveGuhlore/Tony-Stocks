"""Tests for the normalized paper equity curve (roadmap item 7 backend).

Pure + deterministic. Builds a realized-equity series from closed paper positions,
indexed to 100 at the baseline so unequal capital ($1M Tony vs $100k bot) compares as
a pure % return — the same normalization the Command Center curve uses. Research only.
"""
from __future__ import annotations

from trading_bot.analytics.equity_curve import (
    build_paper_equity_curve,
    open_positions_unrealized_pl,
)


def _closed(symbol, closed_at, realized_pl):
    return {"symbol": symbol, "status": "closed", "closed_at": closed_at, "realized_pl": realized_pl}


def _open(symbol, qty, entry_price):
    return {"symbol": symbol, "status": "open", "qty": qty, "entry_price": entry_price}


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


# --- head-to-head fairness: mark OPEN positions to live on the latest point only ---

def test_open_position_marked_up_raises_latest_point():
    closed = [_closed("AAA", "2026-06-04T15:00:00Z", 1000.0)]  # +1.0% realized
    open_pos = [_open("BBB", 100, 50.0)]  # 100 sh, fill 50
    base = build_paper_equity_curve(closed, base_equity=100_000)
    marked = build_paper_equity_curve(
        closed, base_equity=100_000, open_positions=open_pos, live_prices={"BBB": 60.0}
    )
    # unrealized = 100 * (60 - 50) = +1000 -> latest point gains another +1.0%
    assert marked.points[-1].equity == base.points[-1].equity + 1000.0
    assert marked.points[-1].index == 102.0
    assert marked.return_pct == 2.0
    # earlier points are untouched (only the latest is marked)
    assert marked.points[:-1] == base.points[:-1]


def test_open_position_marked_down_lowers_latest_point():
    closed = [_closed("AAA", "2026-06-04T15:00:00Z", 1000.0)]
    open_pos = [_open("BBB", 100, 50.0)]
    marked = build_paper_equity_curve(
        closed, base_equity=100_000, open_positions=open_pos, live_prices={"BBB": 45.0}
    )
    # unrealized = 100 * (45 - 50) = -500 -> 100_000 + 1000 - 500 = 100_500
    assert marked.points[-1].equity == 100_500.0
    assert marked.return_pct == 0.5


def test_no_live_prices_is_identical_to_realized_only():
    closed = [_closed("AAA", "2026-06-04T15:00:00Z", 1000.0)]
    open_pos = [_open("BBB", 100, 50.0)]
    realized = build_paper_equity_curve(closed, base_equity=100_000)
    none_prices = build_paper_equity_curve(
        closed, base_equity=100_000, open_positions=open_pos, live_prices=None
    )
    empty_prices = build_paper_equity_curve(
        closed, base_equity=100_000, open_positions=open_pos, live_prices={}
    )
    assert none_prices.points == realized.points
    assert empty_prices.points == realized.points
    assert none_prices.return_pct == realized.return_pct == 1.0


def test_closed_only_book_unchanged_even_with_prices():
    # No open positions -> nothing to mark, curve is the realized series.
    closed = [_closed("AAA", "2026-06-04T15:00:00Z", 1000.0)]
    realized = build_paper_equity_curve(closed, base_equity=100_000)
    marked = build_paper_equity_curve(
        closed, base_equity=100_000, open_positions=[], live_prices={"BBB": 999.0}
    )
    assert marked.points == realized.points
    assert marked.return_pct == 1.0


def test_open_symbol_without_live_price_contributes_zero():
    closed = [_closed("AAA", "2026-06-04T15:00:00Z", 1000.0)]
    open_pos = [_open("BBB", 100, 50.0), _open("CCC", 10, 20.0)]
    # only BBB is priced; CCC has no quote -> contributes 0
    marked = build_paper_equity_curve(
        closed, base_equity=100_000, open_positions=open_pos, live_prices={"BBB": 55.0}
    )
    assert marked.points[-1].equity == 100_000 + 1000 + 500.0


def test_unrealized_helper_sums_and_skips_unusable_rows():
    rows = [
        _open("BBB", 100, 50.0),                 # +1000 at 60
        _open("CCC", 10, 20.0),                  # no price -> 0
        {"symbol": "DDD", "qty": None, "entry_price": 10.0},  # bad qty -> 0
        {"symbol": "EEE", "qty": 5},             # no entry_price -> 0
    ]
    total = open_positions_unrealized_pl(rows, {"bbb": 60.0})  # case-insensitive symbols
    assert total == 1000.0
    assert open_positions_unrealized_pl(rows, None) == 0.0
    assert open_positions_unrealized_pl(rows, {}) == 0.0
