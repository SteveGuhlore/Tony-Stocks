"""Tests for the broker interface + in-memory FakeBroker (paper phase 3).

FakeBroker implements the same Broker interface as AlpacaPaperBroker so the rest of
the system (router wiring, reconciliation, journal) can be tested without network.
Its simulate_price hook drives full trigger -> fill -> target/stop lifecycles.
"""
from __future__ import annotations

from trading_bot.execution.broker import (
    BracketOrderResult,
    BrokerAccount,
    BrokerPosition,
    FakeBroker,
)


def _open(broker, symbol="ZETA", qty=50, entry=100.0, stop=95.0, target=115.0):
    return broker.submit_bracket(symbol=symbol, qty=qty, entry=entry, stop=stop, target=target)


class TestFakeBrokerAccount:
    def test_account_reports_equity_and_label(self):
        b = FakeBroker(equity=100_000.0, account_label="tony")
        acct = b.account()
        assert isinstance(acct, BrokerAccount)
        assert acct.equity == 100_000.0
        assert acct.account_label == "tony"


class TestSubmitBracket:
    def test_submit_opens_position(self):
        b = FakeBroker()
        res = _open(b)
        assert isinstance(res, BracketOrderResult)
        assert res.symbol == "ZETA"
        assert res.qty == 50
        assert res.entry == 100.0 and res.stop == 95.0 and res.target == 115.0
        assert res.order_id

    def test_position_is_listed_and_retrievable(self):
        b = FakeBroker()
        _open(b)
        pos = b.get_position("ZETA")
        assert isinstance(pos, BrokerPosition)
        assert pos.symbol == "ZETA"
        assert pos.qty == 50
        assert pos.avg_entry_price == 100.0
        assert [p.symbol for p in b.list_positions()] == ["ZETA"]

    def test_symbol_is_uppercased(self):
        b = FakeBroker()
        b.submit_bracket(symbol="zeta", qty=10, entry=10.0, stop=9.0, target=12.0)
        assert b.get_position("ZETA") is not None

    def test_unknown_position_is_none(self):
        assert FakeBroker().get_position("NONE") is None


class TestLifecycleSimulation:
    def test_price_reaching_target_closes_as_target_hit(self):
        b = FakeBroker()
        _open(b, entry=100.0, target=115.0, stop=95.0)
        b.simulate_price("ZETA", 116.0)
        assert b.get_position("ZETA") is None  # closed
        closed = b.closed_positions()
        assert len(closed) == 1
        assert closed[0]["symbol"] == "ZETA"
        assert closed[0]["result"] == "target_hit"
        assert closed[0]["exit"] == 115.0  # exits at the target level

    def test_price_reaching_stop_closes_as_stop_hit(self):
        b = FakeBroker()
        _open(b, entry=100.0, target=115.0, stop=95.0)
        b.simulate_price("ZETA", 94.0)
        assert b.get_position("ZETA") is None
        closed = b.closed_positions()
        assert closed[0]["result"] == "stop_hit"
        assert closed[0]["exit"] == 95.0

    def test_price_between_keeps_position_open(self):
        b = FakeBroker()
        _open(b, entry=100.0, target=115.0, stop=95.0)
        b.simulate_price("ZETA", 103.0)
        pos = b.get_position("ZETA")
        assert pos is not None
        assert pos.unrealized_pl == (103.0 - 100.0) * 50

    def test_close_position_marks_closed(self):
        b = FakeBroker()
        _open(b, entry=100.0)
        b.simulate_price("ZETA", 108.0)
        res = b.close_position("ZETA")
        assert b.get_position("ZETA") is None
        assert res.symbol == "ZETA"
        closed = b.closed_positions()
        assert closed[0]["result"] == "closed"
        assert closed[0]["exit"] == 108.0

    def test_close_unknown_position_is_safe(self):
        b = FakeBroker()
        assert b.close_position("NONE") is None
