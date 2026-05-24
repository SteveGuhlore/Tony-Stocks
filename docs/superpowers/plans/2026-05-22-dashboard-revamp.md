# Dashboard Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 5-tab inconsistent dashboard with a uniform 4-tab Professional Slate design (Today / Watchlist / Outcomes / Research).

**Architecture:** Add `render_compact_card()` to `theme.py` as the single card renderer used everywhere. Rewrite the 4 page functions in `app.py` using consistent HTML patterns and the Professional Slate color tokens. Remove old page dispatchers.

**Tech Stack:** Streamlit, custom HTML via `render_html()`, existing `_dashboard_context()` for data, existing `ScannerRepository`.

**Spec:** `docs/superpowers/specs/2026-05-22-dashboard-revamp-design.md`

---

## Color Reference (copy these into code — do not invent new colors)

```python
# Professional Slate tokens
_BG_BASE    = "#0f172a"
_BG_SURFACE = "#1e293b"
_BG_HEADER  = "#111827"
_BORDER     = "#1f2937"
_TEXT_PRI   = "#f1f5f9"
_TEXT_SEC   = "#64748b"
_TEXT_MUTED = "#475569"
_BLUE       = "#3b82f6"
_BLUE_LIGHT = "#93c5fd"
_VIOLET     = "#8b5cf6"
_VIOLET_LT  = "#a5b4fc"
_GREEN      = "#34d399"
_GREEN_DARK = "#22c55e"
_RED        = "#ef4444"
_AMBER      = "#fbbf24"

# Left-border and badge colors by status key
BORDER_BY_STATUS = {
    "watching":    "#3b82f6",
    "active":      "#34d399",
    "triggered":   "#34d399",
    "pending":     "#8b5cf6",
    "target_hit":  "#22c55e",
    "target_before_stop": "#22c55e",
    "stop_hit":    "#ef4444",
    "stop_before_target": "#ef4444",
    "failed_setup":"#ef4444",
}
BADGE_BY_STATUS = {
    # (bg, text, label)
    "watching":   ("#1e3a5f", "#93c5fd", "WATCHING"),
    "active":     ("#064e3b", "#6ee7b7", "ACTIVE"),
    "triggered":  ("#064e3b", "#6ee7b7", "TRIGGERED"),
    "pending":    ("#1e1b4b", "#a5b4fc", "PENDING"),
    "target_hit": ("#14532d", "#4ade80", "TARGET HIT"),
    "target_before_stop": ("#14532d", "#4ade80", "TARGET HIT"),
    "stop_hit":   ("#450a0a", "#f87171", "STOP HIT"),
    "stop_before_target": ("#450a0a", "#f87171", "STOP HIT"),
    "failed_setup":("#450a0a", "#f87171", "FAILED"),
}
```

---

### Task 1: Add `render_compact_card()` to theme.py + tests

**Files:**
- Modify: `src/trading_bot/dashboard/theme.py` — add after `render_result_outcome_cards` (~line 900)
- Modify: `tests/test_dashboard_theme.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_dashboard_theme.py`:

