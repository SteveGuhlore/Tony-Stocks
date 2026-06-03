from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from trading_bot.vault.sector_map import SECTOR_MAP, get_etf, get_sector

_SECTOR_ETFS = ["XLK", "XLE", "XLV", "XLU", "XLI", "XLF", "XLP", "XLY", "XLB", "XLRE", "XLC"]


def _pct(val: float | None, ref: float | None) -> str:
    if val is None or ref is None or ref == 0:
        return "N/A"
    diff = ((val - ref) / ref) * 100
    sign = "+" if diff >= 0 else ""
    return f"{sign}{diff:.1f}%"


def _rr(target: float | None, close: float | None, stop: float | None) -> str:
    if target is None or close is None or stop is None or close == 0:
        return "N/A"
    upside = abs(target - close)
    downside = abs(close - stop)
    if downside == 0:
        return "N/A"
    return f"{upside / downside:.1f}:1"


def _detect_clusters(
    snapshots: list[dict[str, Any]], threshold: int = 3
) -> list[dict[str, Any]]:
    """Return cluster dicts when >= threshold active signals share a sector."""
    sector_tickers: dict[str, list[str]] = {}
    for snap in snapshots:
        sym = snap.get("symbol", "")
        sector = get_sector(sym)
        if sector in ("Unknown", "Benchmark"):
            continue
        sector_tickers.setdefault(sector, []).append(sym)
    clusters = []
    for sector, tickers in sector_tickers.items():
        if len(tickers) >= threshold:
            etf = get_etf(tickers[0]) if tickers else ""
            clusters.append({"sector": sector, "etf": etf, "tickers": tickers})
    return clusters


