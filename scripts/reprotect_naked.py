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
import json
import time
import urllib.request

from trading_bot.settings import load_scanner_settings
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.execution import build_alpaca_paper_broker, load_paper_trading_config

_PAPER_REST = "https://paper-api.alpaca.markets"


def _protected_symbols(key: str, secret: str) -> set[str]:
    """Symbols with a LIVE protective stop, via raw REST ``nested=true``.

    Ground truth for naked detection. An OCO's stop leg sits at status="held" and is NOT
    returned by a flat status=open query — it only appears rolled up under its parent's
    ``legs`` when ``nested=true``. The alpaca-py GetOrdersRequest in this SDK build drops
    the nested flag, so we read the REST endpoint directly (identical logic to
    preflight_check.sh's cross-account audit). A symbol is protected iff it has an open
    SELL order/leg carrying a real stop_price (or a stop-type)."""
    url = f"{_PAPER_REST}/v2/orders?status=open&limit=500&nested=true"
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
    with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 - fixed paper host
        orders = json.load(r)
    out: set[str] = set()
    for o in orders:
        for x in [o, *(o.get("legs") or [])]:
            if x.get("side") == "sell" and (x.get("stop_price") or "stop" in str(x.get("type", "")).lower()):
                out.add(str(x.get("symbol") or "").upper())
    return out


def _open_orders(client, sym: str):
    # Used only to drain a symbol's orders before re-OCO (the cancelable take-profit is
    # status=open and visible here). Naked DETECTION does not use this — it uses the
    # raw-REST nested call in _protected_symbols, because held stop legs aren't returned
    # by a flat status=open query and this SDK build drops the nested flag.
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest
    req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[sym], limit=100)
    return list(client.get_orders(filter=req))


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
    protected = _protected_symbols(broker.api_key, broker.secret_key)  # raw-REST nested ground truth

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
        if sym in protected:
            already_ok += 1
            continue  # already protected (live stop leg) — leave it
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