```python
class TestRenderCompactCard:
    def _make_card(self, status="watching", headline_right="$18.40", detail_line="Trigger: close > $18.80"):
        return {
            "symbol": "PLTR",
            "setup_type": "Breakout",
            "status": status,
            "status_label": "WATCHING",
            "headline_right": headline_right,
            "detail_line": detail_line,
            "border_color": "#3b82f6",
            "badge_bg": "#1e3a5f",
            "badge_text_color": "#93c5fd",
        }

    def test_watching_card_calls_st_markdown(self):
        card = self._make_card(status="watching")
        with patch("trading_bot.dashboard.theme.st") as mock_st:
            from trading_bot.dashboard.theme import render_compact_card
            render_compact_card(card)
            mock_st.markdown.assert_called_once()
            html = mock_st.markdown.call_args[0][0]
            assert "#3b82f6" in html
            assert "PLTR" in html
            assert "WATCHING" in html

    def test_active_card_shows_pl(self):
        card = self._make_card(status="active", headline_right="+8.3%")
        card.update({"border_color": "#34d399", "badge_bg": "#064e3b",
                     "badge_text_color": "#6ee7b7", "status_label": "ACTIVE"})
        with patch("trading_bot.dashboard.theme.st") as mock_st:
            from trading_bot.dashboard.theme import render_compact_card
            render_compact_card(card)
            html = mock_st.markdown.call_args[0][0]
            assert "#34d399" in html
            assert "+8.3%" in html

    def test_target_hit_card(self):
        card = self._make_card(status="target_hit", headline_right="+14.1%")
        card.update({"border_color": "#22c55e", "badge_bg": "#14532d",
                     "badge_text_color": "#4ade80", "status_label": "TARGET HIT"})
        with patch("trading_bot.dashboard.theme.st") as mock_st:
            from trading_bot.dashboard.theme import render_compact_card
            render_compact_card(card)
            html = mock_st.markdown.call_args[0][0]
            assert "#22c55e" in html

    def test_stop_hit_card(self):
        card = self._make_card(status="stop_hit", headline_right="-5.2%")
        card.update({"border_color": "#ef4444", "badge_bg": "#450a0a",
                     "badge_text_color": "#f87171", "status_label": "STOP HIT"})
        with patch("trading_bot.dashboard.theme.st") as mock_st:
            from trading_bot.dashboard.theme import render_compact_card
            render_compact_card(card)
            html = mock_st.markdown.call_args[0][0]
            assert "#ef4444" in html
```

- [ ] **Step 2: Run tests to confirm they fail**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_theme.py::TestRenderCompactCard -v
```

Expected: `AttributeError: module 'trading_bot.dashboard.theme' has no attribute 'render_compact_card'`

- [ ] **Step 3: Implement `render_compact_card()` in theme.py**

Add after `render_result_outcome_cards`:

```python
def render_compact_card(card: dict[str, Any]) -> None:
    """Unified compact row card — used by all four dashboard pages."""
    symbol = _esc(str(card.get("symbol", "")))
    setup_type = _esc(str(card.get("setup_type", "")))
    status_label = _esc(str(card.get("status_label", "")))
    headline_right = _esc(str(card.get("headline_right", "")))
    detail_line = _esc(str(card.get("detail_line", "")))
    border = card.get("border_color", "#334155")
    badge_bg = card.get("badge_bg", "#1e293b")
    badge_text = card.get("badge_text_color", "#94a3b8")

    st.markdown(
        f"""<div style="background:#1e293b;border:1px solid #1f2937;border-left:3px solid {border};"""
        f"""border-radius:6px;padding:10px 14px;margin-bottom:4px;">"""
        f"""<div style="display:flex;justify-content:space-between;align-items:center;">"""
        f"""<div style="display:flex;align-items:center;gap:10px;">"""
        f"""<span style="font-size:15px;font-weight:700;color:#f1f5f9;">{symbol}</span>"""
        f"""<span style="font-size:10px;color:#64748b;">{setup_type}</span>"""
        f"""<span style="background:{badge_bg};color:{badge_text};font-size:9px;padding:1px 7px;"""
        f"""border-radius:3px;font-weight:600;">{status_label}</span>"""
        f"""</div>"""
        f"""<span style="font-size:12px;font-weight:600;color:#f1f5f9;">{headline_right}</span>"""
        f"""</div>"""
        f"""<div style="margin-top:4px;font-size:10px;color:#475569;">{detail_line}</div>"""
        f"""</div>""",
        unsafe_allow_html=True,
    )
```

- [ ] **Step 4: Run tests to confirm pass**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_theme.py::TestRenderCompactCard -v
```

Expected: 4 PASSED

- [ ] **Step 5: Commit**

```powershell
git add src/trading_bot/dashboard/theme.py tests/test_dashboard_theme.py
git commit -m "feat: add render_compact_card() — unified compact row card for all dashboard pages"
```

---

