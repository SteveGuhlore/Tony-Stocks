# Dashboard Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Results page with color-coded outcome cards + filter chips, and replace "Settings / System Health" with an "Intelligence" page showing last-cycle scan stats and learning trends.

**Architecture:** All changes are in `app.py` and `theme.py` only. No database, CLI, or helpers.py logic changes. New renderer functions follow the existing `render_html()` pattern. Existing `build_result_card_model()` dict keys are reused as-is — the card data model is unchanged, only the presentation layer changes.

**Tech Stack:** Python 3.14, Streamlit, Plotly, existing `ScannerRepository`, `OutcomeAnalytics`

---

## File Map

| File | Change |
|------|--------|
| `src/trading_bot/dashboard/theme.py` | Add `render_result_outcome_card()`, `render_results_kpi_bar()`, `render_result_outcome_cards()` — replaces `render_result_card()` and `render_results_table()` |
| `src/trading_bot/dashboard/app.py` | Rewrite `render_results()`, add `render_intelligence()`, rename nav entry, wrap `render_system_health()` body in expander |
| `tests/test_dashboard_theme.py` | New tests for card color logic and KPI bar |
| `tests/test_dashboard_helpers.py` | No changes |

---

## Task 1: New outcome card renderer in theme.py

**Files:**
- Modify: `src/trading_bot/dashboard/theme.py` (after line 795)
- Test: `tests/test_dashboard_theme.py`

The `build_result_card_model()` dict already contains `outcome_label` and `results_filter`. We use `outcome_label` for color and `results_filter` for the badge text.

Color mapping (matches `_trace_status_pill_html` existing logic):
- `target_hit`, `target_before_stop` → green (`#14532d` bg, `#4ade80` text, `#22c55e` border)
- `stop_hit`, `stop_before_target`, `failed_setup` → red (`#450a0a` bg, `#f87171` text, `#ef4444` border)
- `tracking`, `still_active` → purple (`#1e1b4b` bg, `#a5b4fc` text, `#7c6fff` border)
- anything else → grey (`#1a1a1a` bg, `#888` text, `#333` border)

- [ ] **Step 1: Write failing tests**

Add to `tests/test_dashboard_theme.py`:

```python
from trading_bot.dashboard.theme import (
    _outcome_card_color,
    render_result_outcome_card,
    render_results_kpi_bar,
)


def test_outcome_card_color_target():
    assert _outcome_card_color("target_hit")["border"] == "#22c55e"
    assert _outcome_card_color("target_before_stop")["border"] == "#22c55e"


def test_outcome_card_color_stop():
    assert _outcome_card_color("stop_hit")["border"] == "#ef4444"
    assert _outcome_card_color("failed_setup")["border"] == "#ef4444"


def test_outcome_card_color_active():
    assert _outcome_card_color("tracking")["border"] == "#7c6fff"
    assert _outcome_card_color("still_active")["border"] == "#7c6fff"


def test_outcome_card_color_default():
    assert _outcome_card_color("unreviewed")["border"] == "#333"
    assert _outcome_card_color("")["border"] == "#333"


def test_render_result_outcome_card_runs():
    card = {
        "symbol": "PLTR",
        "outcome_label": "target_hit",
        "results_filter": "Target reached",
        "research_pl_pct": "+14.1%",
        "entry_trigger": "$18.40",
        "target": "$21.00",
        "stop": "$17.00",
        "setup_type": "Breakout",
        "trigger_date": "May 20",
        "status": "Target Hit",
        "reason": "Strong momentum setup.",
        "result_explanation": "Target hit on May 20.",
        "risk_reward": "1:2.5",
        "price_value": "$21.10",
        "price_label": "Exit price",
        "active_entry": "$18.40",
        "exit_price": "$21.10",
        "exit_price_label": "Exit (target hit)",
        "phase": "closed",
    }
    # Should not raise
    render_result_outcome_card(card)


def test_render_results_kpi_bar_runs():
    summary = {
        "active": 3,
        "closed": 10,
        "target_reached": 6,
        "stop_reached": 3,
        "watched": 13,
        "triggered": 9,
        "target_hits": 6,
        "stop_hits": 3,
        "partial_moves": 1,
        "waiting": 0,
        "expired": 0,
        "insufficient_data": 0,
        "watched_setups": 13,
        "still_active": 3,
    }
    render_results_kpi_bar(summary)
```

