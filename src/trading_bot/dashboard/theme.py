"""Streamlit-safe HTML/CSS theme for the Tony Stocks product dashboard."""
from __future__ import annotations

import html as html_module
from typing import Any

import pandas as pd
import streamlit as st

from trading_bot.dashboard.helpers import format_percent_or_missing, is_missing_scalar

_TONY_APP_CSS = """
<style>
/* ── Base: dark navy research terminal ─────────────────────────── */
[data-testid="stAppViewContainer"] {
  background: #080d1c;
}
[data-testid="stAppViewContainer"] > .main > .block-container {
  background: transparent;
}
[data-testid="stSidebar"] {
  background: #040810;
  border-right: 1px solid rgba(255,255,255,0.07);
}
.block-container {
  padding-top: 1.5rem;
  max-width: 1280px;
}
/* ── Sidebar brand ─────────────────────────────────────────────── */
.trace-brand {
  font-size: 1.1rem;
  font-weight: 800;
  color: #e2e8f0;
  letter-spacing: -0.01em;
  padding: 0.5rem 0 0.1rem 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}
.trace-brand-icon {
  display: inline-flex;
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: linear-gradient(135deg, #3b82f6 0%, #6366f1 100%);
  color: #fff;
  align-items: center;
  justify-content: center;
  font-size: 0.82rem;
  font-weight: 800;
}
.trace-brand-sub {
  font-size: 0.68rem;
  color: #475569;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  padding-bottom: 0.4rem;
}
/* ── Hero ──────────────────────────────────────────────────────── */
.tony-hero {
  border-radius: 18px;
  padding: 1.5rem 1.75rem;
  margin-bottom: 1.25rem;
  background: linear-gradient(135deg, #1e3a5f 0%, #1a2a5e 55%, #15194a 100%);
  color: #e2e8f0;
  border: 1px solid rgba(99,102,241,0.25);
  box-shadow: 0 8px 32px rgba(0,0,0,0.4);
}
.tony-hero-title {
  font-size: 1.6rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0 0 0.3rem 0;
  color: #f1f5f9;
}
.tony-hero-sub {
  font-size: 0.98rem;
  opacity: 0.85;
  margin: 0;
  color: #cbd5e1;
}
.tony-hero-badge {
  display: inline-block;
  margin-top: 0.75rem;
  padding: 0.26rem 0.72rem;
  border-radius: 999px;
  background: rgba(99,102,241,0.22);
  border: 1px solid rgba(99,102,241,0.38);
  font-size: 0.76rem;
  font-weight: 600;
  color: #a5b4fc;
}
/* ── Section header ────────────────────────────────────────────── */
.tony-section {
  font-size: 1.05rem;
  font-weight: 700;
  color: #e2e8f0;
  margin: 1.25rem 0 0.6rem 0;
  letter-spacing: -0.01em;
}
/* ── Stat grid ─────────────────────────────────────────────────── */
.tony-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 0.65rem;
  margin: 0.75rem 0 1rem 0;
}
.tony-stat-tile {
  border-radius: 14px;
  padding: 0.85rem 1rem;
  background: #111827;
  border: 1px solid rgba(255,255,255,0.07);
}
.tony-stat-tile-purple {
  background: linear-gradient(145deg, #1e1b4b 0%, #111827 100%);
  border-color: rgba(99,102,241,0.35);
}
.tony-stat-tile-blue {
  background: linear-gradient(145deg, #0c1d3b 0%, #111827 100%);
  border-color: rgba(59,130,246,0.35);
}
.tony-stat-tile-green {
  background: linear-gradient(145deg, #052e16 0%, #111827 100%);
  border-color: rgba(34,197,94,0.35);
}
.tony-stat-tile-amber {
  background: linear-gradient(145deg, #1c1003 0%, #111827 100%);
  border-color: rgba(245,158,11,0.35);
}
.tony-stat-label {
  font-size: 0.67rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #475569;
}
.tony-stat-value {
  font-size: 1.35rem;
  font-weight: 800;
  color: #f1f5f9;
  margin-top: 0.2rem;
  line-height: 1.2;
}
.tony-stat-hint {
  font-size: 0.71rem;
  color: #64748b;
  margin-top: 0.2rem;
}
/* ── Cards ─────────────────────────────────────────────────────── */
.tony-card {
  border-radius: 18px;
  padding: 1.2rem 1.4rem;
  margin-bottom: 0.9rem;
  background: #111827;
  border: 1px solid rgba(255,255,255,0.07);
  box-shadow: 0 4px 16px rgba(0,0,0,0.3);
}
.tony-card-preview {
  padding: 0.95rem 1.1rem;
}
.tony-preview-why {
  font-size: 0.9rem;
  margin: 0.4rem 0 0.5rem 0;
  padding: 0.5rem 0.65rem;
}
.tony-preview-pl {
  font-size: 1.05rem;
  font-weight: 800;
  text-align: right;
  white-space: nowrap;
}
.tony-card-track {
  border-left: 3px solid #3b82f6;
}
.tony-card-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.5rem;
}
.tony-card-symbol {
  font-size: 1.85rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: #f1f5f9;
  line-height: 1.1;
}
.tony-card-symbol-sm {
  font-size: 1.35rem;
  font-weight: 800;
  color: #f1f5f9;
}
.tony-pl-hero {
  font-size: 1.4rem;
  font-weight: 800;
  text-align: right;
}
.tony-pl-positive { color: #22c55e; }
.tony-pl-negative { color: #ef4444; }
.tony-pl-neutral  { color: #94a3b8; }
.tony-card-why {
  color: #94a3b8;
  font-size: 0.95rem;
  line-height: 1.5;
  margin: 0.6rem 0 0.8rem 0;
  padding: 0.7rem 0.85rem;
  background: #0d1526;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.05);
}
.tony-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin: 0.45rem 0 0.6rem 0;
}
.tony-metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(110px, 1fr));
  gap: 0.55rem;
  margin: 0.6rem 0 0.7rem 0;
}
.tony-metric {
  background: #0d1526;
  border-radius: 12px;
  padding: 0.55rem 0.7rem;
  border: 1px solid rgba(255,255,255,0.05);
}
.tony-metric-highlight {
  background: linear-gradient(145deg, #0c1d3b 0%, #0d1526 100%);
  border-color: rgba(59,130,246,0.2);
}
.tony-metric-label {
  font-size: 0.65rem;
  color: #475569;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 600;
}
.tony-metric-value {
  font-size: 1rem;
  font-weight: 700;
  color: #e2e8f0;
  margin-top: 0.15rem;
}
/* ── Pills ──────────────────────────────────────────────────────── */
.tony-pill {
  display: inline-block;
  padding: 0.24rem 0.65rem;
  border-radius: 999px;
  font-size: 0.73rem;
  font-weight: 600;
}
.tony-pill-positive { background: rgba(34,197,94,0.15);  color: #4ade80; border: 1px solid rgba(34,197,94,0.25); }
.tony-pill-negative { background: rgba(239,68,68,0.15);  color: #f87171; border: 1px solid rgba(239,68,68,0.25); }
.tony-pill-warning  { background: rgba(245,158,11,0.15); color: #fbbf24; border: 1px solid rgba(245,158,11,0.25); }
.tony-pill-risk     { background: rgba(249,115,22,0.15); color: #fb923c; border: 1px solid rgba(249,115,22,0.25); }
.tony-pill-info     { background: rgba(59,130,246,0.15); color: #60a5fa; border: 1px solid rgba(59,130,246,0.25); }
.tony-pill-purple   { background: rgba(99,102,241,0.15); color: #a78bfa; border: 1px solid rgba(99,102,241,0.25); }
.tony-pill-neutral  { background: rgba(100,116,139,0.12);color: #94a3b8; border: 1px solid rgba(100,116,139,0.2); }
/* ── Footnotes / disclaimers ───────────────────────────────────── */
.tony-footnote {
  font-size: 0.78rem;
  color: #475569;
  margin-top: 0.4rem;
  line-height: 1.4;
}
.tony-disclaimer {
  border-radius: 10px;
  padding: 0.65rem 0.85rem;
  background: rgba(245,158,11,0.08);
  border: 1px solid rgba(245,158,11,0.2);
  color: #fbbf24;
  font-size: 0.83rem;
  margin: 0.65rem 0;
}
.tony-results-banner {
  border-radius: 10px;
  padding: 0.75rem 1rem;
  background: rgba(245,158,11,0.08);
  border: 1px solid rgba(245,158,11,0.2);
  color: #fbbf24;
  font-weight: 600;
  margin-bottom: 0.9rem;
  font-size: 0.87rem;
}
.tony-briefing-line {
  font-size: 0.97rem;
  color: #64748b;
  margin: 0.35rem 0 0.8rem 0;
  line-height: 1.45;
}
/* ── TRACE Results page header ─────────────────────────────────── */
.trace-page-header { margin-bottom: 1rem; }
.trace-page-title {
  font-size: 1.75rem;
  font-weight: 800;
  color: #f1f5f9;
  margin: 0 0 0.2rem 0;
  letter-spacing: -0.02em;
}
.trace-page-sub { font-size: 0.87rem; color: #64748b; margin: 0; }
/* ── TRACE Results table ───────────────────────────────────────── */
.trace-results-table {
  background: #111827;
  border-radius: 14px;
  border: 1px solid rgba(255,255,255,0.07);
  overflow: hidden;
  margin-top: 0.75rem;
}
.trace-table-header {
  display: grid;
  grid-template-columns: 1.6fr 1.2fr 1.1fr 0.85fr 0.85fr 0.85fr 0.85fr 0.75fr 0.75fr 1.0fr 1.6fr;
  padding: 0.6rem 1.1rem;
  border-bottom: 1px solid rgba(255,255,255,0.07);
  background: rgba(255,255,255,0.025);
}
.trace-th {
  font-size: 0.63rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: #64748b;
}
.trace-table-row {
  display: grid;
  grid-template-columns: 1.6fr 1.2fr 1.1fr 0.85fr 0.85fr 0.85fr 0.85fr 0.75fr 0.75fr 1.0fr 1.6fr;
  padding: 0.85rem 1.1rem;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  align-items: start;
}
.trace-table-row:hover { background: rgba(255,255,255,0.025); }
.trace-table-row:last-child { border-bottom: none; }
.trace-symbol {
  font-size: 1.0rem;
  font-weight: 800;
  color: #f1f5f9;
  letter-spacing: -0.01em;
  line-height: 1.15;
}
.trace-company {
  font-size: 0.7rem;
  color: #334155;
  margin-top: 0.08rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.trace-setup-type { font-size: 0.79rem; color: #64748b; }
.trace-status-pill {
  display: inline-block;
  padding: 0.2rem 0.55rem;
  border-radius: 6px;
  font-size: 0.71rem;
  font-weight: 600;
  white-space: nowrap;
}
.trace-pill-blue   { background: rgba(59,130,246,0.14);  color: #60a5fa; border: 1px solid rgba(59,130,246,0.25); }
.trace-pill-green  { background: rgba(34,197,94,0.14);   color: #4ade80; border: 1px solid rgba(34,197,94,0.25); }
.trace-pill-red    { background: rgba(239,68,68,0.14);   color: #f87171; border: 1px solid rgba(239,68,68,0.25); }
.trace-pill-amber  { background: rgba(245,158,11,0.14);  color: #fbbf24; border: 1px solid rgba(245,158,11,0.25); }
.trace-pill-gray   { background: rgba(100,116,139,0.11); color: #94a3b8; border: 1px solid rgba(100,116,139,0.18); }
.trace-cell        { font-size: 0.81rem; color: #94a3b8; }
.trace-price-hit   { font-size: 0.81rem; color: #4ade80; font-weight: 600; }
.trace-price-stop  { font-size: 0.81rem; color: #f87171; font-weight: 600; }
.trace-pl-positive { color: #4ade80; font-weight: 700; font-size: 0.83rem; }
.trace-pl-negative { color: #f87171; font-weight: 700; font-size: 0.83rem; }
.trace-pl-neutral  { color: #64748b; font-size: 0.83rem; }
.trace-notes-cell  {
  font-size: 0.75rem; color: #64748b;
  overflow: hidden; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
}
.trace-empty-state {
  text-align: center; padding: 2.5rem;
  color: #64748b; font-size: 0.88rem;
}
.trace-disclaimer {
  font-size: 0.71rem; color: #475569;
  text-align: right; padding: 0.55rem 1.1rem;
  border-top: 1px solid rgba(255,255,255,0.04);
  font-style: italic;
}
</style>
"""