### Task 2: Rewrite `main()` nav + add `render_today()`

**Files:**
- Modify: `src/trading_bot/dashboard/app.py`
- Modify: `tests/test_dashboard_helpers.py`

- [ ] **Step 1: Write failing smoke tests**

Add to `tests/test_dashboard_helpers.py`:

```python
def test_nav_has_four_tabs():
    import inspect
    from trading_bot.dashboard import app
    src = inspect.getsource(app.main)
    for tab in ["Today", "Watchlist", "Outcomes", "Research"]:
        assert tab in src, f"Tab '{tab}' missing from main()"
    for old_tab in ["Tony Watchlist", "Backtest Review", "Intelligence"]:
        assert old_tab not in src, f"Old tab '{old_tab}' still in main()"

def test_render_today_exists():
    from trading_bot.dashboard import app
    assert hasattr(app, "render_today"), "render_today() not defined"
```

- [ ] **Step 2: Run to confirm they fail**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_helpers.py::test_nav_has_four_tabs tests/test_dashboard_helpers.py::test_render_today_exists -v
```

Expected: FAIL

- [ ] **Step 3: Rewrite `main()` in app.py**

Replace the existing `main()` function (currently the last function before `if __name__ == "__main__":`) with:

```python
def main() -> None:
    repo = repository()
    results = latest_results(repo)
    inject_tony_theme()
    with st.sidebar:
        render_html(
            '<div class="trace-brand">'
            '<span class="trace-brand-icon">T</span>'
            "Tony Stocks"
            "</div>"
            '<div class="trace-brand-sub">Research terminal</div>'
        )
        st.divider()
        page = st.radio(
            "Navigate",
            ["Today", "Watchlist", "Outcomes", "Research"],
            label_visibility="collapsed",
        )
    if page == "Today":
        render_today(repo, results)
    elif page == "Watchlist":
        render_watchlist(repo, results)
    elif page == "Outcomes":
        render_outcomes(repo)
    elif page == "Research":
        render_research(repo, results)