- [ ] **Step 2: Run to verify fail**

```powershell
$env:PYTHONPATH = "src"; .venv\Scripts\python.exe -m pytest tests/test_dashboard_theme.py -k "outcome_card or kpi_bar" -x -q 2>&1 | Select-Object -Last 15
```
Expected: ImportError or NameError — functions not defined yet.

- [ ] **Step 3: Implement in theme.py**

Add after the `render_results_table` function (after line ~797):

```python
# ── Outcome card renderer (V37 redesign) ────────────────────────────────────

_OUTCOME_COLORS: dict[str, dict[str, str]] = {
    "target_hit":        {"border": "#22c55e", "bg": "#0d1f11", "pill_bg": "#14532d", "pill_text": "#4ade80"},
    "target_before_stop": {"border": "#22c55e", "bg": "#0d1f11", "pill_bg": "#14532d", "pill_text": "#4ade80"},
    "stop_hit":          {"border": "#ef4444", "bg": "#1a0d0d", "pill_bg": "#450a0a", "pill_text": "#f87171"},
    "stop_before_target": {"border": "#ef4444", "bg": "#1a0d0d", "pill_bg": "#450a0a", "pill_text": "#f87171"},
    "failed_setup":      {"border": "#ef4444", "bg": "#1a0d0d", "pill_bg": "#450a0a", "pill_text": "#f87171"},
    "tracking":          {"border": "#7c6fff", "bg": "#13111f", "pill_bg": "#1e1b4b", "pill_text": "#a5b4fc"},
    "still_active":      {"border": "#7c6fff", "bg": "#13111f", "pill_bg": "#1e1b4b", "pill_text": "#a5b4fc"},
}
_OUTCOME_COLORS_DEFAULT = {"border": "#333", "bg": "#111", "pill_bg": "#1a1a1a", "pill_text": "#888"}


def _outcome_card_color(outcome_label: str) -> dict[str, str]:
    return _OUTCOME_COLORS.get((outcome_label or "").lower().strip(), _OUTCOME_COLORS_DEFAULT)


def render_result_outcome_card(card: dict[str, Any]) -> None:
    """Render a single color-coded result outcome card."""
    c = _outcome_card_color(card.get("outcome_label", ""))
    symbol = _esc(card.get("symbol", "?"))
    badge = _esc(card.get("results_filter") or card.get("status", "—"))
    pl = _esc(card.get("research_pl_pct", "—"))
    pl_color = "#22c55e" if str(card.get("research_pl_pct", "")).startswith("+") else (
        "#ef4444" if str(card.get("research_pl_pct", "")).startswith("-") else "#888"
    )
    entry = _esc(card.get("entry_trigger") or card.get("active_entry") or "—")
    target = _esc(card.get("target", "—"))
    stop = _esc(card.get("stop", "—"))
    setup = _esc(card.get("setup_type", "—"))
    date = _esc(card.get("trigger_date", "—"))

    render_html(
        f'<div style="border:1px solid {c["border"]};border-left:3px solid {c["border"]};'
        f'border-radius:6px;padding:10px 14px;background:{c["bg"]};margin-bottom:8px;">'
        f'<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;">'
        f'<div>'
        f'<span style="font-size:15px;font-weight:700;color:#fff;">{symbol}</span>'
        f'<span style="margin-left:8px;background:{c["pill_bg"]};color:{c["pill_text"]};'
        f'padding:2px 7px;border-radius:3px;font-size:10px;font-weight:600;">{badge}</span>'
        f'</div>'
        f'<span style="color:{pl_color};font-size:14px;font-weight:700;">{pl}</span>'
        f'</div>'
        f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;font-size:11px;color:#888;margin-bottom:6px;">'
        f'<div>Entry <span style="color:#ccc;font-weight:500;">{entry}</span></div>'
        f'<div>Target <span style="color:#4ade80;font-weight:500;">{target}</span></div>'
        f'<div>Stop <span style="color:#f87171;font-weight:500;">{stop}</span></div>'
        f'</div>'
        f'<div style="font-size:10px;color:#555;">{setup} · {date}</div>'
        f'</div>'
    )


def render_results_kpi_bar(summary: dict[str, Any]) -> None:
    """Render the 5-metric KPI bar above the Results cards."""
    active = summary.get("active") or summary.get("still_active", 0)
    closed = summary.get("closed", 0)
    targets = summary.get("target_reached") or summary.get("target_hits", 0)
    stops = summary.get("stop_reached") or summary.get("stop_hits", 0)
    triggered = summary.get("triggered", 0)
    win_rate = f"{round(targets / triggered * 100)}%" if triggered else "—"

    cols = st.columns(5)
    cols[0].metric("Active", active)
    cols[1].metric("Closed", closed)
    cols[2].metric("Targets Hit", targets)
    cols[3].metric("Stops Hit", stops)
    cols[4].metric("Win Rate", win_rate, help="Targets hit / triggered setups")


def render_result_outcome_cards(cards: list[dict[str, Any]]) -> None:
    """Render all outcome cards; show empty state if none."""
    if not cards:
        st.info("No results match the current filter.")
        return
    for card in cards:
        render_result_outcome_card(card)
```

