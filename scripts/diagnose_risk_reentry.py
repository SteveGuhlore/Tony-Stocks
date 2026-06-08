"""Diagnose (1) position-sizing vs account equity and (2) same-day stop->rebuy churn.

Read-only. Run on the VM from the repo dir:

    PYTHONPATH=src .venv/bin/python scripts/diagnose_risk_reentry.py --config config/default_config.yaml

Equity is read from the live broker when keys are present (so % sizing is real);
pass --equity to skip the network call.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from trading_bot.settings import load_scanner_settings
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.storage.database import connect
from trading_bot.execution import load_paper_trading_config


def _equity(settings, cfg, override):
    if override:
        return float(override), "override"
    try:
        from trading_bot.execution import build_alpaca_paper_broker
        return float(build_alpaca_paper_broker(cfg).account().equity), "live broker"
    except Exception as exc:  # no keys / network — fall back
        return None, f"unavailable ({exc})"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/default_config.yaml")
    ap.add_argument("--equity", type=float, default=None)
    args = ap.parse_args()

    settings = load_scanner_settings(args.config)
    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    now_et = datetime.now(ZoneInfo("America/New_York"))
    day = now_et.strftime("%Y-%m-%d")
    eq, eq_src = _equity(settings, cfg, args.equity)

    print(f"=== RISK / RE-ENTRY DIAGNOSIS  ({now_et:%Y-%m-%d %H:%M %Z}) ===")
    print(f"DB: {settings.database_path}   account_label={cfg.account_label!r}")
    print(f"equity: {('$%,.0f' % eq) if eq else 'n/a'} ({eq_src})")
    print(f"config: risk_per_trade_pct={cfg.risk_per_trade_pct}  "
          f"max_notional_per_position={cfg.max_notional_per_position}  "
          f"max_open_positions={cfg.max_open_positions}")
    if eq:
        intended = eq * cfg.risk_per_trade_pct / 100.0
        print(f"  -> intended 1-trade size at {cfg.risk_per_trade_pct}% of equity = ${intended:,.0f}")
        print(f"  -> but max_notional cap = ${cfg.max_notional_per_position:,.0f} "
              f"= {cfg.max_notional_per_position / eq * 100:.3f}% of equity "
              + ("  <-- CAP IS BINDING, positions far below intended %"
                 if cfg.max_notional_per_position < intended else ""))

    # ── 1) Per-position sizing (open book) ────────────────────────────────────
    with connect(settings.database_path) as conn:
        rows = conn.execute(
            "SELECT symbol, qty, entry_price, stop, opened_at, status, result, closed_at "
            "FROM paper_positions WHERE account_label=? ORDER BY opened_at",
            (cfg.account_label,),
        ).fetchall()
    rows = [dict(r) for r in rows]
    open_rows = [r for r in rows if r["status"] == "open"]

    print(f"\n[1] Open positions: {len(open_rows)}")
    print(f"    {'SYM':<6} {'QTY':>12} {'ENTRY':>9} {'NOTIONAL':>11} {'%EQ':>7}  frac?")
    buckets = {"~$1k (≈0.1%)": 0, "~$10k (≈1%)": 0, "other": 0}
    for r in sorted(open_rows, key=lambda x: -(float(x["qty"] or 0) * float(x["entry_price"] or 0))):
        notion = float(r["qty"] or 0) * float(r["entry_price"] or 0)
        pct = (notion / eq * 100.0) if eq else float("nan")
        frac = abs(float(r["qty"]) - round(float(r["qty"]))) > 1e-6
        if notion < 3000:
            buckets["~$1k (≈0.1%)"] += 1
        elif notion < 30000:
            buckets["~$10k (≈1%)"] += 1
        else:
            buckets["other"] += 1
        print(f"    {r['symbol']:<6} {float(r['qty']):>12.4f} {float(r['entry_price'] or 0):>9.2f} "
              f"{notion:>11,.0f} {pct:>6.2f}%  {'frac' if frac else 'whole'}")
    print("    sizing buckets:", {k: v for k, v in buckets.items() if v})

    # ── 2) Same-day stop -> rebuy churn ───────────────────────────────────────
    # A symbol is "churned" if it has a position CLOSED today and another OPENED
    # today AFTER that close (esp. result=stop_hit).
    print(f"\n[2] Same-day exit -> re-entry (account {cfg.account_label!r}, {day})")
    by_sym: dict[str, list[dict]] = {}
    for r in rows:
        opened = (r["opened_at"] or "")[:10]
        closed = (r["closed_at"] or "")[:10]
        if opened == day or closed == day:
            by_sym.setdefault(r["symbol"], []).append(r)

    churned = 0
    for sym, evs in sorted(by_sym.items()):
        closes_today = [e for e in evs if (e["closed_at"] or "")[:10] == day]
        for c in closes_today:
            reopened = [e for e in evs
                        if (e["opened_at"] or "") > (c["closed_at"] or "")
                        and (e["opened_at"] or "")[:10] == day]
            if reopened:
                churned += 1
                ce = c.get("result") or "closed"
                print(f"    {sym:<6} EXIT {ce:<9} @ {c['closed_at'][11:19]} "
                      f"-> RE-ENTERED {len(reopened)}x (next @ {reopened[0]['opened_at'][11:19]})")
    if churned == 0:
        print("    none detected in the ledger today.")
    else:
        print(f"\n    *** {churned} same-day exit->re-entry event(s). After a STOP this is "
              "loss-churn: no re-entry guard is blocking it.")


if __name__ == "__main__":
    main()
