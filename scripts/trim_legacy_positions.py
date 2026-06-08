"""Trim oversized (legacy) paper positions down to the target % of equity.

The bot's book carries legacy positions sized at ~5% (old $5k notional default)
alongside new 1% entries. This realigns the big ones to 1% so sizing is uniform
and the head-to-head isn't skewed. Per position it: cancels the open protective
orders, market-reduces to the target share count, re-attaches OCO protection on
the remainder, and updates the ledger qty.

DRY-RUN by default (read-only — safe during market hours). Add --execute to fire.

    # plan only (no orders):
    PYTHONPATH=src .venv/bin/python scripts/trim_legacy_positions.py --config config/default_config.yaml
    # actually trim:
    PYTHONPATH=src .venv/bin/python scripts/trim_legacy_positions.py --config config/default_config.yaml --execute
"""
from __future__ import annotations

import argparse
import math

from trading_bot.settings import load_scanner_settings
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.storage.database import connect
from trading_bot.execution import build_alpaca_paper_broker, load_paper_trading_config


def _cancel_open_orders(client, sym: str) -> int:
    from alpaca.trading.enums import QueryOrderStatus
    from alpaca.trading.requests import GetOrdersRequest
    req = GetOrdersRequest(status=QueryOrderStatus.OPEN, symbols=[sym], limit=100)
    n = 0
    for o in client.get_orders(filter=req):
        try:
            client.cancel_order_by_id(o.id)
            n += 1
        except Exception as exc:
            print(f"      WARN: could not cancel order {getattr(o, 'id', '?')} for {sym}: {exc}")
    return n


def _reduce_position(client, sym: str, sell_qty: int) -> None:
    from alpaca.trading.requests import ClosePositionRequest
    client.close_position(sym, close_options=ClosePositionRequest(qty=str(sell_qty)))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/default_config.yaml")
    ap.add_argument("--target-pct", type=float, default=1.0, help="Target notional %% of equity per position.")
    ap.add_argument("--trim-above-mult", type=float, default=1.5,
                    help="Only trim positions whose notional exceeds target * this multiple.")
    ap.add_argument("--execute", action="store_true", help="Place live orders (default: dry-run).")
    args = ap.parse_args()

    settings = load_scanner_settings(args.config)
    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    repo = ScannerRepository(settings.database_path)
    broker = build_alpaca_paper_broker(cfg)
    client = broker._client  # direct client for partial-close + order cancel

    equity = float(broker.account().equity)
    target_notional = equity * args.target_pct / 100.0
    trim_threshold = target_notional * args.trim_above_mult

    # repo stop/target per open symbol (for re-protection)
    levels = {
        str(p["symbol"]).upper(): (p.get("stop"), p.get("target"))
        for p in repo.list_open_paper_positions(account_label=cfg.account_label)
    }

    positions = broker.list_positions()
    mode = "EXECUTE" if args.execute else "DRY-RUN"
    print(f"=== TRIM LEGACY POSITIONS [{mode}] ===")
    print(f"equity=${equity:,.0f}  target={args.target_pct}% (${target_notional:,.0f})  "
          f"trim if notional > ${trim_threshold:,.0f}\n")
    print(f"{'SYM':<6} {'QTY':>6} {'PRICE':>9} {'NOTIONAL':>10} {'->TGTQTY':>9} {'SELL':>6} {'PROCEEDS':>10}")

    total_before = sum(p.market_value for p in positions)
    plan = []
    freed = 0.0
    for p in sorted(positions, key=lambda x: -x.market_value):
        if p.qty <= 0:
            continue
        price = p.market_value / p.qty
        if p.market_value <= trim_threshold:
            continue
        target_qty = max(1, math.floor(target_notional / price))
        sell_qty = p.qty - target_qty
        if sell_qty <= 0:
            continue
        proceeds = sell_qty * price
        freed += proceeds
        plan.append((p.symbol, p.qty, price, target_qty, sell_qty))
        print(f"{p.symbol:<6} {p.qty:>6} {price:>9.2f} {p.market_value:>10,.0f} "
              f"{target_qty:>9} {sell_qty:>6} {proceeds:>10,.0f}")

    print(f"\nPositions to trim: {len(plan)}   est. exposure freed: ${freed:,.0f}")
    print(f"Gross exposure: ${total_before:,.0f} ({total_before/equity:.2f}x) "
          f"-> ~${total_before-freed:,.0f} ({(total_before-freed)/equity:.2f}x)")

    if not plan:
        print("\nNothing exceeds the trim threshold. Done.")
        return
    if not args.execute:
        print("\nDRY-RUN — no orders placed. Re-run with --execute to trim.")
        return

    print("\nExecuting...")
    for sym, qty, price, target_qty, sell_qty in plan:
        stop, target = levels.get(sym, (None, None))
        print(f"  {sym}: cancel orders -> sell {sell_qty} -> re-protect {target_qty} "
              f"(stop={stop} target={target})")
        try:
            _cancel_open_orders(client, sym)
            _reduce_position(client, sym, sell_qty)
            if stop is not None and target is not None:
                broker.submit_protection(symbol=sym, qty=target_qty,
                                         stop=float(stop), target=float(target))
            else:
                print(f"      WARN: no stored stop/target for {sym}; remainder LEFT UNPROTECTED")
            with connect(settings.database_path) as conn:
                conn.execute(
                    "UPDATE paper_positions SET qty=? WHERE account_label=? AND symbol=? AND status='open'",
                    (target_qty, cfg.account_label, sym),
                )
            print(f"      done: {sym} now {target_qty} sh")
        except Exception as exc:
            print(f"      ERROR trimming {sym}: {exc}  (check broker state for this symbol!)")

    print("\nTrim complete. Verify with: python -m trading_bot.cli paper-status --config", args.config)


if __name__ == "__main__":
    main()