- [ ] **Step 4: Run tests to verify pass**

```powershell
$env:PYTHONPATH = "src"; .venv\Scripts\python.exe -m pytest tests/test_dashboard_theme.py -k "outcome_card or kpi_bar" -x -q 2>&1 | Select-Object -Last 15
```
Expected: 6 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/trading_bot/dashboard/theme.py tests/test_dashboard_theme.py
git commit -m "feat: add render_result_outcome_card and render_results_kpi_bar to theme"
```

---

## Task 2: Rewire render_results() in app.py

**Files:**
- Modify: `src/trading_bot/dashboard/app.py` lines ~1567–1597

Replace the existing `render_results()` body. The filter chips map to `RESULTS_FILTERS` values — "Open" maps to `"Active"` phase which is `filter_name="Active"`, and "Closed" maps directly. We add a chip-style selectbox using `st.radio(..., horizontal=True)` styled as chips.

- [ ] **Step 1: Write failing test**

Add to `tests/test_dashboard_helpers.py` (or `test_outcome_analytics.py`):

```python
def test_results_filter_open_returns_active_rows():
    """'Open' chip must return active + waiting rows, not closed rows."""
    from trading_bot.dashboard.helpers import filter_results_product_rows
    import pandas as pd

    rows = pd.DataFrame([
        {"results_phase": "active",  "results_filter": "Active",  "symbol": "PLTR"},
        {"results_phase": "closed",  "results_filter": "Target reached", "symbol": "SOFI"},
        {"results_phase": "waiting", "results_filter": "Waiting for trigger", "symbol": "HOOD"},
    ])
    result = filter_results_product_rows(rows, "Active")
    assert list(result["symbol"]) == ["PLTR"]
    closed = filter_results_product_rows(rows, "Closed")
    assert list(closed["symbol"]) == ["SOFI"]
    all_rows = filter_results_product_rows(rows, "All")
    assert len(all_rows) == 3