_PILL_CLASS = {
    "positive": "tony-pill-positive",
    "negative": "tony-pill-negative",
    "warning": "tony-pill-warning",
    "risk": "tony-pill-risk",
    "info": "tony-pill-info",
    "purple": "tony-pill-purple",
    "neutral": "tony-pill-neutral",
}

_STAT_TILE_CLASS = {
    "default": "",
    "purple": "tony-stat-tile-purple",
    "blue": "tony-stat-tile-blue",
    "green": "tony-stat-tile-green",
    "amber": "tony-stat-tile-amber",
    "info": "tony-stat-tile-blue",
    "neutral": "",
}


def _esc(text: str) -> str:
    return html_module.escape(str(text), quote=True)


def render_html(html: str) -> None:
    """Render a complete HTML fragment (theme cards, grids, sections)."""
    body = html.strip()
    if body:
        st.markdown(body, unsafe_allow_html=True)


def inject_tony_theme() -> None:
    st.markdown(_TONY_APP_CSS, unsafe_allow_html=True)


def build_stat_grid_html(items: list[tuple[str, str, str, str | None]]) -> str:
    """Build a complete stat-grid HTML fragment."""
    if not items:
        return '<div class="tony-stat-grid"></div>'
    cells: list[str] = []
    for label, value, tone, hint in items:
        tile_class = ("tony-stat-tile " + _STAT_TILE_CLASS.get(tone, "")).strip()
        hint_block = f'<div class="tony-stat-hint">{_esc(hint)}</div>' if hint else ""
        cells.append(
            f'<div class="{tile_class}">'
            f'<div class="tony-stat-label">{_esc(label)}</div>'
            f'<div class="tony-stat-value">{_esc(value)}</div>'
            f"{hint_block}"
            f"</div>"
        )
    return f'<div class="tony-stat-grid">{"".join(cells)}</div>'


