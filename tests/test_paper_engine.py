"""Tests for the paper-trading engine: cycle orchestration (paper phase 5).

run_paper_cycle ties the router, broker, and storage together: reconcile closed
positions -> apply CC-verdict exits -> open new triggered picks (gated). Driven by
a FakeBroker + a temp-file repo so a full trigger -> fill -> target/stop lifecycle
runs with no network.
"""
from __future__ import annotations

import pytest

from trading_bot.execution.broker import FakeBroker
from trading_bot.execution.paper_engine import run_paper_cycle
from trading_bot.execution.paper_config import PaperTradingConfig
from trading_bot.storage.repositories import ScannerRepository


@pytest.fixture()
def repo(tmp_path):
    return ScannerRepository(tmp_path / "engine.db")


def _cfg(**over):
    base = dict(enabled=True, risk_per_trade_pct=1.0, max_open_positions=8,
                max_notional_per_position=100_000.0, max_daily_orders=20)
    base.update(over)
    return PaperTradingConfig(**base)


def _pick(symbol="ZETA", entry=100.0, stop=95.0, target=115.0, snapshot_id=1):
    return {"symbol": symbol, "entry": entry, "stop": stop, "target": target, "snapshot_id": snapshot_id}


def _cycle(broker, repo, config, **over):
    base = dict(
        broker=broker, repo=repo, config=config, triggered_picks=[], account_label="tony",
        market_open=True, kill_switch=False, cc_exits=set(), now_iso="2026-06-02T15:00:00+00:00",
        day="2026-06-02",
    )
    base.update(over)
    return run_paper_cycle(**base)


class TestOpening:
    def test_triggered_pick_opens_position_and_orders(self, repo):
        b = FakeBroker(equity=100_000.0)
        summary = _cycle(b, repo, _cfg(), triggered_picks=[_pick()])
        assert summary["submitted"] and summary["submitted"][0]["symbol"] == "ZETA"
        assert b.get_position("ZETA") is not None
        assert repo.open_paper_position_symbols(account_label="tony") == {"ZETA"}
        assert repo.count_paper_orders_today(account_label="tony", day="2026-06-02") == 1

    def test_duplicate_pick_not_reopened(self, repo):
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick()])
        summary = _cycle(b, repo, _cfg(), triggered_picks=[_pick()])
        assert summary["submitted"] == []
        assert repo.count_paper_orders_today(account_label="tony", day="2026-06-02") == 1

    def test_disabled_config_opens_nothing(self, repo):
        b = FakeBroker()
        summary = _cycle(b, repo, _cfg(enabled=False), triggered_picks=[_pick()])
        assert summary["submitted"] == []
        assert b.list_positions() == []

    def test_kill_switch_blocks_opening(self, repo):
        b = FakeBroker()
        summary = _cycle(b, repo, _cfg(), triggered_picks=[_pick()], kill_switch=True)
        assert summary["submitted"] == []

    def test_market_closed_blocks_opening(self, repo):
        b = FakeBroker()
        summary = _cycle(b, repo, _cfg(), triggered_picks=[_pick()], market_open=False)
        assert summary["submitted"] == []


class TestReconciliation:
    def test_target_hit_closes_repo_position_with_outcome(self, repo):
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.simulate_price("ZETA", 116.0)  # bracket target fills at the broker
        summary = _cycle(b, repo, _cfg())  # next cycle, no new picks -> reconcile
        assert summary["reconciled"] and summary["reconciled"][0]["result"] == "target_hit"
        assert repo.open_paper_position_symbols(account_label="tony") == set()
        closed = [p for p in repo.list_paper_positions(account_label="tony") if p["status"] == "closed"]
        assert closed[0]["result"] == "target_hit"
        assert closed[0]["exit_price"] == 115.0

    def test_stop_hit_closes_repo_position(self, repo):
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.simulate_price("ZETA", 94.0)
        summary = _cycle(b, repo, _cfg())
        assert summary["reconciled"][0]["result"] == "stop_hit"

    def test_realized_pl_computed_when_broker_omits_it(self, repo):
        """The live Alpaca broker reports closes with realized_pl=None; reconcile must
        compute it from the stored entry + exit fill so the paper book records real P&L
        (not 0) and the head-to-head measurement works."""
        from trading_bot.execution.paper_engine import _realized_pl
        assert _realized_pl({"entry_price": 100.0, "qty": 10}, 95.0) == -50.0
        assert _realized_pl({"entry_price": 100.0, "qty": 10}, None) is None
        assert _realized_pl({"entry_price": None, "qty": 10}, 95.0) is None
        assert _realized_pl({"entry_price": 100.0, "qty": 0}, 95.0) is None

        class _NoPnLBroker(FakeBroker):  # mimics the live broker: exit fill, no P&L
            def closed_positions(self):
                return [{**c, "realized_pl": None} for c in super().closed_positions()]

        b = _NoPnLBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.simulate_price("ZETA", 94.0)  # stop fills at 95
        _cycle(b, repo, _cfg())
        closed = [p for p in repo.list_paper_positions(account_label="tony") if p["status"] == "closed"]
        assert closed and closed[0]["result"] == "stop_hit"
        expected = round((float(closed[0]["exit_price"]) - float(closed[0]["entry_price"])) * closed[0]["qty"], 2)
        assert closed[0]["realized_pl"] == expected
        assert closed[0]["realized_pl"] < 0  # a stop-out is a loss, not 0

    def test_reconcile_is_idempotent(self, repo):
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick()])
        b.simulate_price("ZETA", 116.0)
        _cycle(b, repo, _cfg())
        summary = _cycle(b, repo, _cfg())  # already reconciled
        assert summary["reconciled"] == []