def _build_sector_etf_snapshot(
    snapshots: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Extract score/setup for sector ETF tickers present in the scored snapshot list."""
    etf_map = {s["symbol"]: s for s in snapshots if s.get("symbol") in _SECTOR_ETFS}
    result = []
    for etf in _SECTOR_ETFS:
        if etf in etf_map:
            snap = etf_map[etf]
            score = snap.get("score", "N/A")
            setup = snap.get("setup_category", "")
            trend = (
                "↑ bullish" if isinstance(score, (int, float)) and score >= 65
                else "↓ weak" if isinstance(score, (int, float)) and score <= 45
                else "→ neutral"
            )
            result.append({"etf": etf, "score": score, "setup": setup, "trend": trend})
    return result


def write_bridge_export(
    date: str,
    eod_result: dict[str, Any],
    command_center_dir: str | Path,
    snapshots: list[dict[str, Any]] | None = None,
    slot: str | None = None,
    note: str | None = None,
) -> Path:
    """Write curated analyst brief to {command_center_dir}/bridge/tony-stocks/.

    ``slot`` selects the drop cadence: None or "eod" writes the canonical daily
    file ``YYYY-MM-DD.md`` (export_type: eod-bridge). An intraday slot like "1030"
    writes a timestamped ``YYYY-MM-DDTHHMM.md`` (export_type: intraday-bridge) so
    it never overwrites the daily file; the Command Center dedups on the timestamp.
    """
    is_intraday = bool(slot) and slot != "eod"
    cc_path = Path(command_center_dir)
    bridge_dir = cc_path / "bridge" / "tony-stocks"
    bridge_dir.mkdir(parents=True, exist_ok=True)
    out_path = bridge_dir / (f"{date}T{slot}.md" if is_intraday else f"{date}.md")

    sc = eod_result.get("scan_coverage") or {}
    scorecard = eod_result.get("signal_scorecard") or {}
    sr = eod_result.get("tony_self_review") or {}
    svr = eod_result.get("strategy_version_report") or {}
    tos = eod_result.get("terminal_outcome_summary") or {}
    outcomes = eod_result.get("outcomes_since_last_brief") or []
    suggestions = sr.get("rule_suggestions") or []
    snaps = snapshots or []

    # Read the real scan-coverage keys (with legacy fallbacks) — the builder emits
    # configured_universe_size / symbols_scored / percent_universe_covered_today,
    # not universe_size / scored_count, which previously made every bridge read 0/0.
    universe_size = (
        sc.get("universe_size") or sc.get("configured_universe_size")
        or sc.get("symbols_selected_loaded") or 0
    )
    scored_count = (
        sc.get("scored_count") or sc.get("symbols_scored")
        or sc.get("unique_symbols_scored_today") or 0
    )
    coverage_pct = sc.get("coverage_pct") or sc.get("percent_universe_covered_today") or 0.0
    cycles = sc.get("cycles_completed") or eod_result.get("cycles_completed") or 0
    strategy_version = svr.get("current_version") or "v1"
    active_count = tos.get("active_count", 0)

    non_etf = [s for s in snaps if s.get("symbol") not in _SECTOR_ETFS]
    tier1 = sorted([s for s in non_etf if s.get("days_active", 0) >= 3],
                   key=lambda s: s.get("score", 0), reverse=True)
    tier2 = sorted([s for s in non_etf if s.get("days_active", 0) == 2],
                   key=lambda s: s.get("score", 0), reverse=True)
    tier3 = sorted([s for s in non_etf if s.get("days_active", 0) == 1],
                   key=lambda s: s.get("score", 0), reverse=True)

    clusters = _detect_clusters(snaps)
    etf_snapshot = _build_sector_etf_snapshot(snaps)

    try:
        prev_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:
        prev_date = "previous"

    export_type = "intraday-bridge" if is_intraday else "eod-bridge"
    title_suffix = f" — {slot} ET intraday" if is_intraday else ""
    lines: list[str] = [
        "---",
        f"date: {date}",
        "source: TradingBotAgentProject",
        f"strategy_version: {strategy_version}",
        f"export_type: {export_type}",
    ]
    if is_intraday:
        lines.append(f"slot: {slot}")
    if note:
        lines.append("test: true")
        lines.append(f"note: {note}")
    lines += [
        "---",
        "",
        f"# Tony Stocks Bridge — {date}{title_suffix}",
        "",
    ]
    if note:
        lines += [f"> ⚠️ **{note}**", ""]
    lines += [
        "## Scanner Summary",
        f"- Universe: {universe_size} | Scored: {scored_count} ({coverage_pct:.1f}%) | Cycles: {cycles}",
        "",
        "## Tier 1 — Hand Off for Deep Analysis",
        "*(3+ days active — full conviction review)*",
        "",
    ]
    if tier1:
        for s in tier1:
            sym = s.get("symbol", "")
            close = s.get("latest_close")
            target = s.get("target_price")
            stop = s.get("stop_price")
            entry_triggered = s.get("status") == "active"
            lines += [
                f"### [[{sym}]]",
                f"- Days active: {s.get('days_active', '')} | Score: {s.get('score', '')} | Setup: {s.get('setup_category', '')}",
                f"- Last close: ${close} | Target: ${target} ({_pct(target, close)}) | Stop: ${stop} ({_pct(stop, close)})",
                f"- R/R: {_rr(target, close, stop)} | Entry triggered: {'yes' if entry_triggered else 'no'}",
                "",
            ]
    else:
        lines += ["*No Tier 1 signals today.*", ""]

    lines += ["## Tier 2 — Monitor", "*(2 days — building conviction)*", "",
              "| Ticker | Score | Setup | Close | To Target | To Stop | R/R |",
              "|--------|-------|-------|-------|-----------|---------|-----|"]
    if tier2:
        for s in tier2:
            close = s.get("latest_close")
            target = s.get("target_price")
            stop = s.get("stop_price")
            lines.append(
                f"| [[{s.get('symbol', '')}]] | {s.get('score', '')} | {s.get('setup_category', '')} "
                f"| ${close} | {_pct(target, close)} | {_pct(stop, close)} | {_rr(target, close, stop)} |"
            )
    else:
        lines.append("| — | — | — | — | — | — | — |")
    lines.append("")

    lines += ["## Tier 3 — New Signals (1 day)", "",
              "| Ticker | Score | Setup | Close |", "|--------|-------|-------|-------|"]
    if tier3:
        for s in tier3:
            lines.append(f"| [[{s.get('symbol', '')}]] | {s.get('score', '')} | {s.get('setup_category', '')} | ${s.get('latest_close', '')} |")
    else:
        lines.append("| — | — | — | — |")
    lines.append("")

    lines += ["## Sector ETF Snapshot", "*(macro context for signal clusters)*", "",
              "| ETF | Sector | Score | Setup | Trend |",
              "|-----|--------|-------|-------|-------|"]
    if etf_snapshot:
        for e in etf_snapshot:
            sector = SECTOR_MAP.get(e["etf"], {}).get("sector", "")
            lines.append(f"| {e['etf']} | {sector} | {e['score']} | {e['setup']} | {e['trend']} |")
    else:
        lines.append("| — | — | — | — | — |")
    lines.append("")

    lines += ["## Cluster Risk Flags", "*(concentration warning — same sector exposure)*", ""]
    if clusters:
        for c in clusters:
            tickers_str = " + ".join(c["tickers"])
            lines += [
                f"⚠ {c['sector'].upper()} CLUSTER: {tickers_str} = {len(c['tickers'])} signals",
                f"  → All correlated to {c['etf']}",
                f"  → Risk: sector-wide drawdown affects all {len(c['tickers'])}",
                "",
            ]
    else:
        lines += ["*No cluster risk flags today.*", ""]

    lines += ["## Outcomes Since Last Brief", "",
              "| Ticker | Result | Entry Date | Days Held | P/L |",
              "|--------|--------|-----------|-----------|-----|"]
    if outcomes:
        for o in outcomes:
            pl = o.get("pl_pct")
            pl_str = f"{pl:+.1f}%" if isinstance(pl, (int, float)) else "N/A"
            result = o.get("result", "")
            icon = "✅" if "target" in result else ("❌" if "stop" in result else "⏳")
            lines.append(
                f"| {o.get('symbol', '')} | {icon} {result.replace('_', ' ')} "
                f"| {o.get('entry_date', '')} | {o.get('days_held', '')} | {pl_str} |"
            )
    else:
        lines.append("| — | — | — | — | — |")
    lines += ["", f"Active carry-over: {active_count} positions", ""]

    lines += ["## Signal Scorecard (running totals)", "",
              "| Setup | Triggered | Target Rate | Stop Rate |",
              "|-------|-----------|-------------|-----------|"]
    if isinstance(scorecard, dict) and scorecard:
        for setup, stats in scorecard.items():
            if not isinstance(stats, dict):
                continue
            triggered = stats.get("triggered", stats.get("total_triggered", ""))
            tr = stats.get("target_rate", "")
            sr2 = stats.get("stop_rate", "")
            if isinstance(tr, float):
                tr = f"{tr:.0%}"
            if isinstance(sr2, float):
                sr2 = f"{sr2:.0%}"
            lines.append(f"| {setup} | {triggered} | {tr} | {sr2} |")
    else:
        lines.append("| — | — | — | — |")
    lines.append("")

    lines += ["## Rule Suggestions Pending Review"]
    if suggestions:
        for i, sug in enumerate(suggestions, 1):
            lines.append(f"{i}. [{sug.get('confidence', '')}] {sug.get('suggestion', '')}")
    else:
        lines.append("*No suggestions pending.*")
    lines.append("")

    tier1_action = ", ".join(s.get("symbol", "") for s in tier1) if tier1 else "none"
    cluster_action = ", ".join(c["sector"] for c in clusters) if clusters else "none"
    lines += [
        "## For Tony",
        "Daily brief from scanner. Action items:",
        f"- Deep analysis on Tier 1: {tier1_action}",
        f"- Cluster risk review: {cluster_action}",
        "- Update signal-ledger.md + index.md after review",
        f"← Previous: [[bridge/tony-stocks/{prev_date}]] | [[bridge/tony-stocks/index]]",
    ]

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