```

- [ ] **Step 4: Add `render_today()` in app.py**

Add the following function immediately before `main()`. It requires these imports already present at top of file: `datetime`, `pd`, `st`, `render_html`, `section_header`, `briefing_line`, `_esc`, `_dashboard_context`, `render_compact_card` (imported from theme).

```python
def render_today(repo: ScannerRepository, results: pd.DataFrame) -> None:
    import datetime as _dt
    from trading_bot.dashboard.theme import render_compact_card

    ctx = _dashboard_context(repo, results)
    picks_df: pd.DataFrame = ctx.get("picks_df", pd.DataFrame())
    tracking_df: pd.DataFrame = ctx.get("tracking_df", pd.DataFrame())
    latest_scan_ts = ctx.get("latest_scan_ts")
    win_rate = ctx.get("win_rate_pct", "—")

    scan_age_str = "—"
    status_label, status_bg, status_text = "READY", "#064e3b", "#6ee7b7"
    if latest_scan_ts:
        try:
            age = _dt.datetime.now() - pd.Timestamp(latest_scan_ts).to_pydatetime().replace(tzinfo=None)
            mins = int(age.total_seconds() / 60)
            scan_age_str = f"{mins}m ago" if mins < 60 else f"{mins // 60}h ago"
            if age.total_seconds() > 7200:
                status_label, status_bg, status_text = "STALE", "#3f1f04", "#fbbf24"
        except Exception:
            pass

    n_watching = len(picks_df) if not picks_df.empty else 0
    n_triggered = len(tracking_df) if not tracking_df.empty else 0

    render_html(
        f'<div style="background:#111827;border:1px solid #1f2937;border-radius:8px;'
        f'padding:10px 14px;margin-bottom:14px;">'
        f'<div style="display:flex;gap:8px;align-items:center;margin-bottom:8px;">'
        f'<span style="background:{status_bg};color:{status_text};font-size:9px;'
        f'padding:3px 10px;border-radius:12px;font-weight:600;">{status_label}</span>'
        f'<span style="background:#1e3a5f;color:#93c5fd;font-size:9px;'
        f'padding:3px 10px;border-radius:12px;">Scan {scan_age_str}</span>'
        f'</div>'
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;">'
        f'<div style="background:#0f172a;border:1px solid #1f2937;border-radius:6px;padding:8px 10px;">'
        f'<div style="font-size:16px;font-weight:700;color:#60a5fa;">{n_watching}</div>'
        f'<div style="font-size:9px;color:#64748b;">Watching</div></div>'
        f'<div style="background:#0f172a;border:1px solid #1f2937;border-radius:6px;padding:8px 10px;">'
        f'<div style="font-size:16px;font-weight:700;color:#34d399;">{n_triggered}</div>'
        f'<div style="font-size:9px;color:#64748b;">Triggered</div></div>'
        f'<div style="background:#0f172a;border:1px solid #1f2937;border-radius:6px;padding:8px 10px;">'
        f'<div style="font-size:16px;font-weight:700;color:#fbbf24;">—</div>'
        f'<div style="font-size:9px;color:#64748b;">Alerts</div></div>'
        f'<div style="background:#0f172a;border:1px solid #1f2937;border-radius:6px;padding:8px 10px;">'
        f'<div style="font-size:16px;font-weight:700;color:#f1f5f9;">{win_rate}</div>'
        f'<div style="font-size:9px;color:#64748b;">Win Rate</div></div>'
        f'</div></div>'
    )

    col_left, col_right = st.columns([1, 1.5])

    with col_left:
        section_header("Briefing")
        briefing_events = pd.DataFrame()
        if hasattr(repo, "load_events"):
            try:
                briefing_events = repo.load_events(event_type="agent_insight", limit=1)
            except Exception:
                pass
        if not briefing_events.empty:
            note = str(briefing_events.iloc[0].get("notes", ""))
            render_html(
                f'<div style="background:#1e293b;border:1px solid #1f2937;border-left:3px solid #8b5cf6;'
                f'border-radius:0 6px 6px 0;padding:10px 12px;font-size:10px;color:#94a3b8;'
                f'line-height:1.6;font-style:italic;">{_esc(note[:300])}</div>'
            )
        else:
            st.caption("No briefing available.")

        section_header("Review Today")
        items: list[str] = []
        if not tracking_df.empty:
            items.append(f"{len(tracking_df)} active position(s) — review stops")
        if not picks_df.empty:
            items.append(f"{len(picks_df)} setup(s) being watched")
        if not items:
            items.append("Nothing flagged for review today")
        review_html = "".join(
            f'<div style="font-size:10px;color:#94a3b8;line-height:2.0;">• {_esc(i)}</div>'
            for i in items
        )
        render_html(f'<div style="margin-top:6px;">{review_html}</div>')

    with col_right:
        section_header("Live Setups")
        any_setups = False

        if not tracking_df.empty:
            for _, row in tracking_df.iterrows():
                pl = row.get("research_pl_pct")
                pl_str = (f"+{pl:.1f}%" if isinstance(pl, float) and pl >= 0
                          else f"{pl:.1f}%" if isinstance(pl, float) else "—")
                render_compact_card({
                    "symbol": str(row.get("symbol", "")),
                    "setup_type": str(row.get("setup_type", "")),
                    "status": "active",
                    "status_label": "ACTIVE",
                    "headline_right": pl_str,
                    "detail_line": (f"Entry {row.get('entry_price','—')} · "
                                    f"Target {row.get('target','—')} · "
                                    f"Stop {row.get('stop','—')}"),
                    "border_color": "#34d399",
                    "badge_bg": "#064e3b",
                    "badge_text_color": "#6ee7b7",
                })
                any_setups = True

        if not picks_df.empty:
            for _, row in picks_df.iterrows():
                render_compact_card({
                    "symbol": str(row.get("symbol", "")),
                    "setup_type": str(row.get("setup_type", "")),
                    "status": "watching",
                    "status_label": "WATCHING",
                    "headline_right": f"Entry {row.get('entry_price','—')}",
                    "detail_line": str(row.get("entry_trigger", ""))[:80],
                    "border_color": "#3b82f6",
                    "badge_bg": "#1e3a5f",
                    "badge_text_color": "#93c5fd",
                })
                any_setups = True

        if not any_setups:
            st.caption("No active setups.")
