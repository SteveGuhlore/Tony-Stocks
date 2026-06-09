"""Tests for AlpacaPaperBroker (paper phase 3).

Mapping is exercised with an injected stub trading client, so real alpaca-py
request objects are built (catching API misuse) without any network or keys. The
live integration path is gated behind real keys and not run here.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from trading_bot.execution.alpaca_paper import AlpacaPaperBroker, build_alpaca_paper_broker
from trading_bot.execution.broker import BracketOrderResult, BrokerAccount, BrokerPosition
from trading_bot.execution.paper_config import PaperTradingConfig


class _StubClient:
    def __init__(self):
        self.submitted = []
        self.closed = []

    def submit_order(self, order_data):
        self.submitted.append(order_data)
        return SimpleNamespace(id="ord-1", symbol="ZETA", qty="50", status="accepted")

    def get_account(self):
        return SimpleNamespace(equity="100000", cash="60000", buying_power="120000")

    def get_all_positions(self):
        return [SimpleNamespace(symbol="ZETA", qty="50", avg_entry_price="100.0",
                                market_value="5000.0", unrealized_pl="150.0")]

    def close_position(self, symbol):
        self.closed.append(symbol)
        return SimpleNamespace(id="close-1", symbol=symbol, qty="50", status="accepted")


def _broker(client=None):
    return AlpacaPaperBroker(api_key="k", secret_key="s", account_label="tony", client=client or _StubClient())


class TestConstruction:
    def test_rejects_non_paper_base_url(self):
        with pytest.raises(ValueError):
            AlpacaPaperBroker(api_key="k", secret_key="s", base_url="https://api.alpaca.markets", client=_StubClient())

    def test_factory_missing_keys_raises(self):
        cfg = PaperTradingConfig(enabled=True)
        with pytest.raises(RuntimeError):
            build_alpaca_paper_broker(cfg, env={})

    def test_factory_builds_from_env(self):
        cfg = PaperTradingConfig(enabled=True)
        b = build_alpaca_paper_broker(cfg, env={"ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"}, client=_StubClient())
        assert isinstance(b, AlpacaPaperBroker)

    def test_factory_prefers_dedicated_paper_keys(self):
        cfg = PaperTradingConfig(enabled=True)
        env = {"ALPACA_PAPER_API_KEY": "pk", "ALPACA_PAPER_SECRET_KEY": "ps",
               "ALPACA_API_KEY": "k", "ALPACA_SECRET_KEY": "s"}
        b = build_alpaca_paper_broker(cfg, env=env, client=_StubClient())
        assert b.api_key == "pk"


class TestClosedPositions:
    """closed_positions() maps raw CLOSED-order queries to close records. The raw feed
    is newest-first with one order PER FILL — a re-entered symbol shows several SELL
    fills, and the engine must only ever see the most recent one."""

    @staticmethod
    def _stub_alpaca(monkeypatch):
        """Install minimal alpaca.trading.{enums,requests} stand-ins so the lazy imports
        inside closed_positions() resolve without alpaca-py (and deterministically when
        the real package is present)."""
        import sys
        from types import ModuleType, SimpleNamespace

        enums = ModuleType("alpaca.trading.enums")
        enums.OrderSide = SimpleNamespace(SELL="sell", BUY="buy")
        enums.QueryOrderStatus = SimpleNamespace(CLOSED="closed", OPEN="open")
        requests_mod = ModuleType("alpaca.trading.requests")

        class GetOrdersRequest:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

        requests_mod.GetOrdersRequest = GetOrdersRequest
        trading = ModuleType("alpaca.trading")
        root = ModuleType("alpaca")
        for name, mod in (("alpaca", root), ("alpaca.trading", trading),
                          ("alpaca.trading.enums", enums), ("alpaca.trading.requests", requests_mod)):
            monkeypatch.setitem(sys.modules, name, mod)

    @staticmethod
    def _order(symbol, price, status="filled", side="sell", filled_at="2026-06-09T15:00:00Z"):
        return SimpleNamespace(symbol=symbol, status=status, side=side,
                               filled_avg_price=price, filled_at=filled_at, submitted_at=None)

    def _broker_with_orders(self, monkeypatch, orders):
        self._stub_alpaca(monkeypatch)
        client = _StubClient()
        client.get_orders = lambda filter: orders  # noqa: A002 - alpaca-py kwarg name
        return _broker(client)

    def test_keeps_only_newest_fill_per_symbol(self, monkeypatch):
        b = self._broker_with_orders(monkeypatch, [
            self._order("ZETA", "120.0", filled_at="2026-06-09T15:00:00Z"),  # newest first
            self._order("AAPL", "200.0", filled_at="2026-06-08T15:00:00Z"),
            self._order("ZETA", "95.0", filled_at="2026-06-02T15:00:00Z"),   # stale re-entry fill
        ])
        records = {r["symbol"]: r for r in b.closed_positions()}
        assert len(records) == 2
        assert records["ZETA"]["exit"] == 120.0          # not the stale 95
        assert records["ZETA"]["closed_at"] == "2026-06-09T15:00:00Z"
        assert records["ZETA"]["result"] is None and records["ZETA"]["realized_pl"] is None

    def test_skips_non_sells_unfilled_and_priceless_orders(self, monkeypatch):
        b = self._broker_with_orders(monkeypatch, [
            self._order("BUYS", "100.0", side="buy"),
            self._order("CANC", "100.0", status="canceled"),
            self._order("NOPX", None),
            self._order("GOOD", "50.0"),
        ])
        assert [r["symbol"] for r in b.closed_positions()] == ["GOOD"]

    def test_partially_filled_sell_is_reported(self, monkeypatch):
        b = self._broker_with_orders(monkeypatch, [self._order("PART", "75.0", status="partially_filled")])
        assert b.closed_positions()[0]["exit"] == 75.0

    def test_order_query_error_returns_empty(self, monkeypatch):
        self._stub_alpaca(monkeypatch)
        client = _StubClient()

        def boom(filter):  # noqa: A002
            raise OSError("alpaca down")

        client.get_orders = boom
        assert _broker(client).closed_positions() == []


class TestMapping:
    def test_submit_bracket_maps_result(self):
        client = _StubClient()
        b = _broker(client)
        res = b.submit_bracket(symbol="ZETA", qty=50, entry=100.0, stop=95.0, target=115.0)
        assert isinstance(res, BracketOrderResult)
        assert res.order_id == "ord-1"
        assert res.symbol == "ZETA"
        assert res.qty == 50
        assert res.entry == 100.0 and res.stop == 95.0 and res.target == 115.0
        assert len(client.submitted) == 1  # one bracket request sent

    def test_account_maps(self):
        acct = _broker().account()
        assert isinstance(acct, BrokerAccount)
        assert acct.equity == 100000.0
        assert acct.cash == 60000.0
        assert acct.account_label == "tony"

    def test_list_positions_maps(self):
        positions = _broker().list_positions()
        assert len(positions) == 1
        p = positions[0]
        assert isinstance(p, BrokerPosition)
        assert p.symbol == "ZETA"
        assert p.qty == 50
        assert p.avg_entry_price == 100.0
        assert p.unrealized_pl == 150.0

    def test_get_position_filters_by_symbol(self):
        b = _broker()
        assert b.get_position("ZETA").symbol == "ZETA"
        assert b.get_position("NONE") is None

    def test_close_position_calls_client(self):
        client = _StubClient()
        b = _broker(client)
        res = b.close_position("ZETA")
        assert client.closed == ["ZETA"]
        assert res is not None
