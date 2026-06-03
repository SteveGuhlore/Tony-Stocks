# Design Spec — Alpaca Paper Trading Execution

**Date:** 2026-06-02
**Status:** Draft for review (execute in a fresh session)
**Scope:** Auto-execute Tony's triggered picks as Alpaca **paper** bracket orders, behind safety gates, with positions/fills surfaced back to the dashboard.

## Decisions (locked with user)
- **Execution path:** real **Alpaca paper account** (`TradingClient(..., paper=True)`), not the in-memory simulator.
- **Trigger:** **auto-submit** when a tracked pick's `entry_triggered` flips true in the watch loop — gated, off by default.

## Product truth
Tony already scans → picks → tracks `entry_triggered`. This subsystem adds the missing edge: when entry triggers, place a risk-sized **bracket order** (entry + stop + target) on Alpaca paper, track the position to close (target/stop), and journal the real fills so Tony's paper record reflects actual fills instead of hypothetical math. This is the bridge toward eventual real-money trust.

## Architecture
- **`execution/alpaca_paper.py`** — `AlpacaPaperBroker` implementing a small interface (`submit_bracket`, `get_position`, `list_positions`, `cancel`, `account`) over `alpaca-py` with `paper=True`. Mirrors the existing `PaperBroker` interface so tests can swap a fake.
- **`execution/order_router.py`** — pure-ish policy: given a triggered snapshot + account state + config, decide whether to place an order and size it. **Fully unit-tested** (sizing, gates, dedup). No I/O.
- **Watch-loop hook** — in the tracking path where `entry_triggered` is set (`snapshots/active_tracking.py` / `cli.py watch`), call the router; on an approved order, submit via the broker and persist an order/position row.
- **Storage** — `paper_orders` / `paper_positions` tables (extend `storage/database.py` + `repositories.py`); journal fills via `paper/paper_journal.py` (extend beyond the current P&L helper).
- **Reconciliation** — each cycle, sync open positions with Alpaca (fills, stop/target hits) → update outcome labels feeding the existing outcomes/record pipeline.
- **API + dashboard** — `GET /api/paper/positions` + account summary; surface in the Board (real P/L on triggered rows) and a small account chip in the StatusBar. The dashboard's existing P/L column starts reflecting real fills.

## Safety gates (all required, fail-closed)
- Master flag `paper_trading.enabled: false` by default; **independent** of `live_trading_enabled` (which stays false and continues to block any real-money path).
- `risk_per_trade_pct` (e.g. 1%) → position size from entry/stop distance; reject if size rounds to 0.
- `max_open_positions`, `max_notional_per_position`, `max_daily_orders`.
- Market-hours guard (no orders when closed); duplicate guard (one open position per symbol; dedup on snapshot id).
- Kill switch (config flag + CLI `paper-flatten` to cancel/close all).
- Never place an order without Alpaca **paper** base URL asserted at startup.

## Config (new `paper_trading:` block in default_config.yaml)
```yaml
paper_trading:
  enabled: false
  risk_per_trade_pct: 1.0
  max_open_positions: 8
  max_notional_per_position: 5000
  max_daily_orders: 20
  bracket: true            # entry + stop + target as one bracket
```

## Phased plan (each phase: tests + commit; build/CLI smoke)
1. **Config + flags** — add `paper_trading` block + loader/validation; assert paper base URL. Tests for config parsing + the fail-closed default.
2. **Order router (pure)** — `should_trade()` + `size_position()` with all gates. TDD: sizing math, each gate, dedup, kill switch. No network.
3. **Alpaca paper broker** — `AlpacaPaperBroker` over `alpaca-py` paper; thin, with a `FakeBroker` for tests. Integration test gated behind keys (skipped in CI/demo).
4. **Storage + journal** — `paper_orders`/`paper_positions` tables + repository methods + fill journaling. Tests on repositories.
5. **Watch-loop wiring** — call router on `entry_triggered`, submit, persist; reconcile open positions each cycle → outcomes. Tests with FakeBroker driving a full trigger→fill→target/stop lifecycle.
6. **API + dashboard** — `/api/paper/positions` + account; Board real P/L + StatusBar account chip; degrade when disabled.

## Non-goals
- No real-money trading (`live_trading_enabled` stays false; separate future effort with its own gates).
- No options/shorts initially (long equity brackets only).
- No portfolio optimization — one pick = one position.

## Open questions (settle at execution start)
- Position sizing basis: % of paper account equity vs fixed notional? (spec assumes risk-% of equity).
- Partial fills / GTC vs DAY orders?
- Do we trade only `reaffirm`/no-CC picks, or also wait for Command Center verdict before sizing? (Tie-in to Plan 5 contract.)