def html_has_balanced_divs(fragment: str) -> bool:
    return fragment.count("<div") == fragment.count("</div>")


def pill_html(label: str, tone: str = "neutral") -> str:
    css_class = _PILL_CLASS.get(tone, "tony-pill-neutral")
    return f'<span class="tony-pill {css_class}">{_esc(label)}</span>'


def section_header(title: str) -> None:
    render_html(f'<div class="tony-section">{_esc(title)}</div>')


def briefing_line(text: str) -> None:
    render_html(f'<div class="tony-briefing-line">{_esc(text)}</div>')


def render_hero(*, real_data_only: bool) -> None:
    badge = "Real data only · Demo blocked" if real_data_only else "Check real-data-only settings"
    render_html(
        f'<div class="tony-hero">'
        f'<div class="tony-hero-title">Tony is watching the market.</div>'
        f'<div class="tony-hero-sub">Here is what Tony thinks matters right now.</div>'
        f'<div class="tony-hero-badge">{_esc(badge)}</div>'
        f"</div>"
    )


def render_stat_grid(items: list[tuple[str, str, str, str | None]]) -> None:
    render_html(build_stat_grid_html(items))


def _metric_html(label: str, value: str, *, highlight: bool = False) -> str:
    extra = " tony-metric-highlight" if highlight else ""
    return (
        f'<div class="tony-metric{extra}">'
        f'<div class="tony-metric-label">{_esc(label)}</div>'
        f'<div class="tony-metric-value">{_esc(value)}</div>'
        f"</div>"
    )