```

- [ ] **Step 5: Run tests to confirm pass**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_helpers.py::test_nav_has_four_tabs tests/test_dashboard_helpers.py::test_render_today_exists -v
```

Expected: 2 PASSED

- [ ] **Step 6: Commit**

```powershell
git add src/trading_bot/dashboard/app.py tests/test_dashboard_helpers.py
git commit -m "feat: 4-tab nav + render_today() Split Hero layout"
```

---

### Task 3: Add `render_watchlist()` (unified picks + tracking with chip filter)

**Files:**
- Modify: `src/trading_bot/dashboard/app.py`
- Modify: `tests/test_dashboard_helpers.py`

- [ ] **Step 1: Write failing smoke test**

Add to `tests/test_dashboard_helpers.py`:

```python
def test_render_watchlist_exists():
    from trading_bot.dashboard import app
    assert hasattr(app, "render_watchlist"), "render_watchlist() not defined"
    import inspect
    src = inspect.getsource(app.render_watchlist)
    assert "render_compact_card" in src
```

- [ ] **Step 2: Run to confirm fail**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_helpers.py::test_render_watchlist_exists -v
```

- [ ] **Step 3: Add `render_watchlist()` in app.py** (add before `render_today`)

```python
def render_watchlist(repo: ScannerRepository, results: pd.DataFrame) -> None:
    from trading_bot.dashboard.theme import render_compact_card

    ctx = _dashboard_context(repo, results)
    picks_df: pd.DataFrame = ctx.get("picks_df", pd.DataFrame())
    tracking_df: pd.DataFrame = ctx.get("tracking_df", pd.DataFrame())

    st.markdown("#### Watchlist")
    chip = st.radio("Filter", ["All", "Watching", "Active", "Pending"],
                    horizontal=True, key="wl_chip")

    any_shown = False

    if chip in ("All", "Active") and not tracking_df.empty:
        section_header("Active")
        for _, row in tracking_df.iterrows():
            pl = row.get("research_pl_pct")
            pl_str = (f"+{pl:.1f}%" if isinstance(pl, float) and pl >= 0
                      else f"{pl:.1f}%" if isinstance(pl, float) else "—")
            render_compact_card({
                "symbol": str(row.get("symbol", "")),
                "setup_type": str(row.get("setup_type", "")),
                "status": "active",
                "status_label": "ACTIVE",
                "headline_right": pl_str,
                "detail_line": (f"Entry {row.get('entry_price','—')} · "
                                f"Target {row.get('target','—')} · "
                                f"Stop {row.get('stop','—')}"),
                "border_color": "#34d399",
                "badge_bg": "#064e3b",
                "badge_text_color": "#6ee7b7",
            })
            any_shown = True

    if chip in ("All", "Watching") and not picks_df.empty:
        watching = picks_df
        if "status" in picks_df.columns:
            watching = picks_df[~picks_df["status"].str.lower().isin(["pending"])]
        if not watching.empty:
            section_header("Watching")
            for _, row in watching.iterrows():
                render_compact_card({
                    "symbol": str(row.get("symbol", "")),
                    "setup_type": str(row.get("setup_type", "")),
                    "status": "watching",
                    "status_label": "WATCHING",
                    "headline_right": f"Entry {row.get('entry_price','—')}",
                    "detail_line": str(row.get("entry_trigger", ""))[:80],
                    "border_color": "#3b82f6",
                    "badge_bg": "#1e3a5f",
                    "badge_text_color": "#93c5fd",
                })
                any_shown = True

    if chip in ("All", "Pending") and not picks_df.empty and "status" in picks_df.columns:
        pending = picks_df[picks_df["status"].str.lower() == "pending"]
        if not pending.empty:
            section_header("Pending")
            for _, row in pending.iterrows():
                render_compact_card({
                    "symbol": str(row.get("symbol", "")),
                    "setup_type": str(row.get("setup_type", "")),
                    "status": "pending",
                    "status_label": "PENDING",
                    "headline_right": f"Entry {row.get('entry_price','—')}",
                    "detail_line": str(row.get("entry_trigger", ""))[:80],
                    "border_color": "#8b5cf6",
                    "badge_bg": "#1e1b4b",
                    "badge_text_color": "#a5b4fc",
                })
                any_shown = True

    if not any_shown:
        st.info("No setups match the selected filter.")
