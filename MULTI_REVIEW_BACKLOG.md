# Multi-review backlog (Tony-Stocks)

From the 2026-06-17 multi-model audit (Claude Opus 4.8 + Codex gpt-5.4 high + Gemini 2.5-pro).
**Fixed items are in git history on this merge.** This file tracks what's intentionally left for later.

## Remaining engineering work
- [ ] **`cli._funnel_eval_signals_from_snapshots`** (MED): still collapses snapshots to one per ticker.
      `build_evaluated_picks` now accepts `signals_history` (as-of joined) — wire the CLI to pass it.
- [ ] **`analytics/backtest_review.py` `win_rate()`** (MED): counts every target/stop hit, but P/L and
      equity silently drop trades with invalid brackets → metrics can mix denominators. Make the trade
      set consistent across win-rate and P/L.
- [ ] **Scripts** (LOW, dev tooling):
  - `scripts/verify_research_stack.py`: runs network calls + `sys.exit()` at import time (no
    `if __name__ == "__main__"` guard) and never adds `src/` to `sys.path`.
  - `scripts/seed_vault.py`: `days_active_map` computed over the full dataset once → backfilled notes
    get future activity counts.
  - `scripts/index_cc_vault.py`: claims non-destructive but overwrites root `HOME.md` / top-level
    `_index.md`; only indexes top-level dirs.

## Operator action items (before VM deploy from `main`)
- [ ] **Set `DASHBOARD_ACTION_PIN` on the VM.** The control endpoints now fail closed in prod
      (`ENV_ROLE=prod`) without it — every control action returns 403 until it is set.
- [ ] **Verify the dashboard control buttons (B1)** against a running dashboard + backend. The
      Stop-watch / Pause / Flatten-all / Trigger-scan buttons now fire real `api.control.*` calls
      (previously inert); the live click→API→toast flow was not exercised in the audit.

## Superseded by this morning's main (dropped from this branch)
- Control API path `/api/control` -> `/api/controls` and button wiring (B1): **already done on
  `main`** (better — react-query mutations + per-action Idempotency-Key). My versions dropped.
- `MiniLine` empty-state guard: main's richer MiniLine STILL has the `all.length < 2` bug (two
  1-point series render a blank SVG). Low priority — re-apply the `drawable = series.filter(p>=2)`
  guard if it ever matters.

## Notes (verified already-handled, no change needed)
- `tony_bridge` corrupt-log self-heals (renames `.corrupt` + atomic write).
- `market_clock` holiday table already spans 2026-2027.
- Models' "duplicate orders" / "missing buying-power" findings were FALSE POSITIVES given the
  `paper_engine` repo-based dedup wiring (see MASTER-REPORT).