def _metrics_row_html(items: list[tuple[str, str, bool]]) -> str:
    cells = "".join(_metric_html(label, val, highlight=hi) for label, val, hi in items)
    return f'<div class="tony-metric-grid">{cells}</div>'


_HOME_WHY_MAX_LEN = 100


def _short_home_reason(text: str, *, max_len: int = _HOME_WHY_MAX_LEN) -> str:
    cleaned = str(text or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 3].rstrip() + "..."


def build_pick_preview_card_html(card: dict[str, str]) -> str:
    """Compact Home Tony Pick preview (full reasoning stays on Tony Picks tab)."""
    risk_tone = "risk" if "volatility" in card.get("risk_level", "").lower() else "neutral"
    pills = "".join([
        pill_html(card["tony_rating"], "purple"),
        pill_html(card["setup_type"], "info"),
        pill_html(f"Risk: {card['risk_level']}", risk_tone),
        pill_html(card["status"], card.get("status_tone", "neutral")),
    ])
    metrics = _metrics_row_html([
        ("Entry trigger", card["entry_trigger"], True),
        ("Active entry", card["active_entry"], False),
        (card.get("price_label", "Current price"), card["current_price"], False),
        ("Target", card["target"], False),
        ("Stop", card["stop"], False),
    ])
    return (
        f'<div class="tony-card tony-card-preview">'
        f'<div class="tony-card-symbol-sm">{_esc(card["symbol"])}</div>'
        f'<div class="tony-pill-row">{pills}</div>'
        f'<div class="tony-card-why tony-preview-why">{_esc(card.get("home_summary", card["why"]))}</div>'
        f"{metrics}"
        f"</div>"
    )