```

- [ ] **Step 4: Run test**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_helpers.py::test_render_watchlist_exists -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/trading_bot/dashboard/app.py tests/test_dashboard_helpers.py
git commit -m "feat: render_watchlist() — unified chip-filtered compact card list"
```

---

### Task 4: Add `render_outcomes()` (replaces render_results)

**Files:**
- Modify: `src/trading_bot/dashboard/app.py`
- Modify: `tests/test_dashboard_helpers.py`

- [ ] **Step 1: Write failing smoke test**

Add to `tests/test_dashboard_helpers.py`:

```python
def test_render_outcomes_exists():
    from trading_bot.dashboard import app
    assert hasattr(app, "render_outcomes"), "render_outcomes() not defined"
    import inspect
    src = inspect.getsource(app.render_outcomes)
    assert "render_compact_card" in src
```

- [ ] **Step 2: Run to confirm fail**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_helpers.py::test_render_outcomes_exists -v
```

- [ ] **Step 3: Add `render_outcomes()` in app.py** (add before `render_watchlist`)

```python
def render_outcomes(repo: ScannerRepository) -> None:
    from trading_bot.dashboard.theme import render_compact_card, render_results_kpi_bar
    from trading_bot.dashboard.helpers import build_result_card_model

    raw_snaps = _load_research_snapshots(repo)
    if raw_snaps.empty:
        st.info("No outcome data yet.")
        return

    prepared = _results_prepared_for_period(raw_snaps, "All")
    cards = [build_result_card_model(row) for _, row in prepared.iterrows()]

    n_active  = sum(1 for c in cards if str(c.get("phase","")).lower() in ("active","triggered"))
    n_closed  = sum(1 for c in cards if str(c.get("phase","")).lower() == "closed")
    n_targets = sum(1 for c in cards if str(c.get("outcome_label","")).lower() in ("target_hit","target_before_stop"))
    n_stops   = sum(1 for c in cards if str(c.get("outcome_label","")).lower() in ("stop_hit","stop_before_target","failed_setup"))
    win_rate  = f"{round(n_targets / n_closed * 100)}%" if n_closed > 0 else "—"
    render_results_kpi_bar({
        "n_active": n_active, "n_closed": n_closed,
        "n_targets": n_targets, "n_stops": n_stops, "win_rate_pct": win_rate,
    })

    chip = st.radio("Filter", ["All", "Open", "Targets", "Stops"],
                    horizontal=True, key="outcomes_chip")
    chip_filter_map: dict[str, list[str]] = {
        "All":     [],
        "Open":    ["active", "triggered"],
        "Targets": ["target_hit", "target_before_stop"],
        "Stops":   ["stop_hit", "stop_before_target", "failed_setup"],
    }
    active_filters = chip_filter_map[chip]

    BORDER = {
        "target_hit": "#22c55e", "target_before_stop": "#22c55e",
        "stop_hit": "#ef4444", "stop_before_target": "#ef4444", "failed_setup": "#ef4444",
        "active": "#34d399", "triggered": "#34d399",
    }
    BADGE_BG = {
        "target_hit": "#14532d", "target_before_stop": "#14532d",
        "stop_hit": "#450a0a", "stop_before_target": "#450a0a", "failed_setup": "#450a0a",
        "active": "#064e3b", "triggered": "#064e3b",
    }
    BADGE_TEXT = {
        "target_hit": "#4ade80", "target_before_stop": "#4ade80",
        "stop_hit": "#f87171", "stop_before_target": "#f87171", "failed_setup": "#f87171",
        "active": "#6ee7b7", "triggered": "#6ee7b7",
    }
    BADGE_LABEL = {
        "target_hit": "TARGET HIT", "target_before_stop": "TARGET HIT",
        "stop_hit": "STOP HIT", "stop_before_target": "STOP HIT", "failed_setup": "FAILED",
        "active": "ACTIVE", "triggered": "TRIGGERED",
    }

    shown = 0
    for card in cards:
        ol = str(card.get("outcome_label", "")).lower().replace(" ", "_")
        phase = str(card.get("phase", "")).lower()
        key = ol if ol in BORDER else phase
        if active_filters and ol not in active_filters and phase not in active_filters:
            continue
        pl = card.get("research_pl_pct")
        pl_str = (f"+{pl:.1f}%" if isinstance(pl, float) and pl >= 0
                  else f"{pl:.1f}%" if isinstance(pl, float) else "—")
        closed_date = str(card.get("trigger_date") or card.get("last_event_date") or "")
        render_compact_card({
            "symbol": card.get("symbol", ""),
            "setup_type": card.get("setup_type", ""),
            "status": key,
            "status_label": BADGE_LABEL.get(key, key.upper()),
            "headline_right": pl_str,
            "detail_line": (f"Entry {card.get('entry_price','—')} · "
                            f"Target {card.get('target','—')} · "
                            f"Stop {card.get('stop','—')}"
                            + (f" · {closed_date}" if closed_date else "")),
            "border_color": BORDER.get(key, "#334155"),
            "badge_bg": BADGE_BG.get(key, "#1e293b"),
            "badge_text_color": BADGE_TEXT.get(key, "#94a3b8"),
        })
        shown += 1

    if shown == 0:
        st.info("No outcomes match the selected filter.")
