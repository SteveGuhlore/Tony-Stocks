"""Diagnose why the bot's FIRST PASS (its own paper book) made no entries today.

Read-only. Run on the VM (where the live DB lives):

    $env:PYTHONPATH = "src"; python scripts/diagnose_first_pass.py --config config/default_config.yaml

It replays the exact entry pipeline the watch loop uses each cycle —
  repo.triggerable_paper_picks(day) -> should_trade(...) gate -> submit
— so the printout is the *real* reason, not a guess. The second pass (Tony /
Command Center) is a SEPARATE account+system with a different entry mechanism;
this script only explains the bot's own book.
"""
from __future__ import annotations

import argparse
from datetime import datetime
from zoneinfo import ZoneInfo

from trading_bot.settings import load_scanner_settings
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.storage.database import connect
from trading_bot.execution import load_paper_trading_config
from trading_bot.execution.order_router import PortfolioState, should_trade


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/default_config.yaml")
    ap.add_argument("--equity", type=float, default=100_000.0,
                    help="Equity to use for sizing (avoids a broker/network call).")
    args = ap.parse_args()

    settings = load_scanner_settings(args.config)
    cfg = load_paper_trading_config(getattr(settings, "paper_trading", None))
    repo = ScannerRepository(settings.database_path)
    now_et = datetime.now(ZoneInfo("America/New_York"))
    day = now_et.strftime("%Y-%m-%d")

    print(f"=== FIRST-PASS ENTRY DIAGNOSIS  ({now_et:%Y-%m-%d %H:%M %Z}) ===")
    print(f"DB: {settings.database_path}")

    # 0) Config / master switch ------------------------------------------------
    print("\n[0] Paper-trading config")
    print(f"    enabled            : {cfg.enabled}"
          + (f"   reason={cfg.disabled_reason}" if cfg.disabled_reason else ""))
    print(f"    account_label      : {cfg.account_label!r}")
    print(f"    max_open_positions : {cfg.max_open_positions}")
    print(f"    max_daily_orders   : {cfg.max_daily_orders}")
    print(f"    max_notional/pos   : {cfg.max_notional_per_position}")
    print(f"    risk_per_trade_pct : {cfg.risk_per_trade_pct}")

    # 1) Kill switch / market window ------------------------------------------
    import os
    kill = os.path.exists("data/STOP_PAPER_TRADING")
    stop_watch = os.path.exists("data/STOP_WATCH_MODE")
    weekday = now_et.weekday() < 5
    mins = now_et.hour * 60 + now_et.minute
    market_open = weekday and (9 * 60 + 30) <= mins <= (16 * 60)
    print("\n[1] Gates that block the whole cycle")
    print(f"    STOP_PAPER_TRADING present : {kill}   (True = kill switch ON)")
    print(f"    STOP_WATCH_MODE present    : {stop_watch}")
    print(f"    market_open (ET regular)   : {market_open}")

    # 2) Portfolio state -------------------------------------------------------
    open_syms = repo.open_paper_position_symbols(account_label=cfg.account_label)
    orders_today = repo.count_paper_orders_today(account_label=cfg.account_label, day=day)
    state = PortfolioState(
        equity=args.equity,
        open_symbols=frozenset(open_syms),
        open_positions=len(open_syms),
        orders_today=orders_today,
    )
    print("\n[2] Portfolio state (bot account)")
    print(f"    open positions : {len(open_syms)} / {cfg.max_open_positions}"
          + ("   <-- AT/OVER CAP" if len(open_syms) >= cfg.max_open_positions else ""))
    print(f"    orders today   : {orders_today} / {cfg.max_daily_orders}"
          + ("   <-- AT/OVER CAP" if orders_today >= cfg.max_daily_orders else ""))

    # 3) Today's entry-status mix across snapshots ----------------------------
    with connect(settings.database_path) as conn:
        rows = conn.execute(
            "SELECT COALESCE(entry_status,'<null>') s, COUNT(*) n FROM candidate_snapshots "
            "GROUP BY s ORDER BY n DESC"
        ).fetchall()
        triggered_today = conn.execute(
            "SELECT COUNT(*) FROM candidate_snapshots WHERE entry_status='triggered' "
            "AND substr(COALESCE(entry_triggered_at, actual_entry_time,''),1,10)=?",
            (day,),
        ).fetchone()[0]
    print("\n[3] candidate_snapshots.entry_status (all rows)")
    for s, n in rows:
        print(f"    {s:<18}: {n}")
    print(f"    -> entry_status='triggered' WITH today's ET date: {triggered_today}")

    # 4) The actual queue the paper cycle pulls -------------------------------
    picks = repo.triggerable_paper_picks(day=day)
    print(f"\n[4] triggerable_paper_picks(day={day}) -> {len(picks)} pick(s)")
    if not picks:
        print("    *** EMPTY: nothing crossed its planned entry today, so the first pass")
        print("        has nothing to submit. This is the usual reason for 0 entries.")

    # 5) Replay should_trade() for each pick ----------------------------------
    if picks:
        print("\n[5] should_trade() verdict per pick (the real gate)")
        approved = 0
        reasons: dict[str, int] = {}
        for p in picks:
            d = should_trade(
                symbol=p["symbol"], entry=p["entry"], stop=p["stop"], target=p["target"],
                state=state, config=cfg, kill_switch=kill, market_open=market_open,
            )
            tag = "APPROVE" if d.approved else "REJECT "
            print(f"    {tag} {p['symbol']:<6} {d.reason}")
            if d.approved:
                approved += 1
            else:
                key = d.reason.split("(")[0].split(":")[0].strip()
                reasons[key] = reasons.get(key, 0) + 1
        print(f"\n    SUMMARY: {approved} approved, {len(picks) - approved} rejected")
        for k, v in sorted(reasons.items(), key=lambda x: -x[1]):
            print(f"      {v:>3} x {k}")


if __name__ == "__main__":
    main()
