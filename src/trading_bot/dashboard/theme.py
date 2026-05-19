"""Streamlit-safe HTML/CSS theme for the Tony Stocks product dashboard."""
from __future__ import annotations

import html as html_module
from typing import Any

import pandas as pd
import streamlit as st

from trading_bot.dashboard.helpers import format_percent_or_missing, is_missing_scalar

_TONY_APP_CSS = """
<style>
[data-testid="stAppViewContainer"] {
  background: linear-gradient(165deg, #eef2ff 0%, #f8fafc 35%, #f1f5f9 100%);
}
.block-container {
  padding-top: 1.5rem;
  max-width: 1200px;
}
.tony-hero {
  border-radius: 22px;
  padding: 1.6rem 1.8rem;
  margin-bottom: 1.25rem;
  background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 48%, #2563eb 100%);
  color: #ffffff;
  box-shadow: 0 12px 32px rgba(79, 70, 229, 0.28);
}
.tony-hero-title {
  font-size: 1.85rem;
  font-weight: 800;
  letter-spacing: -0.02em;
  margin: 0 0 0.4rem 0;
}
.tony-hero-sub {
  font-size: 1.05rem;
  opacity: 0.95;
  margin: 0;
}
.tony-hero-badge {
  display: inline-block;
  margin-top: 0.85rem;
  padding: 0.35rem 0.85rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.18);
  font-size: 0.82rem;
  font-weight: 600;
}
.tony-section {
  font-size: 1.15rem;
  font-weight: 700;
  color: #0f172a;
  margin: 1.25rem 0 0.65rem 0;
}
.tony-stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 0.75rem;
  margin: 0.75rem 0 1rem 0;
}
.tony-stat-tile {
  border-radius: 16px;
  padding: 0.85rem 1rem;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 4px 12px rgba(15, 23, 42, 0.06);
}
.tony-stat-tile-purple {
  background: linear-gradient(145deg, #ede9fe 0%, #ffffff 100%);
  border-color: #c4b5fd;
}
.tony-stat-tile-blue {
  background: linear-gradient(145deg, #dbeafe 0%, #ffffff 100%);
  border-color: #93c5fd;
}
.tony-stat-tile-green {
  background: linear-gradient(145deg, #dcfce7 0%, #ffffff 100%);
  border-color: #86efac;
}
.tony-stat-tile-amber {
  background: linear-gradient(145deg, #fef3c7 0%, #ffffff 100%);
  border-color: #fcd34d;
}
.tony-stat-label {
  font-size: 0.72rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #64748b;
}
.tony-stat-value {
  font-size: 1.35rem;
  font-weight: 800;
  color: #0f172a;
  margin-top: 0.2rem;
  line-height: 1.2;
}
.tony-stat-hint {
  font-size: 0.78rem;
  color: #64748b;
  margin-top: 0.25rem;
}
.tony-card {
  border-radius: 20px;
  padding: 1.25rem 1.45rem;
  margin-bottom: 1rem;
  background: linear-gradient(160deg, #ffffff 0%, #f8fafc 100%);
  border: 1px solid #e2e8f0;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.08);
}
.tony-card-preview {
  padding: 1rem 1.15rem;
}
.tony-preview-why {
  font-size: 0.92rem;
  margin: 0.45rem 0 0.55rem 0;
  padding: 0.55rem 0.7rem;
}
.tony-preview-pl {
  font-size: 1.05rem;
  font-weight: 800;
  text-align: right;
  white-space: nowrap;
}
.tony-card-track {
  border-left: 4px solid #6366f1;
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
  font-size: 2rem;
  font-weight: 800;
  letter-spacing: -0.03em;
  color: #0f172a;
  line-height: 1.1;
}
.tony-card-symbol-sm {
  font-size: 1.45rem;
  font-weight: 800;
  color: #0f172a;
}
.tony-pl-hero {
  font-size: 1.5rem;
  font-weight: 800;
  text-align: right;
}
.tony-pl-positive { color: #15803d; }
.tony-pl-negative { color: #b91c1c; }
.tony-pl-neutral { color: #475569; }
.tony-card-why {
  color: #334155;
  font-size: 1rem;
  line-height: 1.5;
  margin: 0.65rem 0 0.85rem 0;
  padding: 0.75rem 0.9rem;
  background: #f8fafc;
  border-radius: 12px;
  border: 1px solid #e2e8f0;
}
.tony-pill-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin: 0.5rem 0 0.65rem 0;
}
.tony-metric-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: 0.65rem;
  margin: 0.65rem 0 0.75rem 0;
}
.tony-metric {
  background: #ffffff;
  border-radius: 14px;
  padding: 0.6rem 0.75rem;
  border: 1px solid #e2e8f0;
}
.tony-metric-highlight {
  background: linear-gradient(145deg, #eef2ff 0%, #ffffff 100%);
  border-color: #c7d2fe;
}
.tony-metric-label {
  font-size: 0.7rem;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  font-weight: 600;
}
.tony-metric-value {
  font-size: 1.05rem;
  font-weight: 700;
  color: #0f172a;
  margin-top: 0.2rem;
}
.tony-pill {
  display: inline-block;
  padding: 0.28rem 0.7rem;
  border-radius: 999px;
  font-size: 0.78rem;
  font-weight: 600;
}
.tony-pill-positive { background: #dcfce7; color: #166534; }
.tony-pill-negative { background: #fee2e2; color: #991b1b; }
.tony-pill-warning { background: #fef3c7; color: #92400e; }
.tony-pill-risk { background: #ffedd5; color: #9a3412; }
.tony-pill-info { background: #dbeafe; color: #1e40af; }
.tony-pill-purple { background: #ede9fe; color: #5b21b6; }
.tony-pill-neutral { background: #e2e8f0; color: #334155; }
.tony-footnote {
  font-size: 0.82rem;
  color: #64748b;
  margin-top: 0.4rem;
  line-height: 1.4;
}
.tony-disclaimer {
  border-radius: 14px;
  padding: 0.85rem 1rem;
  background: #fff7ed;
  border: 1px solid #fed7aa;
  color: #9a3412;
  font-size: 0.88rem;
  margin: 0.75rem 0;
}
.tony-results-banner {
  border-radius: 14px;
  padding: 0.9rem 1.1rem;
  background: linear-gradient(135deg, #fef3c7 0%, #fff7ed 100%);
  border: 1px solid #fcd34d;
  color: #92400e;
  font-weight: 600;
  margin-bottom: 1rem;
}
.tony-briefing-line {
  font-size: 1.02rem;
  color: #334155;
  margin: 0.35rem 0 0.85rem 0;
  line-height: 1.45;
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