def render_pick_preview_card(card: dict[str, str]) -> None:
    render_html(build_pick_preview_card_html(card))


def render_pick_signal_card(card: dict[str, str]) -> None:
    risk_tone = "risk" if "volatility" in card.get("risk_level", "").lower() else "neutral"
    pills = "".join([
        pill_html(card["tony_rating"], "purple"),
        pill_html(card["setup_type"], "info"),
        pill_html(f"Risk: {card['risk_level']}", risk_tone),
        pill_html(card["data_quality"], "info"),
        pill_html(card["status"], card.get("status_tone", "neutral")),
        pill_html(
            card["entry_alert_status"],
            "warning" if "Waiting" in card.get("entry_alert_status", "") else "info",
        ),
    ])
    metrics = _metrics_row_html([
        ("Entry trigger", card["entry_trigger"], True),
        ("Distance to trigger", card["distance_to_trigger"], False),
        ("Active entry", card["active_entry"], False),
        (card.get("price_label", "Current price"), card["current_price"], False),
        ("Target", card["target"], False),
        ("Stop", card["stop"], False),
        ("Risk/reward", card["risk_reward"], False),
    ])
    render_html(
        f'<div class="tony-card">'
        f'<div class="tony-card-header"><div class="tony-card-symbol">{_esc(card["symbol"])}</div></div>'
        f'<div class="tony-pill-row">{pills}</div>'
        f'<div class="tony-card-why"><b>Why Tony noticed it</b><br>{_esc(card["why"])}</div>'
        f"{metrics}"
        f'<div class="tony-footnote"><b>Trigger reason:</b> {_esc(card["trigger_reason"])}</div>'
        f'<div class="tony-footnote">{_esc(card["trigger_explanation"])}</div>'
        f'<div class="tony-footnote"><b>Confirms if:</b> {_esc(card["confirms_if"])}</div>'
        f'<div class="tony-footnote"><b>Invalidates if:</b> {_esc(card["invalidates_if"])}</div>'
        f"</div>"
    )


def build_tracking_preview_card_html(card: dict[str, str]) -> str:
    """Compact Home Active Tracking preview (full cards on Active Tracking tab)."""
    pl_tone = card.get("pl_tone", "info")
    pl_class = f"tony-pl-{pl_tone}" if pl_tone in ("positive", "negative") else "tony-pl-neutral"
    metrics = _metrics_row_html([
        ("Entry trigger", card["entry_trigger"], False),
        ("Tracked from", card["tracked_from_price"], False),
        (card.get("price_label", "Current price"), card.get("price_value", card["current_price"]), True),
        ("Target", card["target"], False),
        ("Stop", card["stop"], False),
    ])
    return (
        f'<div class="tony-card tony-card-preview tony-card-track">'
        f'<div class="tony-card-header">'
        f'<div class="tony-card-symbol-sm">{_esc(card["symbol"])}</div>'
        f'<div class="{pl_class} tony-preview-pl">{_esc(card["research_pl_pct"])}</div>'
        f"</div>"
        f'<div class="tony-pill-row">'
        f'{pill_html(card["time_active"], "info")}'
        f'{pill_html(f"Result: {card["tony_status"]}", card.get("status_tone", "neutral"))}'
        f"</div>"
        f'<div class="tony-card-why tony-preview-why">{_esc(card.get("home_summary", ""))}</div>'
        f"{metrics}"
        f"</div>"
    )


def render_tracking_preview_card(card: dict[str, str]) -> None:
    render_html(build_tracking_preview_card_html(card))


