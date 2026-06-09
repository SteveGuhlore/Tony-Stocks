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


def test_build_account_curve_handles_zero_base():
    c = build_account_curve({"timestamp": [1, 2], "equity": [0.0, 0.0]}, "X")
    assert c["base_value"] is None
    assert all(p["index"] == 100.0 for p in c["points"])  # degrade flat, never divide by zero


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