```

- [ ] **Step 4: Run test**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_helpers.py::test_render_outcomes_exists -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/trading_bot/dashboard/app.py tests/test_dashboard_helpers.py
git commit -m "feat: render_outcomes() — compact card results with KPI bar and chip filter"
```

---

### Task 5: Add `render_research()` (backtest + intelligence + system health)

**Files:**
- Modify: `src/trading_bot/dashboard/app.py`
- Modify: `tests/test_dashboard_helpers.py`

- [ ] **Step 1: Write failing smoke test**

Add to `tests/test_dashboard_helpers.py`:

```python
def test_render_research_exists():
    from trading_bot.dashboard import app
    assert hasattr(app, "render_research"), "render_research() not defined"
```

- [ ] **Step 2: Run to confirm fail**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_helpers.py::test_render_research_exists -v
```

- [ ] **Step 3: Add `render_research()` in app.py** (add before `render_outcomes`)

```python
def render_research(repo: ScannerRepository, results: pd.DataFrame) -> None:
    ctx = _dashboard_context(repo, results)

    st.markdown("#### Research")

    n_scanned   = ctx.get("symbols_scanned") or 0
    picks_df    = ctx.get("picks_df", pd.DataFrame())
    n_candidates = ctx.get("n_candidates") or 0
    n_picks     = len(picks_df) if not picks_df.empty else 0

    render_html(
        f'<div style="background:#111827;border:1px solid #1f2937;border-radius:8px;'
        f'padding:10px 14px;margin-bottom:14px;display:flex;align-items:center;">'
        f'<div style="flex:1;text-align:center;">'
        f'<div style="font-size:18px;font-weight:700;color:#60a5fa;">{n_scanned}</div>'
        f'<div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.06em;">Scanned</div>'
        f'</div>'
        f'<div style="color:#334155;font-size:18px;padding:0 8px;">›</div>'
        f'<div style="flex:1;text-align:center;">'
        f'<div style="font-size:18px;font-weight:700;color:#8b5cf6;">{n_candidates}</div>'
        f'<div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.06em;">Candidates</div>'
        f'</div>'
        f'<div style="color:#334155;font-size:18px;padding:0 8px;">›</div>'
        f'<div style="flex:1;text-align:center;">'
        f'<div style="font-size:18px;font-weight:700;color:#34d399;">{n_picks}</div>'
        f'<div style="font-size:9px;color:#64748b;text-transform:uppercase;letter-spacing:.06em;">Picks</div>'
        f'</div>'
        f'</div>'
    )

    section_header("Top Signals — Last Scan")
    scan_df = ctx.get("scan_df", pd.DataFrame())
    if not scan_df.empty:
        show_cols = [c for c in ["symbol", "score", "setup_type", "entry_trigger"] if c in scan_df.columns]
        st.dataframe(scan_df[show_cols].head(5), use_container_width=True, hide_index=True)
    else:
        st.caption("No scan data available.")

    section_header("Backtest Review")
    render_backtest_review(repo)

    section_header("Agent Insights")
    render_agent_insights()

    with st.expander("Developer: System Health & Config"):
        render_system_health(repo, results)