def render_tracking_position_card(card: dict[str, str]) -> None:
    pl_tone = card.get("pl_tone", "info")
    pl_class = f"tony-pl-{pl_tone}" if pl_tone in ("positive", "negative") else "tony-pl-neutral"
    fresh_note = ""
    if card.get("is_fresh") != "yes":
        fresh_note = (
            '<div class="tony-footnote">Historical research record — not a live active setup.</div>'
        )
    metrics = _metrics_row_html([
        ("Entry trigger", card["entry_trigger"], False),
        ("Tracked from", card["tracked_from_price"], False),
        (card.get("price_label", "Current price"), card.get("price_value", card["current_price"]), True),
        ("Target", card["target"], False),
        ("Stop", card["stop"], False),
        ("Risk/reward", card["risk_reward"], False),
    ])
    tracking_label = "Live active tracking" if card.get("is_fresh") == "yes" else "Research record"
    reassessment_block = ""
    if card.get("reassessment_note"):
        reassessment_block = f'<motionless class="tony-footnote">{_esc(card["reassessment_note"])}</motionless>'.replace("motionless", "div")
    render_html(
        f'<div class="tony-card tony-card-track">'
        f'<div class="tony-card-header">'
        f'<div class="tony-card-symbol">{_esc(card["symbol"])}</div>'
        f'<div class="tony-pl-hero {pl_class}">Research P/L<br>{_esc(card["research_pl_pct"])}</div>'
        f"</div>"
        f'<div class="tony-pill-row">'
        f'{pill_html(tracking_label, "purple")}'
        f'{pill_html(card["time_active"], "info")}'
        f'{pill_html(f"Result so far: {card["tony_status"]}", card.get("status_tone", "neutral"))}'
        f"</div>"
        f"{metrics}"
        f'<div class="tony-footnote">Triggered {_esc(card["tracked_from_time"])}</div>'
        f'<div class="tony-disclaimer">Research tracking only — not a trade.</div>'
        f'<div class="tony-footnote">{_esc(card["plan_note"])}</div>'
        f"{reassessment_block}"
        f"{fresh_note}"
        f"</div>"
    )


def render_result_card(card: dict[str, str]) -> None:
    metrics = _metrics_row_html([
        (card.get("price_label", "Current price"), card["price_value"], True),
        ("Entry trigger", card["entry_trigger"], False),
        ("Active entry", card["active_entry"], False),
        ("Research P/L", card["research_pl_pct"], False),
        ("Target", card["target"], False),
        ("Stop", card["stop"], False),
        ("Risk/reward", card["risk_reward"], False),
    ])
    render_html(
        f'<div class="tony-card">'
        f'<div class="tony-card-header"><div class="tony-card-symbol">{_esc(card["symbol"])}</div></div>'
        f'<div class="tony-pill-row">'
        f'{pill_html(card["setup_type"], "info")}'
        f'{pill_html(card["status"], "purple")}'
        f"</div>"
        f"{metrics}"
        f'<div class="tony-card-why"><b>Why Tony watched it</b><br>{_esc(card["reason"])}</div>'
        f'<div class="tony-footnote"><b>Result:</b> {_esc(card["result_explanation"])}</div>'
        f"</div>"
    )


def avg_research_pl_from_prepared(prepared: pd.DataFrame) -> str:
    if prepared.empty or "result_eod" not in prepared.columns:
        return "—"
    triggered = (
        prepared[prepared["entry_triggered"].fillna(0).astype(int).eq(1)]
        if "entry_triggered" in prepared.columns
        else prepared
    )
    if triggered.empty:
        return "—"
    values: list[float] = []
    for raw in triggered["result_eod"]:
        if is_missing_scalar(raw):
            continue
        try:
            pct = float(raw) * 100.0
            if pct == pct:
                values.append(pct)
        except (TypeError, ValueError):
            continue
    if not values:
        return "Not enough data yet"
    return format_percent_or_missing(sum(values) / len(values))


def render_results_performance(summary: dict[str, Any], *, avg_pl: str, period: str) -> None:
    render_html(
        '<div class="tony-results-banner">'
        "Research outcomes only. No edge proven. Not investment advice."
        "</div>"
    )
    st.caption(f"Period: {period}")
    pl_tone = "green" if str(avg_pl).startswith("+") else "default"
    render_stat_grid([
        ("Watched", str(summary["watched_setups"]), "blue", "Setups Tony saved"),
        ("Triggered", str(summary["triggered"]), "purple", "Alerts that fired"),
        ("Active", str(summary.get("active", summary["still_active"])), "blue", None),
        ("Closed", str(summary.get("closed", 0)), "default", None),
        ("Target reached", str(summary["target_hits"]), "green", None),
        ("Stop reached", str(summary["stop_hits"]), "default", None),
        ("Partial moves", str(summary["partial_moves"]), "amber", None),
        ("Waiting", str(summary.get("waiting", 0)), "amber", None),
        ("Expired", str(summary["expired_no_trigger"]), "amber", None),
        ("Avg research P/L", avg_pl, pl_tone, "Closed-window returns only"),
    ])
    best = summary.get("best_setup_category")
    weak = summary.get("weakest_setup_category")
    if best:
        briefing_line(f"Strongest setup type (early): {best}")
    if weak:
        briefing_line(f"Weakest setup type (early): {weak}")


