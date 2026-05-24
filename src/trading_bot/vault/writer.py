from __future__ import annotations

from pathlib import Path
from typing import Any


def write_daily_note(
    date: str,
    eod_result: dict[str, Any],
    vault_dir: str | Path,
    snapshots: list[dict[str, Any]] | None = None,
) -> Path:
    """Write vault/daily/YYYY-MM-DD.md from eod_result dict. Overwrites if exists."""
    vault_path = Path(vault_dir)
    daily_dir = vault_path / "daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    note_path = daily_dir / f"{date}.md"

    sc = eod_result.get("scan_coverage") or {}
    sr = eod_result.get("tony_self_review") or {}
    svr = eod_result.get("strategy_version_report") or {}
    tos = eod_result.get("terminal_outcome_summary") or {}
    rd = eod_result.get("rotation_diagnostics") or {}
    skip = eod_result.get("skip_reasons") or {}
    scorecard = eod_result.get("signal_scorecard") or {}
    suggestions = sr.get("rule_suggestions") or []
    strategy_version = (svr.get("current_version") or "v1")
    snaps = snapshots or []

    universe_size = sc.get("universe_size", 0)
    scored_count = sc.get("scored_count", 0)
    coverage_pct = sc.get("coverage_pct", 0.0)
    cycles = sc.get("cycles_completed", 0)
    real_data_count = sc.get("real_data_count", 0)
    active_count = tos.get("active_count", 0)
    target_hits = tos.get("target_hits", 0)
    stop_hits = tos.get("stop_hits", 0)
    avg_pl = tos.get("avg_terminal_pl", None)
    pl_str = f"{avg_pl:.1f}%" if isinstance(avg_pl, (int, float)) else "N/A"

    lines: list[str] = [
        "---",
        f"date: {date}",
        "tags: [daily, eod]",
        f"strategy_version: {strategy_version}",
        f"universe_size: {universe_size}",
        f"scored_count: {scored_count}",
        f"coverage_pct: {coverage_pct}",
        f"cycles: {cycles}",
        "---",
        "",
        f"# {date} — EOD Daily Note",
        "",
        "## 1. Scan Coverage",
        f"- Universe: {universe_size} symbols | Scored: {scored_count} ({coverage_pct:.1f}%)",
        f"- Cycles completed: {cycles}",
        f"- Real data symbols: {real_data_count}",
        "",
        "## 2. All Scored Symbols",
        "*(every symbol that ran through scoring)*",
        "",
        "| Ticker | Score | Setup Category | Status | Days Active |",
        "|--------|-------|----------------|--------|-------------|",
    ]
    for snap in snaps:
        sym = snap.get("symbol", "")
        lines.append(
            f"| [[{sym}]] | {snap.get('score', '')} | {snap.get('setup_category', '')} "
            f"| {snap.get('status', '')} | {snap.get('days_active', 0)} |"
        )
    if not snaps:
        lines.append("| — | — | — | — | — |")
    lines.append("")

    lines += [
        "## 3. Skip Reasons",
        "*(why symbols didn't get scored)*",
        "",
        "| Reason | Count |",
        "|--------|-------|",
    ]
    if skip:
        for reason, count in skip.items():
            lines.append(f"| {reason} | {count} |")
    else:
        lines.append("| — | — |")
    lines.append("")

    unique = rd.get("unique_symbols_scanned", 0)
    fresh = rd.get("fresh_discoveries", 0)
    repeats = rd.get("repeat_scans", 0)
    uni_cov = rd.get("universe_coverage_pct", 0.0)
    lines += [
        "## 4. Rotation Diagnostics",
        f"- Unique symbols scanned today: {unique}",
        f"- Fresh discoveries: {fresh}",
        f"- Repeat scans: {repeats}",
        f"- Universe coverage: {uni_cov:.1f}%",
        "",
    ]

    tier1 = [s for s in snaps if s.get("days_active", 0) >= 3]
    tier2 = [s for s in snaps if s.get("days_active", 0) == 2]
    tier3 = [s for s in snaps if s.get("days_active", 0) == 1]
    lines += ["## 5. Top Signals (Curated)", ""]
    if tier1:
        lines += ["### Tier 1 — High Conviction (3+ days)",
                  "| Ticker | Setup | Score | Days Active |",
                  "|--------|-------|-------|-------------|"]
        for s in tier1:
            lines.append(f"| [[{s['symbol']}]] | {s.get('setup_category', '')} | {s.get('score', '')} | {s.get('days_active', '')} |")
        lines.append("")
    if tier2:
        lines += ["### Tier 2 — Medium Conviction (2 days)",
                  "| Ticker | Setup | Score | Days Active |",
                  "|--------|-------|-------|-------------|"]
        for s in tier2:
            lines.append(f"| [[{s['symbol']}]] | {s.get('setup_category', '')} | {s.get('score', '')} | {s.get('days_active', '')} |")
        lines.append("")
    if tier3:
        lines += ["### Tier 3 — Monitor (1 day)",
                  " · ".join(f"[[{s['symbol']}]]" for s in tier3), ""]
    if not (tier1 or tier2 or tier3):
        lines += ["*No scored signals today.*", ""]

    lines += [
        "## 6. Outcomes Today",
        f"- Active positions: {active_count}",
        f"- Target hits: {target_hits}",
        f"- Stop hits: {stop_hits}",
        f"- Avg terminal P/L: {pl_str}",
        "",
        "## 7. Signal Scorecard",
        "| Setup | Triggered | Target Rate | Stop Rate |",
        "|-------|-----------|-------------|-----------|",
    ]
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

    strongest = sr.get("strongest_setup", "N/A")
    weakest = sr.get("weakest_setup", "N/A")
    tomorrow_watch = sr.get("tomorrow_watch", "")
    lines += [
        "## 8. EOD Self-Review",
        f"- Strongest: {strongest}",
        f"- Weakest: {weakest}",
        f"- Active carry over tomorrow: {active_count}",
    ]
    if tomorrow_watch:
        if isinstance(tomorrow_watch, list):
            for item in tomorrow_watch:
                lines.append(f"- Tomorrow watch: {item}")
        else:
            lines.append(f"- Tomorrow watch: {tomorrow_watch}")
    lines.append("")

    lines += ["## 9. Rule Suggestions"]
    if suggestions:
        for i, sug in enumerate(suggestions, 1):
            lines.append(f"{i}. [{sug.get('confidence', '')}] {sug.get('suggestion', '')}")
    else:
        lines.append("*No suggestions today.*")
    lines += [
        "",
        "## 10. Strategy",
        f"- Version: {strategy_version} | Proposals pending: {len(suggestions)}",
        "- No changes applied today",
        "",
        "## Links",
        f"← [[{date}]] | [[index]]",
    ]

    note_path.write_text("\n".join(lines), encoding="utf-8")
    return note_path


