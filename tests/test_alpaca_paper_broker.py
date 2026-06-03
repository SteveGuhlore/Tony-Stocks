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
