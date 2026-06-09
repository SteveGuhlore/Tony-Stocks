"""Tests for analytics.equity_compare — indexing + common-window alignment."""
from __future__ import annotations

from trading_bot.analytics.equity_compare import align_common, build_account_curve


def test_build_account_curve_indexes_to_100():
    hist = {"timestamp": [1000, 2000, 3000], "equity": [100_000.0, 101_000.0, 99_000.0]}
    c = build_account_curve(hist, "Bot")
    assert c["label"] == "Bot"
    assert c["base_value"] == 100_000.0
    assert [round(p["index"], 1) for p in c["points"]] == [100.0, 101.0, 99.0]
    assert c["points"][0]["equity"] == c["points"][0]["index"]  # plotted value == index
    assert c["points"][0]["t"].startswith("1970-01-01T00:16:40")  # ts 1000 -> ISO UTC
    assert c["return_pct"] == -1.0  # last index 99.0 -> -1.0%


def test_build_account_curve_empty_safe():
    for bad in (None, {}, {"timestamp": [], "equity": []}, "nope"):
        c = build_account_curve(bad, "Tony")  # type: ignore[arg-type]
        assert c["points"] == []
        assert c["return_pct"] is None


def test_build_account_curve_drops_unfunded_leading_zeros():
    # Alpaca pads pre-funding days with equity 0 — they must be dropped, not indexed to 0.
    c = build_account_curve({"timestamp": [1, 2, 3, 4], "equity": [0.0, 0.0, 100.0, 110.0]}, "X")
    assert [p["ts"] for p in c["points"]] == [3, 4]  # zero days filtered
    assert c["base_value"] == 100.0
    assert [p["index"] for p in c["points"]] == [100.0, 110.0]
    assert c["return_pct"] == 10.0


def test_build_account_curve_all_zero_is_empty():
    c = build_account_curve({"timestamp": [1, 2], "equity": [0.0, 0.0]}, "X")
    assert c["points"] == [] and c["base_value"] is None


def test_align_common_trims_and_rebases_to_shared_start():
    # Bot has an extra earlier point (ts 1000) Tony lacks; common window starts at 2000.
    bot = build_account_curve({"timestamp": [1000, 2000, 3000], "equity": [90.0, 100.0, 110.0]}, "Bot")
    tony = build_account_curve({"timestamp": [2000, 3000], "equity": [50.0, 55.0]}, "Tony")
    abot, atony = align_common(bot, tony)
    # both trimmed to the 2 common timestamps and re-indexed to 100 at ts=2000
    assert [p["ts"] for p in abot["points"]] == [2000, 3000]
    assert [p["ts"] for p in atony["points"]] == [2000, 3000]
    assert abot["points"][0]["index"] == 100.0
    assert atony["points"][0]["index"] == 100.0
    # bot 100->110 = +10%, tony 50->55 = +10% over the shared window
    assert abot["return_pct"] == 10.0
    assert atony["return_pct"] == 10.0


def test_align_common_no_overlap_is_noop():
    bot = build_account_curve({"timestamp": [1, 2], "equity": [100.0, 101.0]}, "Bot")
    tony = build_account_curve({"timestamp": [9, 10], "equity": [100.0, 99.0]}, "Tony")
    abot, atony = align_common(bot, tony)
    assert abot["points"] == bot["points"]
    assert atony["points"] == tony["points"]


# ── error/edge: the real Alpaca warts (see tests/_doubles.py fixtures) ─────────────

def test_junk_entries_are_dropped_not_raised():
    # Docstring promise: malformed payload degrades, never 500s the dashboard route.
    from tests._doubles import history_with_junk_entries
    c = build_account_curve(history_with_junk_entries(), "Bot")
    # null + "n/a" bars dropped; numeric strings ("101000", "1700172800") parsed
    assert [p["value"] for p in c["points"]] == [100_000.0, 101_000.0, 102_000.0]
    assert c["points"][1]["ts"] == 1_700_172_800


def test_non_list_arrays_yield_empty_curve():
    for bad in ({"timestamp": "soon", "equity": 5}, {"timestamp": {"a": 1}, "equity": [1.0]}):
        c = build_account_curve(bad, "Bot")
        assert c["points"] == [] and c["return_pct"] is None


def test_mismatched_array_lengths_zip_to_shorter():
    c = build_account_curve({"timestamp": [1, 2, 3], "equity": [100.0, 110.0]}, "Bot")
    assert [p["ts"] for p in c["points"]] == [1, 2]


def test_prefunding_zero_payload_end_to_end():
    from tests._doubles import history_with_prefunding_zeros
    c = build_account_curve(history_with_prefunding_zeros(), "Bot")
    assert len(c["points"]) == 3                      # 3 zero days dropped
    assert c["base_value"] == 100_000.0
    assert c["return_pct"] == -0.5                    # 100k -> 99.5k


def test_single_point_curve_has_zero_return():
    c = build_account_curve({"timestamp": [1], "equity": [100_000.0]}, "Bot")
    assert len(c["points"]) == 1
    assert c["return_pct"] == 0.0