class TestSameDayReentry:
    """The DAL bug: stop fills -> position closed -> bot must NOT re-buy it same day."""

    def test_stopped_out_pick_is_not_rebought_same_day(self, repo):
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.simulate_price("ZETA", 94.0)            # stop fills at the broker
        stop_cycle = _cycle(b, repo, _cfg())       # reconcile -> closed stop_hit
        assert stop_cycle["reconciled"][0]["result"] == "stop_hit"
        # Same day, the scanner re-presents ZETA (fresh plan). Must be rejected.
        summary = _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=99.0, stop=94.0, target=120.0)])
        assert summary["submitted"] == []
        assert any("re-entry" in r["reason"].lower() for r in summary["rejected"])
        assert repo.open_paper_position_symbols(account_label="tony") == set()

    def test_reentry_allowed_when_flag_disabled(self, repo):
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.simulate_price("ZETA", 94.0)
        _cycle(b, repo, _cfg())                     # closed stop_hit
        summary = _cycle(b, repo, _cfg(block_same_day_reentry=False),
                         triggered_picks=[_pick(entry=99.0, stop=94.0, target=120.0)])
        assert summary["submitted"] and summary["submitted"][0]["symbol"] == "ZETA"


class TestLiveLikeBrokerSeam:
    """Error/edge coverage against the LIVE broker contract (see tests/_doubles.py).

    The live Alpaca broker reports closes as bare SELL fills: result=None,
    realized_pl=None, newest-first, one record PER FILL (a re-entered symbol has
    several). FakeBroker's friendly records hide all of that, so these are the cases
    that bit (or would bite) in production.
    """

    def test_live_close_graded_from_stored_levels_and_pl_computed(self, repo):
        from tests._doubles import LiveLikeBroker
        b = LiveLikeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.simulate_price("ZETA", 116.0)  # target leg fills at 115
        summary = _cycle(b, repo, _cfg())
        assert summary["reconciled"][0]["result"] == "target_hit"  # inferred, broker said None
        closed = [p for p in repo.list_paper_positions(account_label="tony") if p["status"] == "closed"]
        assert closed[0]["exit_price"] == 115.0
        assert closed[0]["realized_pl"] == round((115.0 - 100.0) * closed[0]["qty"], 2)

    def test_newest_fill_wins_when_symbol_has_multiple_close_records(self, repo):
        """Re-entry regression: ZETA stops out on day 1, re-enters day 2 and hits target.
        Both SELL fills sit in the live order window; reconciling the day-2 close against
        the STALE day-1 fill records the wrong exit price, result, and P&L."""
        from tests._doubles import LiveLikeBroker
        b = LiveLikeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.simulate_price("ZETA", 94.0)   # day-1 stop fill at 95 (stale record)
        _cycle(b, repo, _cfg())          # reconcile the stop-out
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=99.0, stop=94.0, target=120.0)],
               day="2026-06-03", now_iso="2026-06-03T15:00:00+00:00")
        b.simulate_price("ZETA", 121.0)  # day-2 target fill at 120 (fresh record)
        summary = _cycle(b, repo, _cfg(), day="2026-06-03", now_iso="2026-06-03T16:00:00+00:00")
        assert summary["reconciled"][0]["result"] == "target_hit"
        closed = sorted(
            (p for p in repo.list_paper_positions(account_label="tony") if p["status"] == "closed"),
            key=lambda p: p["closed_at"],
        )
        assert closed[-1]["exit_price"] == 120.0   # fresh fill, not the stale 95
        assert closed[-1]["realized_pl"] > 0

    def test_manual_close_between_levels_is_closed_not_target_or_stop(self, repo):
        from tests._doubles import LiveLikeBroker
        b = LiveLikeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.close_position("ZETA", price=104.0)  # operator flatten mid-range
        summary = _cycle(b, repo, _cfg())
        assert summary["reconciled"][0]["result"] == "closed"
        closed = [p for p in repo.list_paper_positions(account_label="tony") if p["status"] == "closed"]
        assert closed[0]["realized_pl"] == round((104.0 - 100.0) * closed[0]["qty"], 2)

    def test_vanished_position_with_no_close_record_still_closes_repo_row(self, repo):
        """The closing fill aged out of the order window (or the order query failed).
        The repo row must still close — result 'closed', exit/P&L unknown — instead of
        lingering as a phantom open position that blocks the symbol forever."""
        from tests._doubles import AmnesiacBroker
        b = AmnesiacBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick()])
        b._positions.pop("ZETA")  # position gone, no record of why
        summary = _cycle(b, repo, _cfg())
        assert summary["reconciled"][0]["result"] == "closed"
        closed = [p for p in repo.list_paper_positions(account_label="tony") if p["status"] == "closed"]
        assert closed[0]["exit_price"] is None
        assert closed[0]["realized_pl"] is None

    def test_cc_exit_after_reentry_uses_fresh_close_record(self, repo):
        """Same stale-record trap on the CC-exit path: after a stop-out + re-entry, a CC
        flatten must record the NEW fill, not the day-1 stop fill."""
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=100.0, target=115.0, stop=95.0)])
        b.simulate_price("ZETA", 94.0)   # day-1 stop fill at 95
        _cycle(b, repo, _cfg())
        _cycle(b, repo, _cfg(), triggered_picks=[_pick(entry=99.0, stop=94.0, target=120.0)],
               day="2026-06-03", now_iso="2026-06-03T15:00:00+00:00")
        b.simulate_price("ZETA", 105.0)  # mid-range, still open
        summary = _cycle(b, repo, _cfg(close_on_command_center_exit=True), cc_exits={"ZETA"},
                         day="2026-06-03", now_iso="2026-06-03T16:00:00+00:00")
        assert summary["cc_closed"] == ["ZETA"]
        closed = sorted(
            (p for p in repo.list_paper_positions(account_label="tony") if p["status"] == "closed"),
            key=lambda p: p["closed_at"],
        )
        assert closed[-1]["exit_price"] == 105.0   # fresh CC fill, not the stale 95
        assert closed[-1]["realized_pl"] == round((105.0 - 99.0) * closed[-1]["qty"], 2)


