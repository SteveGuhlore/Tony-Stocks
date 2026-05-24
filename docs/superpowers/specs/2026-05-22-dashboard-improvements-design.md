# Dashboard Improvements — Design Spec
**Date:** 2026-05-22

## Summary

Two changes to the existing Streamlit dashboard:
1. **Results page** — replace current card/filter layout with enhanced outcome cards + filter chips
2. **"Settings / System Health" → "Intelligence"** — new scan intelligence view replaces the page; health content moves to a collapsed expander

Nav stays at 5 pages: Home / Tony Watchlist / Intelligence / Results / Backtest Review.

---

## 1. Results Page Redesign

### Problem
- Cannot easily filter between open and closed positions
- Layout looks unpolished; hard to scan many results at once
- Two stacked radio filters (Period + Status) are confusing

### Design: Enhanced Cards with Filter Chips

**KPI bar** (top, always visible):
- Active count, Closed count, Targets Hit, Stops Hit, Win Rate %

**Filter chips** (single row, replaces the two radio buttons):
- All · Open · Closed · Targets · Stops · Expired · Insufficient Data

**Cards** (one per symbol, color-coded by outcome):
- Green border + dark green bg = Target Hit
- Red border + dark red bg = Stop Hit
- Purple border + dark bg = In Play (active)
- Grey border = Expired / waiting / insufficient data

Each card shows: Symbol · badge (TARGET HIT / STOP HIT / IN PLAY / EXPIRED) · P/L % · Entry / Target / Stop prices · Setup description · Score · Date closed (or "Active")

**Period selector** stays as a simple radio above the KPI bar (Today / This week / All time).

### Files to change
- `src/trading_bot/dashboard/app.py` — `render_results()`: replace stacked radios + `render_results_table()` call with new layout
- `src/trading_bot/dashboard/theme.py` — replace `render_results_table()` and `render_result_card()` with new card renderer
- `src/trading_bot/dashboard/helpers.py` — no logic changes; `RESULTS_FILTERS` and `filter_results_product_rows()` already support all filter values

---

## 2. Intelligence Page (replaces Settings / System Health)

### Problem
- "Settings / System Health" is developer-facing and rarely useful day-to-day
- No view shows what the scanner discovered in the last cycle
- No way to see if the system is improving over time

### Design: Scan Intelligence + Health Expander

**Sidebar nav label:** `Intelligence` (replaces `Settings / System Health`)

**Section 1 — Last Cycle Hero bar** (6 metrics):
- Last Cycle age · Scanned · Pre-Screened · Scored · Tony Picks · New Signals

**Section 2 — Two-column row:**
- Left: Discovery Funnel — staged bars: Universe → Pre-screener (% pass) → Scored (% pass) → Tony Picks (% pass) + "vs prior cycle" delta
- Right: Top Signals This Cycle — ranked list, NEW/UP/DN badges, score, one-line reason

**Section 3 — Learning Trend strip (3 sparkline cards):**
- Win Rate rolling 7d · Avg Score of Picks · New Discoveries per cycle

**Section 4 — Health & Config expander (collapsed by default):**
- Existing `render_system_health()` content verbatim
- Label: "System Health & Config (developer)"

### Data sources (all already in repo)
- Hero bar: `repo.latest_scan_run()`, tony events for coverage fields
- Funnel: coverage dict fields — `unique_symbols_scanned_today`, `unique_symbols_scored_today`, pre-screener counts from event log
- Top signals: `repo.latest_scan_results()` + last watch cycle picks
- Learning trend: `OutcomeAnalytics` for win rate; scan results history for avg score trend

### Files to change
- `src/trading_bot/dashboard/app.py`:
  - Rename sidebar option `"Settings / System Health"` → `"Intelligence"`
  - Add `render_intelligence(repo, results)` function
  - Wrap existing `render_system_health()` body in `st.expander("System Health & Config (developer)")`

---

## Out of scope
- No changes to Home, Tony Watchlist, or Backtest Review pages
- No new database tables or CLI commands
- No changes to scan logic or scoring

---

## Test checklist
- [ ] Results: "Closed" chip shows only closed positions
- [ ] Results: "Open" chip shows only active + waiting positions
- [ ] Results: cards render correct color per outcome type
- [ ] Results: KPI counts match chip filter counts
- [ ] Intelligence: hero bar renders gracefully with no scan data
- [ ] Intelligence: funnel shows correct pass-through percentages
- [ ] Intelligence: health expander contains all existing Settings content
- [ ] Nav: "Settings / System Health" gone, "Intelligence" present
- [ ] All existing tests pass (799)
