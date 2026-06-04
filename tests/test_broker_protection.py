"""Tests for protective-order (OCO re-protect) support on the broker seam.

Covers the behavior run_paper_reprotect relies on: submit_protection records a
protective order, open_protective_symbols reports it for dedup, and protection
clears when the position closes.
"""
from __future__ import annotations

from trading_bot.execution.broker import FakeBroker


def _held(broker: FakeBroker, symbol="AAA", qty=10, entry=100.0, stop=95.0, target=115.0):
    broker.submit_bracket(symbol=symbol, qty=qty, entry=entry, stop=stop, target=target)


def test_submit_protection_marks_symbol_protected():
    b = FakeBroker()
    _held(b, "AAA")
    assert b.open_protective_symbols() == set()  # bracket alone isn't a re-protect
    res = b.submit_protection(symbol="AAA", qty=10, stop=94.0, target=116.0)
    assert res.symbol == "AAA"
    assert res.stop == 94.0 and res.target == 116.0
    assert b.open_protective_symbols() == {"AAA"}


def test_protection_updates_tracked_levels():
    b = FakeBroker()
    _held(b, "AAA", stop=95.0, target=115.0)
    b.submit_protection(symbol="AAA", qty=10, stop=90.0, target=120.0)
    pos = b._positions["AAA"]
    assert pos["stop"] == 90.0 and pos["target"] == 120.0


def test_open_protective_symbols_only_counts_held():
    b = FakeBroker()
    _held(b, "AAA")
    b.submit_protection(symbol="AAA", qty=10, stop=94.0, target=116.0)
    assert b.open_protective_symbols() == {"AAA"}
    # closing the position clears its protection (so re-protect won't re-submit)
    b.close_position("AAA")
    assert b.open_protective_symbols() == set()


def test_reprotect_dedup_semantics():
    # Mirror the CLI's skip logic: a symbol already in open_protective_symbols is skipped.
    b = FakeBroker()
    _held(b, "AAA")
    _held(b, "BBB")
    b.submit_protection(symbol="AAA", qty=10, stop=94.0, target=116.0)
    held = {p.symbol for p in b.list_positions()}
    already = b.open_protective_symbols()
    to_protect = [s for s in held if s not in already]
    assert to_protect == ["BBB"]