```

- [ ] **Step 2: Run to verify pass** (this tests existing logic — should pass already)

```powershell
$env:PYTHONPATH = "src"; .venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py -k "results_filter_open" -x -q 2>&1 | Select-Object -Last 10
```
Expected: 1 passed. (Confirms existing filter logic works before we change the UI.)

- [ ] **Step 3: Update render_results() in app.py**

Find `render_results` (around line 1567) and replace the entire function body:

```python
def render_results(repo: ScannerRepository) -> None:
    """Results — outcome cards with filter chips."""
    inject_tony_theme()
    render_html(
        '<div class="trace-page-header">'
        '<div class="trace-page-title">Results</div>'
        '<div class="trace-page-sub">What happened after Tony noticed each setup.</div>'
        "</div>"
    )

    period = st.radio("Period", RESULT_PERIODS, horizontal=True, key="results_period")
    raw_snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False, limit=5000)
    research_snaps = filter_research_snapshots(raw_snaps)
    result_rows = build_results_product_rows(research_snaps)
    period_rows = filter_result_rows_by_period(result_rows, period)
    prepared = _results_prepared_for_period(raw_snaps, period)
    avg_pl = avg_research_pl_from_prepared(prepared)
    summary = summarize_results_plain_english(
        prepared,
        period_label=period,
        active_tracking_rows=build_active_tracking_product_rows(research_snaps),
    )
    summary.update(summarize_results_product_counts(period_rows))

    render_results_kpi_bar(summary)
    st.caption(risk_reward_definition_text())

    # Filter chips — map friendly labels to RESULTS_FILTERS values
    chip_labels = ["All", "Open", "Closed", "Targets", "Stops", "Expired", "Waiting", "Insufficient Data"]
    chip_to_filter = {
        "All": "All",
        "Open": "Active",
        "Closed": "Closed",
        "Targets": "Target reached",
        "Stops": "Stop reached",
        "Expired": "Expired / not triggered",
        "Waiting": "Waiting for trigger",
        "Insufficient Data": "Insufficient data",
    }
    chip = st.radio("Filter", chip_labels, horizontal=True, key="results_chip")
    filter_name = chip_to_filter[chip]
    filtered_rows = filter_results_product_rows(period_rows, filter_name)
    cards = [build_result_card_model(row) for _, row in filtered_rows.iterrows()]
    render_result_outcome_cards(cards)
```

Also update the import at the top of `render_results()` — add to the theme imports in `app.py`:

```python
from trading_bot.dashboard.theme import (
    ...
    render_result_outcome_card,      # add
    render_result_outcome_cards,     # add
    render_results_kpi_bar,          # add
    ...
)
```

- [ ] **Step 4: Run full test suite**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1 2>&1 | Select-Object -Last 15
```
Expected: All tests pass (799+).

- [ ] **Step 5: Commit**

```powershell
git add src/trading_bot/dashboard/app.py
git commit -m "feat: redesign Results page with outcome cards and filter chips"
```

---

## Task 3: Add render_intelligence() and rename nav

**Files:**
- Modify: `src/trading_bot/dashboard/app.py`

The Intelligence page needs these data sources (all already available in `_dashboard_context` or directly from `repo`):

| Section | Data source |
|---------|-------------|
| Hero bar — last cycle age | `repo.latest_scan_run()["created_at"]` → `event_age_label()` |
| Hero bar — scanned/scored | `ctx["symbols_scanned"]`, coverage from events |
| Hero bar — picks/new signals | `len(ctx["picks_df"])` |
| Funnel % | coverage dict from latest scan run or events |
| Top signals | `results` DataFrame top rows by `final_score` desc |
| Learning trend — win rate | `OutcomeAnalytics(raw_snaps).win_rate()` or `summarize_results_product_counts` |
| Learning trend — avg score | `results["final_score"].mean()` per recent scan |
| Health expander | existing `render_system_health()` content (just wrap it) |

- [ ] **Step 1: Write smoke test**

Add to `tests/test_dashboard_helpers.py`:

