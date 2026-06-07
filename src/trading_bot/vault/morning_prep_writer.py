"""Render MorningPrep artifacts to Obsidian vault, CC bridge, and reports dir.

Output sinks for the off-hours research engine (Task 5):
  1. Vault note        — morning_prep/<date>.md
  2. CC bridge         — bridge/tony-stocks/morning-prep/<date>.md  (one-way bot→CC)
  3. Reports (json+md) — morning_prep/<date>.json + morning_prep/<date>.md

No analysis, no I/O outside of these three sinks, no trading side-effects.
All content is RESEARCH ONLY — no orders are placed off-hours.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trading_bot.analytics.morning_prep import MorningPrep

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fmt_float(value: float | None, decimals: int = 2) -> str:
    """Format a float to a fixed number of decimal places, or 'n/a'."""
    if value is None:
        return "n/a"
    return f"{value:.{decimals}f}"


def _catalysts_summary(catalysts: dict[str, Any]) -> str:
    """Return a compact one-line summary of catalyst flags for the table."""
    if not catalysts:
        return "—"
    parts = []
    if catalysts.get("earnings_blackout"):
        parts.append("earnings-blackout")
    if catalysts.get("earnings_date"):
        parts.append(f"earnings:{catalysts['earnings_date']}")
    if catalysts.get("analyst_upgrade"):
        parts.append("upgrade")
    if catalysts.get("analyst_downgrade"):
        parts.append("downgrade")
    if catalysts.get("news_catalyst"):
        parts.append("news")
    if not parts:
        # Some keys present but none recognized — list truthy keys
        parts = [k for k, v in catalysts.items() if v]
    return ", ".join(parts) if parts else "—"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_morning_prep_markdown(
    prep: MorningPrep,
    *,
    narrative: str | None = None,
) -> str:
    """Return a full markdown string for the given MorningPrep.

    Structure
    ---------
    - YAML front matter with et_date, phase, research_only flag
    - Header with et_date and phase
    - PLANNED ONLY disclaimer (hard requirement — reinforces no off-hours execution)
    - Shortlist table (symbol as [[SYM]] wikilink, all price/conviction columns)
    - What Changed Overnight section
    - Plan for Open section
    - Optional narrative block (appended when narrative is not None)
    """
    lines: list[str] = []

    # -- Front matter --
    lines += [
        "---",
        f"et_date: {prep.et_date}",
        f"phase: {prep.phase}",
        "type: morning-prep",
        "research_only: true",
        "---",
        "",
    ]

    # -- Header --
    lines += [
        f"# Morning Prep — {prep.et_date} ({prep.phase})",
        "",
    ]

    # -- PLANNED disclaimer (hard requirement) --
    lines += [
        "> ⚠️ PLANNED ONLY — no orders are placed off-hours.",
        "> This note is research output only. All entries must be confirmed at open.",
        "",
    ]

    # -- Shortlist table --
    lines.append("## Shortlist")
    lines.append("")
    if not prep.shortlist:
        lines.append("_No candidates met the threshold — no names armed for today._")
        lines.append("")
    else:
        header = ("| symbol | score | setup | entry | stop | target "
                  "| rr | conviction | catalysts |")
        sep = ("|--------|-------|-------|-------|------|--------|"
               "----|------------|-----------|")
        lines.append(header)
        lines.append(sep)
        for c in prep.shortlist:
            cat_text = _catalysts_summary(c.catalysts)
            row = (
                f"| [[{c.symbol}]] "
                f"| {_fmt_float(c.score, 4)} "
                f"| {c.setup or '—'} "
                f"| {_fmt_float(c.entry)} "
                f"| {_fmt_float(c.stop)} "
                f"| {_fmt_float(c.target)} "
                f"| {_fmt_float(c.rr, 2)} "
                f"| {c.conviction} "
                f"| {cat_text} |"
            )
            lines.append(row)
        lines.append("")

    # -- What Changed Overnight --
    lines += [
        "## What Changed Overnight",
        "",
        prep.what_changed_overnight,
        "",
    ]

    # -- Plan for Open --
    lines += [
        "## Plan for Open",
        "",
        prep.plan_for_open,
        "",
    ]

    # -- Optional narrative block --
    if narrative is not None:
        lines += [
            "## Narrative",
            "",
            narrative,
            "",
        ]

    return "\n".join(lines)


def write_morning_prep_note(
    prep: MorningPrep,
    *,
    vault_dir: str | Path,
    narrative: str | None = None,
) -> Path:
    """Write morning_prep/<date>.md under vault_dir. Returns the Path written."""
    out_dir = Path(vault_dir) / "morning_prep"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{prep.et_date}.md"
    out.write_text(render_morning_prep_markdown(prep, narrative=narrative),
                   encoding="utf-8")
    return out


def write_morning_prep_bridge(
    prep: MorningPrep,
    *,
    command_center_dir: str | Path | None,
    narrative: str | None = None,
) -> Path | None:
    """Write bridge/tony-stocks/morning-prep/<date>.md under command_center_dir.

    Returns None immediately (no write) if command_center_dir is None.
    Returns the Path written otherwise.
    """
    if command_center_dir is None:
        return None
    out_dir = (Path(command_center_dir) / "bridge" / "tony-stocks" / "morning-prep")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{prep.et_date}.md"
    out.write_text(render_morning_prep_markdown(prep, narrative=narrative),
                   encoding="utf-8")
    return out


def write_morning_prep_report(
    prep: MorningPrep,
    *,
    reports_dir: str | Path,
) -> Path:
    """Write morning_prep/<date>.json and morning_prep/<date>.md under reports_dir.

    Returns the Path to the JSON file (the primary artifact).
    The .md sidecar is written alongside it for human readability.
    """
    out_dir = Path(reports_dir) / "morning_prep"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / f"{prep.et_date}.json"
    json_path.write_text(json.dumps(prep.to_dict(), indent=2), encoding="utf-8")

    md_path = out_dir / f"{prep.et_date}.md"
    md_path.write_text(render_morning_prep_markdown(prep), encoding="utf-8")

    return json_path
