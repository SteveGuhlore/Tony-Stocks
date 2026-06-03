"""Tests for paper-trading storage: paper_orders / paper_positions (phase 4).

Repository methods journal submitted orders and track position lifecycle so the
watch loop can build PortfolioState (dedup + capacity gates) and reconcile fills
into outcomes. In-memory-style SQLite via a tmp file; no network.
"""
from __future__ import annotations

import pytest

from trading_bot.storage.database import connect, initialize_database
from trading_bot.storage.repositories import ScannerRepository


@pytest.fixture()
def repo(tmp_path):
    return ScannerRepository(tmp_path / "paper.db")


def _order(repo, **over):
    base = dict(
        broker_order_id="o1", account_label="tony", symbol="ZETA", side="buy", qty=50,
        entry=100.0, stop=95.0, target=115.0, time_in_force="day", status="submitted",
        snapshot_id=1, reason="approved", submitted_at="2026-06-02T14:31:00+00:00",
    )
    base.update(over)
    return repo.record_paper_order(**base)


def _open(repo, **over):
    base = dict(
        account_label="tony", symbol="ZETA", qty=50, entry_price=100.0, stop=95.0,
        target=115.0, broker_order_id="o1", snapshot_id=1, opened_at="2026-06-02T14:31:00+00:00",
    )
    base.update(over)
    return repo.open_paper_position(**base)


class TestSchema:
    def test_paper_tables_exist(self, tmp_path):
        db = tmp_path / "db.db"
        initialize_database(db)
        with connect(db) as conn:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert {"paper_orders", "paper_positions"} <= tables


class TestPaperOrders:
    def test_record_returns_id(self, repo):
        oid = _order(repo)
        assert isinstance(oid, int) and oid > 0

    def test_count_orders_today_by_label_and_day(self, repo):
        _order(repo, submitted_at="2026-06-02T14:31:00+00:00")
        _order(repo, symbol="NVDA", broker_order_id="o2", submitted_at="2026-06-02T15:00:00+00:00")
        _order(repo, symbol="OLD", broker_order_id="o3", submitted_at="2026-06-01T15:00:00+00:00")
        assert repo.count_paper_orders_today(account_label="tony", day="2026-06-02") == 2
        assert repo.count_paper_orders_today(account_label="tony", day="2026-06-01") == 1

    def test_count_orders_isolated_by_account(self, repo):
        _order(repo, account_label="tony")
        _order(repo, account_label="cc", broker_order_id="o2")
        assert repo.count_paper_orders_today(account_label="tony", day="2026-06-02") == 1


class TestPaperPositions:
    def test_open_appears_in_open_list(self, repo):
        pid = _open(repo)
        assert isinstance(pid, int) and pid > 0
        opens = repo.list_open_paper_positions(account_label="tony")
        assert [p["symbol"] for p in opens] == ["ZETA"]
        assert repo.open_paper_position_symbols(account_label="tony") == {"ZETA"}

    def test_close_updates_outcome_and_removes_from_open(self, repo):
        _open(repo)
        repo.close_paper_position(
            "ZETA", account_label="tony", result="target_hit", exit_price=115.0,
            realized_pl=750.0, closed_at="2026-06-03T14:00:00+00:00",
        )
        assert repo.open_paper_position_symbols(account_label="tony") == set()
        closed = [p for p in repo.list_paper_positions(account_label="tony") if p["status"] == "closed"]
        assert len(closed) == 1
        assert closed[0]["result"] == "target_hit"
        assert closed[0]["exit_price"] == 115.0
        assert closed[0]["realized_pl"] == 750.0

    def test_open_positions_isolated_by_account(self, repo):
        _open(repo, account_label="tony", symbol="ZETA")
        _open(repo, account_label="cc", symbol="NVDA", broker_order_id="o2")
        assert repo.open_paper_position_symbols(account_label="tony") == {"ZETA"}
        assert repo.open_paper_position_symbols(account_label="cc") == {"NVDA"}

    def test_close_unknown_symbol_is_noop(self, repo):
        # No open position; must not raise.
        repo.close_paper_position("NONE", account_label="tony", result="closed",
                                  exit_price=1.0, realized_pl=0.0, closed_at="2026-06-03T00:00:00+00:00")
        assert repo.open_paper_position_symbols(account_label="tony") == set()