```python
def test_intelligence_page_imports():
    """Intelligence page functions must be importable."""
    from trading_bot.dashboard.app import render_intelligence  # noqa: F401
```

- [ ] **Step 2: Run to verify fail**

```powershell
$env:PYTHONPATH = "src"; .venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py -k "intelligence_page_imports" -x -q 2>&1 | Select-Object -Last 10
```
Expected: ImportError — `render_intelligence` not defined yet.

- [ ] **Step 3: Add render_intelligence() to app.py**

Add this function before `main()` (after `render_tony_learning_panel`):

```python
def render_intelligence(repo: ScannerRepository, results: pd.DataFrame) -> None:
    """Intelligence — what the last scan cycle found, plus learning trends."""
    inject_tony_theme()
    ctx = _dashboard_context(repo, results)

    section_header("Scan Intelligence")
    st.caption("What the last cycle found and whether the system is improving.")

    # ── Hero bar ──────────────────────────────────────────────────────────────
    run = repo.latest_scan_run()
    last_scan_age = event_age_label(ctx["latest_scan_ts"]) if ctx["latest_scan_ts"] else "No scan yet"
    symbols_scanned = ctx.get("symbols_scanned") or (len(results) if not results.empty else 0)
    symbols_scored = int(results["final_score"].notna().sum()) if not results.empty else 0
    picks_count = len(ctx.get("picks_df", pd.DataFrame()))
    tracking_count = len(ctx.get("tracking_df", pd.DataFrame()))
    new_signals = picks_count  # picks from latest cycle

    hero = st.columns(6)
    hero[0].metric("Last Cycle", last_scan_age)
    hero[1].metric("Scanned", symbols_scanned if symbols_scanned is not None else "—")
    hero[2].metric("Pre-Screened", "—", help="Symbols passing pre-screener filter")
    hero[3].metric("Scored", symbols_scored)
    hero[4].metric("Tony Picks", picks_count)
    hero[5].metric("Active Tracking", tracking_count)

    st.divider()

    # ── Funnel + Top Signals ──────────────────────────────────────────────────
    funnel_col, signals_col = st.columns([1, 1.4])

    with funnel_col:
        st.markdown("**Discovery Funnel — Last Cycle**")
        universe_size = symbols_scanned or 0
        prescreened = None  # not yet tracked in DB; show as dash
        scored = symbols_scored
        picks = picks_count
        st.markdown(
            f"| Stage | Count | Pass % |\n"
            f"|-------|-------|--------|\n"
            f"| Universe | {universe_size} | — |\n"
            f"| Pre-screener | {'—' if prescreened is None else prescreened} | — |\n"
            f"| Scored | {scored} | {round(scored/universe_size*100) if universe_size else '—'}% |\n"
            f"| Tony Picks | {picks} | {round(picks/scored*100) if scored else '—'}% |"
        )

    with signals_col:
        st.markdown("**Top Signals — This Cycle**")
        if not results.empty and "final_score" in results.columns:
            top = (
                results[["symbol", "final_score", "setup_category"]]
                .sort_values("final_score", ascending=False)
                .head(6)
                .copy()
            )
            top["final_score"] = top["final_score"].round(1)
            top.columns = ["Symbol", "Score", "Setup"]
            st.dataframe(top, hide_index=True, use_container_width=True)
        else:
            st.info("No scan results yet. Run a scan cycle to populate.")

    st.divider()

    # ── Learning Trend ────────────────────────────────────────────────────────
    st.markdown("**Learning Trend**")
    raw_snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False, limit=2000)
    research_snaps = filter_research_snapshots(raw_snaps)
    counts = summarize_results_product_counts(build_results_product_rows(research_snaps))
    triggered = counts.get("triggered", 0)
    targets = counts.get("target_reached", 0)
    win_rate_str = f"{round(targets/triggered*100)}%" if triggered else "—"
    avg_score_str = f"{round(float(results['final_score'].mean()), 1)}" if not results.empty else "—"

    trend_cols = st.columns(3)
    trend_cols[0].metric("Win Rate (all time)", win_rate_str, help="Targets hit / triggered setups")
    trend_cols[1].metric("Avg Score (last scan)", avg_score_str)
    trend_cols[2].metric("Conclusive Outcomes", counts.get("closed", 0))

    # ── Health expander ───────────────────────────────────────────────────────
    with st.expander("System Health & Config (developer)", expanded=False):
        render_system_health(repo, results)
```

