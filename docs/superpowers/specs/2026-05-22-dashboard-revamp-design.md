# Dashboard Revamp Design — V37

**Status:** Approved  
**Date:** 2026-05-22  
**Replaces:** Ad-hoc page additions built across multiple sessions

---

## Goal

Replace the inconsistent 5-tab Streamlit dashboard with a single uniform visual system across 4 pages: Today, Watchlist, Outcomes, Research.

---

## Visual System — Professional Slate

One CSS token block in `theme.py` governs all colors and spacing. No page invents its own palette.

| Token | Value | Use |
|---|---|---|
| `--bg-base` | `#0f172a` | Page background |
| `--bg-surface` | `#1e293b` | Cards, panels |
| `--bg-header` | `#111827` | Sidebar, header bands |
| `--border` | `#1f2937` | All card borders |
| `--text-primary` | `#f1f5f9` | Symbols, headings |
| `--text-secondary` | `#64748b` | Labels, sub-text |
| `--text-muted` | `#475569` | Section headers, hints |
| `--accent-blue` | `#3b82f6` | Watching state, primary CTA |
| `--accent-blue-light` | `#93c5fd` | Watching badge text |
| `--accent-violet` | `#8b5cf6` | Pending/briefing accent |
| `--accent-violet-light` | `#a5b4fc` | Pending badge text |
| `--accent-green` | `#34d399` | Active/triggered |
| `--accent-green-dark` | `#22c55e` | Target hit outcome |
| `--accent-red` | `#ef4444` | Stop hit outcome |
| `--accent-amber` | `#fbbf24` | Alerts, warnings |

**Left-border color language** (consistent everywhere):
- Blue `#3b82f6` = Watching
- Green `#34d399` = Active / triggered
- Violet `#8b5cf6` = Pending
- Green `#22c55e` = Target hit (outcomes)
- Red `#ef4444` = Stop hit (outcomes)

---

## Card Anatomy — Compact Row

All picks, tracking entries, and outcome records use the same two-line compact row card.

```
┌─ [left border color] ────────────────────────────────────────┐
│ SYMBOL   Setup type   [STATUS BADGE]          $price / +P&L  │
│ Detail line: entry trigger / prices / date                    │
└───────────────────────────────────────────────────────────────┘
```

Single renderer `render_compact_card(card: dict)` in `theme.py`. Called from all four pages. Card dict keys:
- `symbol`, `setup_type`, `status`, `status_label` (display string)
- `headline_right` (price string or P&L percent)
- `detail_line` (second line text)
- `border_color`, `badge_bg`, `badge_text_color`

---

## Navigation — 4 Tabs

```
Today  |  Watchlist  |  Outcomes  |  Research
```

Replaces: Home / Tony Watchlist / Results / Backtest Review / Intelligence

| New tab | Absorbs |
|---|---|
| Today | Home + top of Intelligence |
| Watchlist | Tony Watchlist |
| Outcomes | Results |
| Research | Backtest Review + Intelligence |

---

## Page Designs

### Today — Split Hero

**Header band** (always visible, `#111827` background):
- Status pill: READY (green) / STALE (amber, >2h) / ERROR (red)
- Scan age badge
- 4 KPI tiles: Watching · Triggered · Alerts · Win Rate

**Body — two columns:**
- Left (narrower): Tony's briefing quote (from `agent_insights`) + "Review Today" bullet list (stale setups, approaching targets, open alerts)
- Right (wider): All watching/active/pending picks as compact row cards, ordered by status priority (Active first, then Watching, then Pending)

### Watchlist

Horizontal chip filter: All / Watching / Active / Pending

All Tony picks + active tracking entries in one unified list. Compact row cards grouped by status. Watching cards show entry trigger in detail line. Active cards show current P&L + progress. Pending cards show trigger condition.

### Outcomes

KPI bar (custom HTML, matches Today KPI style): Active · Closed · Targets Hit · Stops Hit · Win Rate

Horizontal chip filter: All / Open / Targets / Stops

Compact row cards for every result record, newest first. Outcomes use green/red left-border color language.

Below fold (collapsed by default): win rate by setup type if ≥5 closed outcomes exist.

### Research

1. Discovery funnel strip: symbols scanned → candidates → picks (from last scan cycle data)
2. Top signals table: top 5 rows from last scan, columns = Symbol · Score · Setup · Trigger
3. Backtest Review panel: existing `BacktestReview` module output, unchanged
4. Agent insights block: last `agent_insights` text if available
5. System Health: collapsed expander (existing `render_system_health()`)

---

## Files to Change

| File | Change |
|---|---|
| `src/trading_bot/dashboard/theme.py` | Add unified CSS token block; add `render_compact_card()`; keep existing outcome card functions; remove `render_results_table()` if unused |
| `src/trading_bot/dashboard/app.py` | Rewrite `main()` nav to 4 tabs; rewrite `render_home()` → `render_today()`; rewrite `render_watchlist()`; rewrite `render_results()` → `render_outcomes()`; rewrite `render_intelligence()` → `render_research()`; remove `render_backtest_review()` as separate tab (moves into Research) |

**No changes to:**
- `helpers.py` — data logic untouched
- `backtest_review.py` — module output embedded as-is
- Database / repositories
- CLI commands

---

## Dead Code to Remove

- `render_results_performance()` — imported but not called after Results rewrite
- `render_results_table()` — replaced by compact card renderer
- `render_result_card()` — replaced by `render_compact_card()`
- Bare `else:` branch in `main()` nav routing

---

## Test Coverage Required

- `test_render_compact_card_watching()` — blue left border, WATCHING badge
- `test_render_compact_card_active()` — green left border, P&L shown
- `test_render_compact_card_target_hit()` — green outcome border
- `test_render_compact_card_stop_hit()` — red outcome border
- `test_render_today_runs()` — smoke: `render_today(mock_repo, mock_results)` doesn't raise
- `test_render_watchlist_runs()` — smoke
- `test_render_outcomes_runs()` — smoke
- `test_render_research_runs()` — smoke
- `test_nav_has_four_tabs()` — main() routes Today/Watchlist/Outcomes/Research
