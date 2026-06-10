"""Paper-trading cycle engine (phase 5).

One call per watch cycle ties the pieces together, in order:
  1. reconcile — close repo positions whose broker bracket filled (target/stop)
  2. CC exits — flatten positions the Command Center verdict says to sell/get out
  3. open — submit risk-sized bracket orders for newly triggered picks (gated)

Broker-agnostic: works against AlpacaPaperBroker (paper=True) or FakeBroker. The
account identity (``account_label``) keeps a second (CC) account isolated.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from trading_bot.execution.broker import Broker
from trading_bot.execution.order_router import PortfolioState, should_trade
from trading_bot.execution.paper_config import PaperTradingConfig
from trading_bot.vault.sector_map import get_sector


def _resolve_sectors(repo: Any, symbols: Any) -> dict[str, str]:
    """Map UPPER(symbol) -> normalized sector for each symbol.

    Layered for coverage: the scanner's own ``scan_results.sector`` first (most complete
    for the live universe), then the ``vault.sector_map`` fallback (which has gaps, e.g.
    HBAN/HST), then "" (unknown -> uncapped at the gate). Resolution lives here so the
    pure router never touches the DB.
    """
    syms = {str(s).upper() for s in (symbols or []) if s}
    if not syms:
        return {}
    try:
        db = repo.sectors_for_symbols(syms)
    except Exception:  # never break the cycle on a sector lookup
        db = {}
    resolved: dict[str, str] = {}
    for sym in syms:
        raw = db.get(sym) or get_sector(sym)
        resolved[sym] = (raw or "").strip().lower()
    return resolved


def _portfolio_state(broker: Broker, repo: Any, account_label: str, day: str) -> PortfolioState:
    account = broker.account()
    open_symbols = repo.open_paper_position_symbols(account_label=account_label)
    exited_today = repo.symbols_closed_today(account_label=account_label, day=day)
    sector_counts = Counter(_resolve_sectors(repo, open_symbols).values())
    return PortfolioState(
        equity=account.equity,
        open_symbols=frozenset(open_symbols),
        open_positions=len(open_symbols),
        orders_today=repo.count_paper_orders_today(account_label=account_label, day=day),
        exited_today=frozenset(exited_today),
        open_sector_counts=dict(sector_counts),
    )


def _classify_exit(exit_price: float | None, position: dict[str, Any]) -> str:
    """Infer a terminal result from the exit price vs the stored target/stop levels."""
    if exit_price is None:
        return "closed"
    target = position.get("target")
    stop = position.get("stop")
    if target is not None and exit_price >= float(target):
        return "target_hit"
    if stop is not None and exit_price <= float(stop):
        return "stop_hit"
    return "closed"


def _realized_pl(position: dict[str, Any], exit_price: float | None) -> float | None:
    """Compute realized P&L = (exit - entry) * qty from the stored position, for brokers
    that report a close without it. The live Alpaca broker's ``closed_positions()`` returns
    ``realized_pl=None`` (it only has the SELL fill, not the entry), so without this the
    paper book records 0 realized on every stop/target exit and the head-to-head P&L is
    blank. Returns None when entry/exit/qty are unusable."""
    if exit_price is None:
        return None
    entry = position.get("entry_price")
    qty = position.get("qty")
    try:
        if entry in (None, "", 0) or not qty:
            return None
        return round((float(exit_price) - float(entry)) * int(qty), 2)
    except (TypeError, ValueError):
        return None


def _latest_close_records(broker: Broker) -> dict[str, dict[str, Any]]:
    """Most recent close record per symbol. A broker can report several SELL fills for
    one symbol (re-entries on later days still inside the live order window), and the
    record order differs by broker (live Alpaca lists newest-first, FakeBroker appends
    oldest-first) — grading a close against a stale fill records the wrong exit price
    and P&L. Prefer the record with the greatest ``closed_at``; on ties or when the
    stamp is missing, the later-seen record wins."""
    best: dict[str, dict[str, Any]] = {}
    for c in broker.closed_positions():
        sym = str(c.get("symbol") or "").upper()
        if not sym:
            continue
        prev = best.get(sym)
        if prev is None or str(c.get("closed_at") or "") >= str(prev.get("closed_at") or ""):
            best[sym] = c
    return best


def reconcile_closed(broker: Broker, repo: Any, account_label: str, now_iso: str) -> list[dict[str, Any]]:
    """Close repo positions that are no longer open at the broker (bracket filled)."""
    broker_open = {p.symbol.upper() for p in broker.list_positions()}
    closed_records = _latest_close_records(broker)
    results: list[dict[str, Any]] = []
    for position in repo.list_open_paper_positions(account_label=account_label):
        sym = str(position["symbol"]).upper()
        if sym in broker_open:
            continue  # still open at the broker
        record = closed_records.get(sym, {})
        exit_price = record.get("exit")
        result = record.get("result") or _classify_exit(exit_price, position)
        realized = record.get("realized_pl")
        if realized is None:  # live broker reports no P&L — compute from entry + exit fill
            realized = _realized_pl(position, exit_price)
        repo.close_paper_position(
            sym, account_label=account_label, result=result, exit_price=exit_price,
            realized_pl=realized, closed_at=now_iso,
        )
        results.append({"symbol": sym, "result": result, "exit": exit_price})
    return results


def apply_cc_exits(
    broker: Broker, repo: Any, config: PaperTradingConfig, cc_exits: set[str],
    account_label: str, now_iso: str,
) -> list[str]:
    """Flatten open positions named by the Command Center exit verdict."""
    if not config.close_on_command_center_exit or not cc_exits:
        return []
    positions = {str(p["symbol"]).upper(): p
                 for p in repo.list_open_paper_positions(account_label=account_label)}
    requested = {str(s).upper() for s in cc_exits}
    closed: list[str] = []
    for sym in sorted(requested & set(positions)):
        if broker.close_position(sym) is None:
            # Broker refused/errored (live broker returns None on any failure). Do NOT
            # mark the repo row closed — that would leave a real position open at the
            # broker with nothing tracking it. The verdict persists; retry next cycle.
            continue
        record = _latest_close_records(broker).get(sym, {})
        realized = record.get("realized_pl")
        if realized is None:  # live broker reports no P&L — compute from entry + exit fill
            realized = _realized_pl(positions[sym], record.get("exit"))
        repo.close_paper_position(
            sym, account_label=account_label, result="closed",
            exit_price=record.get("exit"), realized_pl=realized, closed_at=now_iso,
        )
        closed.append(sym)
    return closed


def open_triggered_picks(
    broker: Broker, repo: Any, config: PaperTradingConfig, triggered_picks: list[dict[str, Any]],
    account_label: str, market_open: bool, kill_switch: bool, day: str, now_iso: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Submit risk-sized bracket orders for triggered picks the gates approve."""
    submitted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for pick in triggered_picks:
        symbol = str(pick.get("symbol", "")).upper()
        state = _portfolio_state(broker, repo, account_label, day)
        sector = _resolve_sectors(repo, [symbol]).get(symbol, "")
        decision = should_trade(
            symbol=symbol, entry=pick.get("entry"), stop=pick.get("stop"),
            target=pick.get("target"), sector=sector, state=state, config=config,
            kill_switch=kill_switch, market_open=market_open,
        )
        if not decision.approved:
            rejected.append({"symbol": symbol, "reason": decision.reason})
            continue
        order = broker.submit_bracket(
            symbol=symbol, qty=decision.quantity, entry=float(pick["entry"]),
            stop=float(pick["stop"]), target=float(pick["target"]),
            time_in_force=config.time_in_force,
        )
        repo.record_paper_order(
            broker_order_id=order.order_id, account_label=account_label, symbol=symbol,
            side="buy", qty=decision.quantity, entry=float(pick["entry"]), stop=float(pick["stop"]),
            target=float(pick["target"]), time_in_force=config.time_in_force, status=order.status,
            snapshot_id=pick.get("snapshot_id"), reason=decision.reason, submitted_at=now_iso,
        )
        repo.open_paper_position(
            account_label=account_label, symbol=symbol, qty=decision.quantity,
            entry_price=float(pick["entry"]), stop=float(pick["stop"]), target=float(pick["target"]),
            broker_order_id=order.order_id, snapshot_id=pick.get("snapshot_id"), opened_at=now_iso,
        )
        submitted.append({"symbol": symbol, "qty": decision.quantity, "order_id": order.order_id})
    return submitted, rejected


def run_paper_cycle(
    *,
    broker: Broker,
    repo: Any,
    config: PaperTradingConfig,
    triggered_picks: list[dict[str, Any]],
    account_label: str,
    market_open: bool,
    kill_switch: bool,
    cc_exits: set[str] | None,
    now_iso: str,
    day: str,
) -> dict[str, Any]:
    """Run one paper-trading cycle: reconcile -> CC exits -> open new picks."""
    reconciled = reconcile_closed(broker, repo, account_label, now_iso)
    cc_closed = apply_cc_exits(broker, repo, config, cc_exits or set(), account_label, now_iso)
    submitted, rejected = open_triggered_picks(
        broker, repo, config, triggered_picks, account_label, market_open, kill_switch, day, now_iso,
    )
    return {
        "reconciled": reconciled,
        "cc_closed": cc_closed,
        "submitted": submitted,
        "rejected": rejected,
    }