def upsert_ticker_page(
    date: str, snapshot: dict[str, Any], vault_dir: str | Path
) -> Path:
    """Create or append-to vault/signals/TICKER.md. Never overwrites existing history rows."""
    vault_path = Path(vault_dir)
    signals_dir = vault_path / "signals"
    signals_dir.mkdir(parents=True, exist_ok=True)

    symbol = snapshot.get("symbol", "UNKNOWN")
    page_path = signals_dir / f"{symbol}.md"
    score = snapshot.get("score", "")
    setup = snapshot.get("setup_category", "")
    status = snapshot.get("status", "")
    days_active = snapshot.get("days_active", 0)
    new_row = f"| [[{date}]] | {setup} | {score} | {status} |"

    if not page_path.exists():
        lines = [
            "---",
            f"ticker: {symbol}",
            "tags: [signal]",
            f"status: {status}",
            f"first_seen: {date}",
            f"days_active: {days_active}",
            "---",
            "",
            f"# {symbol}",
            "",
            f"**Status:** {status}",
            f"**Days Active:** {days_active}",
            "",
            "## Signal History",
            "| Date | Setup | Score | Status |",
            "|------|-------|-------|--------|",
            new_row,
            "",
            "## Entry Plan",
            "*Populated when entry triggered.*",
            "",
            "## Outcome",
            "*Populated on close. Forward-compatible: will hold fill price, order ID, broker confirmation in Phase 4-5.*",
            "",
            "## Notes",
            "",
            "---",
            "[[index]]",
        ]
        page_path.write_text("\n".join(lines), encoding="utf-8")
    else:
        content = page_path.read_text(encoding="utf-8")
        if f"[[{date}]]" in content:
            return page_path
        lines = content.splitlines()
        insert_idx = None
        for i in range(len(lines) - 1, -1, -1):
            if lines[i].startswith("| [["):
                insert_idx = i + 1
                break
        if insert_idx is None:
            lines.append(new_row)
        else:
            lines.insert(insert_idx, new_row)
        updated = []
        for line in lines:
            if line.startswith("days_active:"):
                updated.append(f"days_active: {days_active}")
            elif line.startswith("status:") and not line.startswith("**"):
                updated.append(f"status: {status}")
            else:
                updated.append(line)
        if "[[index]]" not in content:
            updated += ["", "---", "[[index]]"]
        page_path.write_text("\n".join(updated), encoding="utf-8")

    return page_path


def update_vault_index(
    date: str, snapshots: list[dict[str, Any]], vault_dir: str | Path
) -> Path:
    """Write/overwrite vault/index.md with current state summary."""
    vault_path = Path(vault_dir)
    vault_path.mkdir(parents=True, exist_ok=True)
    index_path = vault_path / "index.md"

    active = sorted(
        [s for s in snapshots if s.get("status") in ("active", "waiting_alert", "waiting")],
        key=lambda s: s.get("score", 0), reverse=True,
    )

    lines = [
        "# Trading Bot Vault — Index",
        "",
        f"*Last updated: {date}*",
        "",
        "## Latest Daily Note",
        f"[[daily/{date}]]",
        "",
        "## Current Active Positions",
        "| Ticker | Score | Status |",
        "|--------|-------|--------|",
    ]
    for s in active:
        sym = s.get("symbol", "")
        lines.append(f"| [[signals/{sym}]] | {s.get('score', '')} | {s.get('status', '')} |")
    if not active:
        lines.append("| — | — | — |")
    daily_dir = vault_path / "daily"
    all_daily = sorted(p.stem for p in daily_dir.glob("*.md")) if daily_dir.exists() else []

    lines += ["", "## All Daily Notes"]
    if all_daily:
        lines.append(" | ".join(f"[[daily/{d}]]" for d in all_daily))
    else:
        lines.append(f"[[daily/{date}]]")
    lines += [
        "",
        "## Navigation",
        "- [[signals/]] — all ticker pages",
        "- [[outcomes/]] — performance ledger",
        "- [[strategy/]] — strategy versions and proposals",
        "- [[memory/agent-context]] — curated vault summary",
    ]

    index_path.write_text("\n".join(lines), encoding="utf-8")
    return index_path
