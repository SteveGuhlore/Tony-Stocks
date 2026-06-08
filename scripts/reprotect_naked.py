"""Re-attach stop protection to NAKED paper positions (no stop order at broker).

Background: many open positions carry only a take-profit *limit* sell (no stop),
and that open order holds the full share qty. Alpaca then rejects any new
protective order with 40310000 ("insufficient qty available: held_for_orders"),
so the watch loop can never attach a stop -> the position is naked to the
downside. This sweep, per naked symbol:

    cancel the open (non-stop) orders -> wait for the qty to free ->
    re-submit OCO protection (stop + target) at the bot's STORED levels.

Bot account only. The Command Center account is managed by its own runner; do
not point this at it.

DRY-RUN by default (read-only — safe during market hours). Add --execute to fire.

    # plan only (no orders):
    PYTHONPATH=src .venv/bin/python scripts/reprotect_naked.py --config config/default_config.yaml
    # actually re-protect:
    PYTHONPATH=src .venv/bin/python scripts/reprotect_naked.py --config config/default_config.yaml --execute
"""
from __future__ import annotations

import argparse
import time

from trading_bot.settings import load_scanner_settings
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.execution import build_alpaca_paper_broker, load_paper_trading_config


def _open_orders(client, sym: str):
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest
    req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[sym], limit=100)
    return list(client.get_orders(filter=req))


def _has_stop(orders) -> bool:
    """True if any open order on the symbol is a stop / OCO / bracket (real protection)."""
    for o in orders:
        oc = str(getattr(o, "order_class", "") or "").lower()
        ot = str(getattr(o, "type", "") or "").lower()
        if "oco" in oc or "bracket" in oc or "stop" in ot or getattr(o, "stop_price", None):
            return True
        for leg in (getattr(o, "legs", None) or []):
            lt = str(getattr(leg, "type", "") or "").lower()
            if "stop" in lt or getattr(leg, "stop_price", None):
                return True
    return False


def _cancel_open_orders(client, sym: str) -> int:
    n = 0
    for o in _open_orders(client, sym):
        try:
            client.cancel_order_by_id(o.id)
            n += 1
        except Exception as exc:
            print(f"      WARN: could not cancel order {getattr(o, 'id', '?')} for {sym}: {exc}")
    return n


def _wait_no_open_orders(client, sym: str, timeout: float = 6.0) -> bool:
    """Cancel is async on Alpaca; poll until the shares are no longer held_for_orders."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _open_orders(client, sym):
            return True
        time.sleep(0.4)
    return not _open_orders(client, sym)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/default_config.yaml")
    ap.add_argument("--execute", action="store_true", help="Place live orders (default: dry-run).")
    args = ap.parse_args()

    settings = load_scanner_settings(args.config)
    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    repo = ScannerRepository(settings.database_path)
    broker = build_alpaca_paper_broker(cfg)
    client = broker._client  # direct client for order list + cancel

    # bot's intended stop/target per open symbol (re-protection levels)
    levels = {
        str(p["symbol"]).upper(): (p.get("stop"), p.get("target"))
        for p in repo.list_open_paper_positions(account_label=cfg.account_label)
    }

    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== RE-PROTECT NAKED POSITIONS [{mode}]  account={cfg.account_label} ===\n")
    print(f"{'SYM':<6} {'QTY':>6} {'STORED_STOP':>12} {'STORED_TGT':>11}  PLAN")

    to_fix: list[tuple[str, int, float, float]] = []
    no_levels: list[str] = []
    already_ok = 0
    for p in sorted(broker.list_positions(), key=lambda x: -x.market_value):
        if p.qty <= 0:
            continue
        sym = p.symbol.upper()
        if _has_stop(_open_orders(client, sym)):
            already_ok += 1
            continue  # already protected — leave it
        stop, target = levels.get(sym, (None, None))
        if stop is None or target is None:
            no_levels.append(sym)
            print(f"{sym:<6} {p.qty:>6} {'-':>12} {'-':>11}  SKIP (no stored stop/target)")
            continue
        to_fix.append((sym, p.qty, float(stop), float(target)))
        print(f"{sym:<6} {p.qty:>6} {float(stop):>12.2f} {float(target):>11.2f}  cancel + re-OCO")

    print(f"\nAlready protected: {already_ok}   to re-protect: {len(to_fix)}   "
          f"naked w/o stored levels (skipped): {len(no_levels)} {no_levels or ''}")
    if not to_fix:
        print("\nNothing to re-protect with stored levels. Done.")
        return
    if not args.execute:
        print("\nDRY-RUN — no orders placed. Re-run with --execute to re-protect.")
        return

    print("\nExecuting...")
    for sym, qty, stop, target in to_fix:
        print(f"  {sym}: cancel orders -> re-OCO {qty} sh (stop={stop} target={target})")
        try:
            _cancel_open_orders(client, sym)
            if not _wait_no_open_orders(client, sym):
                print(f"      SKIP: {sym} still has open orders after cancel; leaving untouched")
                continue
            broker.submit_protection(symbol=sym, qty=qty, stop=stop, target=target)
            print(f"      done: {sym} protected ({qty} sh)")
        except Exception as exc:
            print(f"      ERROR re-protecting {sym}: {exc}  (check broker state for this symbol!)")

    print("\nRe-protect complete. Re-run your naked-audit to confirm the count dropped.")


if __name__ == "__main__":
    main()