```

- [ ] **Step 4: Run test**

```powershell
$env:PYTHONPATH = "src"; python -m pytest tests/test_dashboard_helpers.py::test_render_research_exists -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```powershell
git add src/trading_bot/dashboard/app.py tests/test_dashboard_helpers.py
git commit -m "feat: render_research() — funnel + backtest + intelligence + system health"
```

---

### Task 6: Remove old page dispatchers + full test run

**Files:**
- Modify: `src/trading_bot/dashboard/app.py`

- [ ] **Step 1: Check for stray callers of old functions**

```powershell
$env:PYTHONPATH = "src"
Select-String -Path "src\trading_bot\dashboard\app.py","tests\*.py" -Pattern "render_home\b|render_tony_watchlist\b|render_results\b|render_intelligence\b" | Format-Table LineNumber, Line -AutoSize
```

Only delete a function if no callers remain outside `main()`. The new `main()` only calls `render_today`, `render_watchlist`, `render_outcomes`, `render_research` — so the old dispatchers are safe to delete.

- [ ] **Step 2: Delete old page dispatcher functions from app.py**

Delete these four functions (keep all their helpers — they are called by the new pages):
- `render_home()` (replaced by `render_today`)
- `render_tony_watchlist()` (replaced by `render_watchlist`)
- `render_results()` (replaced by `render_outcomes`)
- `render_intelligence()` (replaced by `render_research`)

Do **not** delete: `render_tony_picks`, `render_active_tracking`, `render_outcome_analytics`, `render_system_health`, `render_backtest_review`, `render_agent_insights`, or any helper.

- [ ] **Step 3: Run full test suite**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

Expected: All previously passing tests pass. New tests pass. No regressions.

- [ ] **Step 4: Verify dashboard visually**

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1
```

Open `http://localhost:8501` and confirm:
- Sidebar shows: Today / Watchlist / Outcomes / Research
- Today: header band with KPIs, two columns (briefing left, setups right)
- Watchlist: chip filter (All/Watching/Active/Pending), compact row cards
- Outcomes: KPI bar, chip filter, compact cards with green/red borders
- Research: funnel strip, signals table, backtest, insights, health expander

- [ ] **Step 5: Commit cleanup**

```powershell
git add src/trading_bot/dashboard/app.py
git commit -m "refactor: remove old page dispatchers (render_home, render_tony_watchlist, render_results, render_intelligence)"
```

- [ ] **Step 6: Update AGENT_STATE.md**

Open `AGENT_STATE.md` and update:
- Version to V37
- Page structure: list Today / Watchlist / Outcomes / Research
- Note: dashboard revamp complete, uniform Professional Slate design

```powershell
git add AGENT_STATE.md
git commit -m "docs: AGENT_STATE V37 — 4-tab dashboard revamp complete"
```
