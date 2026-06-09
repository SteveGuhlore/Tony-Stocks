"""Tests for the paper-flatten kill switch (run_paper_flatten)."""
from __future__ import annotations

import argparse

from trading_bot import cli as cli_mod
from trading_bot.execution.broker import FakeBroker
from trading_bot.execution.paper_config import PaperTradingConfig
from trading_bot.storage.repositories import ScannerRepository


class _FlakyCloseBroker(FakeBroker):
    def __init__(self, fail_symbols=()):
        super().__init__()
        self.fail_symbols = set(fail_symbols)

    def close_position(self, symbol, *, price=None):
        if symbol.upper() in self.fail_symbols:
            return None  # live broker: close errored -> None
        return super().close_position(symbol, price=price)


class _NoPnLFlakyBroker(_FlakyCloseBroker):
    def closed_positions(self):  # live broker has the SELL fill only, no P&L
        return [{**c, "realized_pl": None} for c in super().closed_positions()]


def _setup(tmp_path, monkeypatch, broker, symbols=("ZETA",)):
    db = tmp_path / "flatten.db"
    repo = ScannerRepository(db)
    for i, sym in enumerate(symbols):
        broker.submit_bracket(symbol=sym, qty=10, entry=100.0, stop=95.0, target=115.0)
        repo.open_paper_position(account_label="tony", symbol=sym, qty=10, entry_price=100.0,
                                 stop=95.0, target=115.0, broker_order_id=f"o{i}", snapshot_id=i,
                                 opened_at="2026-06-09T14:31:00+00:00")
    cfg = PaperTradingConfig(enabled=True, account_label="tony")
    monkeypatch.setattr(cli_mod, "load_scanner_settings",
                        lambda path: argparse.Namespace(database_path=db, paper_trading={}))
    monkeypatch.setattr(cli_mod, "load_paper_trading_config", lambda raw: cfg, raising=False)
    import trading_bot.execution as execution
    monkeypatch.setattr(execution, "load_paper_trading_config", lambda raw: cfg)
    monkeypatch.setattr(execution, "build_alpaca_paper_broker", lambda c: broker)
    return repo


def test_flatten_closes_broker_and_ledger(tmp_path, monkeypatch):
    b = _NoPnLFlakyBroker()
    repo = _setup(tmp_path, monkeypatch, b, symbols=("ZETA", "NVDA"))
    b.simulate_price("ZETA", 104.0)  # mid-range mark, still open
    out = cli_mod.run_paper_flatten(argparse.Namespace(config="ignored.yaml"))
    assert out["flattened"] == 2
    assert b.list_positions() == []
    rows = repo.list_paper_positions(account_label="tony")
    assert all(r["status"] == "closed" for r in rows)
    zeta = next(r for r in rows if r["symbol"] == "ZETA")
    # live broker reported no P&L -> computed from entry + exit fill, not left None
    assert zeta["realized_pl"] == round((104.0 - 100.0) * 10, 2)


def test_failed_broker_close_leaves_row_open(tmp_path, monkeypatch):
    b = _FlakyCloseBroker(fail_symbols={"ZETA"})
    repo = _setup(tmp_path, monkeypatch, b, symbols=("ZETA", "NVDA"))
    out = cli_mod.run_paper_flatten(argparse.Namespace(config="ignored.yaml"))
    assert out["flattened"] == 1                              # NVDA only
    assert b.get_position("ZETA") is not None                 # broker still holds it
    assert repo.open_paper_position_symbols(account_label="tony") == {"ZETA"}