# ── TRACE Results table ─────────────────────────────────────────────────────


def _trace_status_pill_html(outcome_label: str, status_text: str) -> str:
    """Return a colored pill span for the TRACE results table status column."""
    ol = (outcome_label or "").lower().strip()
    if ol in ("target_hit", "target_before_stop"):
        tone = "green"
    elif ol in ("stop_hit", "stop_before_target", "failed_setup"):
        tone = "red"
    elif ol in ("tracking", "still_active"):
        tone = "blue"
    elif ol in ("entry_not_triggered", "expired_no_trigger", "unreviewed"):
        tone = "gray"
    else:
        tone = "amber"
    return f'<span class="trace-status-pill trace-pill-{tone}">{_esc(status_text)}</span>'


def build_results_table_html(cards: list[dict[str, str]]) -> str:
    """Build the full TRACE-style results HTML table from a list of result card models."""
    headers = [
        "Ticker", "Setup Type", "Status",
        "Entry", "Exit / Current", "Target", "Stop",
        "Research P/L", "R/R", "Date", "What Happened",
    ]
    header_row = "".join(f'<div class="trace-th">{h}</div>' for h in headers)

    if not cards:
        return (
            '<div class="trace-results-table">'
            f'<div class="trace-table-header">{header_row}</div>'
            '<div class="trace-empty-state">No results match the current filter.</div>'
            '<div class="trace-disclaimer">Research outcomes only. No edge proven. Not investment advice.</div>'
            "</div>"
        )

    rows_html = ""
    for card in cards:
        outcome = card.get("outcome_label", "")
        status_text = card.get("status", "—")
        pl_raw = card.get("research_pl_pct", "N/A")
        pl_class = "trace-pl-neutral"
        if isinstance(pl_raw, str) and pl_raw.startswith("+"):
            pl_class = "trace-pl-positive"
        elif isinstance(pl_raw, str) and pl_raw.startswith("-"):
            pl_class = "trace-pl-negative"

        exit_label = card.get("exit_price_label", card.get("price_label", "Exit"))
        exit_value = card.get("exit_price", card.get("price_value", "—"))
        exit_class = ""
        if "target" in exit_label.lower():
            exit_class = " trace-price-hit"
        elif "stop" in exit_label.lower():
            exit_class = " trace-price-stop"

        rows_html += (
            '<div class="trace-table-row">'
            f'<div class="trace-cell"><span class="trace-symbol">{_esc(card.get("symbol", "?"))}</span></div>'
            f'<div class="trace-cell trace-setup-type">{_esc(card.get("setup_type", "—"))}</div>'
            f'<div class="trace-cell">{_trace_status_pill_html(outcome, status_text)}</div>'
            f'<div class="trace-cell">{_esc(card.get("entry_trigger", "N/A"))}</div>'
            f'<div class="trace-cell{exit_class}">{_esc(exit_value)}</div>'
            f'<div class="trace-cell">{_esc(card.get("target", "—"))}</div>'
            f'<div class="trace-cell">{_esc(card.get("stop", "—"))}</div>'
            f'<div class="trace-cell {pl_class}">{_esc(pl_raw)}</div>'
            f'<div class="trace-cell">{_esc(card.get("risk_reward", "—"))}</div>'
            f'<div class="trace-cell">{_esc(card.get("trigger_date", "—"))}</div>'
            f'<div class="trace-cell trace-notes-cell">{_esc(card.get("result_explanation") or card.get("reason", "—"))}</div>'
            "</div>"
        )

    return (
        '<div class="trace-results-table">'
        f'<div class="trace-table-header">{header_row}</div>'
        f"{rows_html}"
        '<div class="trace-disclaimer">Research outcomes only. No edge proven. Not investment advice.</div>'
        "</div>"
    )


def render_results_table(cards: list[dict[str, str]]) -> None:
    """Render the TRACE-style results table via st.markdown."""
    render_html(build_results_table_html(cards))