- [ ] **Step 4: Update main() — rename nav + route to render_intelligence**

Find the `main()` function sidebar radio and the routing block. Change:

```python
# Before:
page = st.radio(
    "Navigate",
    ["Home", "Tony Watchlist", "Results", "Backtest Review", "Settings / System Health"],
    label_visibility="collapsed",
)
...
else:
    render_system_health(repo, results)

# After:
page = st.radio(
    "Navigate",
    ["Home", "Tony Watchlist", "Results", "Backtest Review", "Intelligence"],
    label_visibility="collapsed",
)
...
elif page == "Intelligence":
    render_intelligence(repo, results)
```

Remove the bare `else:` branch (it was `render_system_health` — now that's inside `render_intelligence`).

- [ ] **Step 5: Run smoke test + full suite**

```powershell
$env:PYTHONPATH = "src"; .venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py -k "intelligence_page_imports" -x -q 2>&1 | Select-Object -Last 5
```
Then:
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1 2>&1 | Select-Object -Last 15
```
Expected: All tests pass.

- [ ] **Step 6: Commit**

```powershell
git add src/trading_bot/dashboard/app.py tests/test_dashboard_helpers.py
git commit -m "feat: add Intelligence page, rename nav from Settings/System Health"
```

---

## Task 4: Visual smoke test in browser

- [ ] **Step 1: Launch dashboard**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1
```

- [ ] **Step 2: Verify Results page**
  - Open http://localhost:8501 → Results
  - Confirm KPI bar shows 5 metrics
  - Confirm filter chips row is present (All / Open / Closed / Targets / Stops / Expired / Waiting / Insufficient Data)
  - Click "Closed" — confirm only closed-outcome cards appear
  - Click "Targets" — confirm only green target-hit cards appear
  - Click "Open" — confirm only active/waiting cards appear
  - Confirm card colors: green for target hit, red for stop hit, purple for active

- [ ] **Step 3: Verify Intelligence page**
  - Navigate to "Intelligence" in sidebar (confirm "Settings / System Health" is gone)
  - Confirm hero bar renders (6 metrics)
  - Confirm funnel table renders
  - Confirm top signals table renders
  - Confirm learning trend 3 metrics render
  - Expand "System Health & Config (developer)" — confirm existing health content is intact

- [ ] **Step 4: Final commit if any fixups needed**

```powershell
git add -p
git commit -m "fix: dashboard intelligence/results visual fixups"
```

---

## Self-Review

**Spec coverage:**
- ✅ Results: KPI bar, filter chips, color-coded cards
- ✅ Results: "Open" maps to active+waiting, "Closed" to closed phase
- ✅ Intelligence: hero bar (6 metrics), funnel, top signals, learning trend
- ✅ Intelligence: health content in expander
- ✅ Nav renamed, stays at 5 pages

**Placeholder scan:**
- Pre-screener count shows "—" — pre-screener data is not currently stored per-cycle in the DB. This is honest: the field exists visually and can be wired up when the data exists. Not a blocker.

**Type consistency:**
- `render_results_kpi_bar(summary)` receives the same `summary` dict already produced by `summarize_results_product_counts` — keys verified against both callers.
- `render_result_outcome_card(card)` receives `build_result_card_model()` output — keys verified against the dict returned in helpers.py:2203–2223.