class TestCommandCenterExit:
    def test_cc_exit_closes_open_position(self, repo):
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick()])
        b.simulate_price("ZETA", 105.0)  # still open
        summary = _cycle(b, repo, _cfg(close_on_command_center_exit=True), cc_exits={"ZETA"})
        assert summary["cc_closed"] == ["ZETA"]
        assert b.get_position("ZETA") is None
        assert repo.open_paper_position_symbols(account_label="tony") == set()

    def test_failed_broker_close_keeps_repo_row_open_for_retry(self, repo):
        """The live broker returns None when a close errors. Marking the repo row closed
        anyway would orphan a REAL open position (nothing tracking or protecting it) —
        the row must stay open so the persistent verdict retries next cycle."""
        class _FlakyCloseBroker(FakeBroker):
            def __init__(self):
                super().__init__()
                self.fail_closes = 1

            def close_position(self, symbol, *, price=None):
                if self.fail_closes > 0:
                    self.fail_closes -= 1
                    return None  # live broker: exception swallowed -> None
                return super().close_position(symbol, price=price)

        b = _FlakyCloseBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick()])
        summary = _cycle(b, repo, _cfg(close_on_command_center_exit=True), cc_exits={"ZETA"})
        assert summary["cc_closed"] == []                       # failed close not recorded
        assert b.get_position("ZETA") is not None               # broker still holds it
        assert repo.open_paper_position_symbols(account_label="tony") == {"ZETA"}
        retry = _cycle(b, repo, _cfg(close_on_command_center_exit=True), cc_exits={"ZETA"})
        assert retry["cc_closed"] == ["ZETA"]                   # next cycle succeeds

    def test_cc_exit_ignored_when_disabled(self, repo):
        b = FakeBroker()
        _cycle(b, repo, _cfg(), triggered_picks=[_pick()])
        summary = _cycle(b, repo, _cfg(close_on_command_center_exit=False), cc_exits={"ZETA"})
        assert summary["cc_closed"] == []
        assert b.get_position("ZETA") is not None
