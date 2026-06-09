"""Backfill realized_pl on already-closed paper positions that recorded None.

The live Alpaca broker reported closes with realized_pl=None (it only had the SELL
fill, not the entry), so historically-closed paper positions stored no P&L and the
paper book showed $0 realized. This recomputes realized_pl = (exit - entry) * qty for
those rows from the stored entry/exit/qty. Forward-fixed in paper_engine.reconcile_closed;
this cleans up the rows closed before that fix.

DRY-RUN by default (read-only). Add --execute to write.

    PYTHONPATH=src .venv/bin/python scripts/backfill_realized_pl.py --config config/default_config.yaml
    PYTHONPATH=src .venv/bin/python scripts/backfill_realized_pl.py --config config/default_config.yaml --execute
"""
from __future__ import annotations

import argparse

from trading_bot.settings import load_scanner_settings
from trading_bot.storage.database import connect


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/default_config.yaml")
    ap.add_argument("--execute", action="store_true", help="Write the backfill (default: dry-run).")
    args = ap.parse_args()

    settings = load_scanner_settings(args.config)
    with connect(settings.database_path) as conn:
        rows = conn.execute(
            "SELECT id, symbol, account_label, entry_price, exit_price, qty, result "
            "FROM paper_positions "
            "WHERE status='closed' AND realized_pl IS NULL "
            "AND exit_price IS NOT NULL AND entry_price IS NOT NULL AND qty IS NOT NULL"
        ).fetchall()

        print(f"{'ID':>6} {'SYM':<6} {'ENTRY':>9} {'EXIT':>9} {'QTY':>6} {'REALIZED':>11}  RESULT")
        updates: list[tuple[float, int]] = []
        total = 0.0
        for r in rows:
            d = dict(r)
            try:
                realized = round((float(d["exit_price"]) - float(d["entry_price"])) * int(d["qty"]), 2)
            except (TypeError, ValueError):
                continue
            updates.append((realized, int(d["id"])))
            total += realized
            print(f"{d['id']:>6} {str(d['symbol']):<6} {float(d['entry_price']):>9.2f} "
                  f"{float(d['exit_price']):>9.2f} {int(d['qty']):>6} {realized:>11.2f}  {d.get('result')}")

        print(f"\nRows to backfill: {len(updates)}   net realized P&L: {total:,.2f}")
        if not updates:
            print("Nothing to backfill — all closed rows already have realized_pl.")
            return
        if not args.execute:
            print("\nDRY-RUN — no writes. Re-run with --execute to apply.")
            return

        for realized, rid in updates:
            conn.execute("UPDATE paper_positions SET realized_pl=? WHERE id=?", (realized, rid))
        conn.commit()
        print(f"\nBackfilled {len(updates)} rows. Refresh the dashboard — REALIZED + win-rate now populate.")


if __name__ == "__main__":
    main()
