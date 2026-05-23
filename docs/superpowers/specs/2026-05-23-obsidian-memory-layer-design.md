# Obsidian Memory Layer — Design Spec
**Date:** 2026-05-23
**Status:** Approved for Phase 1 implementation
**Project:** TradingBotAgentProject

---

## Overview

A two-vault memory and handoff system for the trading bot. Vault 1 (inside this repo) stores all operational data as Obsidian-compatible markdown. A bridge export drops a curated analyst brief to the AI Operations Command Center after every EOD run, where the Tony Stocks agent does deep analysis and updates Vault 2.

All file writes go directly to disk via Python — no Obsidian MCP plugin in any write path, eliminating the 50-character truncation issue encountered in prior Command Center setup.

---

## Architecture

```
TradingBotAgentProject
└── vault/                    ← Vault 1 (bot memory)
    ├── index.md
    ├── daily/YYYY-MM-DD.md
    ├── signals/TICKER.md
    ├── outcomes/YYYY-MM-DD-outcomes.md
    ├── strategy/v1.md + proposals.md
    └── memory/agent-context.md

        ↓ after-market-review (EOD, automatic)

AI Operations Command Center
└── bridge/tony-stocks/
    └── YYYY-MM-DD.md         ← bridge export (analyst brief)

        ↓ Tony Stocks agent reads directly (no MCP)

AI Operations Command Center
└── vault/tony-stocks/
    ├── index.md              ← Tony updates: conviction tiers
    ├── signal-ledger.md      ← Tony updates: multi-day tracking
    └── tickers/TICKER.md     ← Tony creates: deep analysis notes
```

### Memory separation

| Layer | Path | Purpose |
|-------|------|---------|
| Claude session memory | `.claude/projects/.../memory/` | User prefs, coding feedback, project context. Stays lean (~5 files). |
| Vault 1 (bot memory) | `vault/` in this repo | All operational data — scans, scores, outcomes, strategy. Grows freely. |
| Vault 2 (command center) | `AI Operations Command Center/vault/tony-stocks/` | Curated, enriched — only what Tony decides matters after deep analysis. |

---

## Vault 1 — Folder Structure

```
vault/
├── index.md                     Root overview, current positions, recent daily links
├── daily/
│   └── YYYY-MM-DD.md            One comprehensive note per trading day
├── signals/
│   └── TICKER.md                One note per ticker, accumulates signal history
├── outcomes/
│   └── YYYY-MM-DD-outcomes.md   Performance ledger — target/stop hits, P/L
├── strategy/
│   ├── v1.md                    Each strategy version as its own note
│   └── proposals.md             Rule suggestions and approval status history
└── memory/
    └── agent-context.md         Curated vault summary Claude reads at session start
```

**Git:** `vault/` is tracked in git. Markdown files are small — no bloat concern.

**Obsidian:** Point Obsidian at the repo root or `vault/` folder. Wikilinks connect everything automatically.

---

## Daily Note Format — `vault/daily/YYYY-MM-DD.md`

Ten sections, capturing everything the bot generates. Nothing omitted.

```markdown
---
date: YYYY-MM-DD
tags: [daily, eod]
strategy_version: v1
universe_size: 349
scored_count: 175
coverage_pct: 50.1
cycles: 12
---

# YYYY-MM-DD — EOD Daily Note

## 1. Scan Coverage
Universe / Scored / Coverage % / Cycles / Real data count

## 2. All Scored Symbols
Full table — every symbol scored, with score, setup category, status, days active.
Wikilinked to signal pages: [[TICKER]]

## 3. Skip Reasons
Breakdown: not_enough_bars, avg_volume_below_minimum, stale_data,
pre_screener_filtered, duplicate_tracked. Tracks data quality trends over time.

## 4. Rotation Diagnostics
Unique symbols scanned, fresh discoveries, repeat scans, universe coverage %.

## 5. Top Signals (Curated)
Tier 1 (3+ days), Tier 2 (2 days), Tier 3 (1 day).
This section is the source for the bridge export.

## 6. Outcomes Today
Target hits, stop hits, active carry-over count, avg terminal P/L.

## 7. Signal Scorecard
Target/stop rate by setup category — the core learning data.

## 8. EOD Self-Review
Strongest/weakest setup, tomorrow watch notes, pending triggers.

## 9. Rule Suggestions
Confidence-tagged suggestions from Tony self-review.

## 10. Strategy
Version, proposals pending, no changes applied unless explicitly approved.

## Links
← [[YYYY-MM-DD]] | → [[YYYY-MM-DD]] | [[index]]
```

---

## Ticker Page Format — `vault/signals/TICKER.md`

Created on first appearance. A new row is appended to the signal history table on every EOD that includes the ticker. Permanent accumulating memory — never overwritten.

```markdown
---
ticker: TICKER
tags: [signal, sector-tag]
status: active
first_seen: YYYY-MM-DD
days_active: N
---

# TICKER — Company Name

**Sector:** [[Sector Name]]
**Status:** Active — Tier N
**Days Active:** N

## Signal History
| Date | Setup | Score | Status |
|------|-------|-------|--------|
| [[YYYY-MM-DD]] | Setup Type | Score | status |

## Entry Plan
Entry trigger, target, stop, R/R (populated when entry triggered).

## Outcome
Terminal outcome when closed — P/L, exit reason, days held.
Forward-compatible: will hold fill price, order ID, broker confirmation in Phase 4-5.

## Notes
Bot appends score trend notes. Tony appends deep analysis link when available.
```

---

## Bridge Export Format — `bridge/tony-stocks/YYYY-MM-DD.md`

Written by the bot directly to `AI Operations Command Center/bridge/tony-stocks/` via Python filesystem write. One dated file per day — never overwritten. Tony reads this file directly using the Read tool on the filesystem path — no MCP plugin, no truncation.

### Sections

```
Frontmatter: date, source, strategy_version, export_type

## Scanner Summary
Universe / scored / coverage % / cycles. Coverage trend vs yesterday.

## Tier 1 — Hand Off for Deep Analysis (3+ days)
Per-signal block: days active, score, setup, last close,
% to target, % to stop, R/R, score trend across days, bot note.

## Tier 2 — Monitor (2 days)
Table: ticker, score, setup, close, % to target, % to stop, R/R.

## Tier 3 — New Signals (1 day)
Table: ticker, score, setup, close.

## Watchlist — Pre-Trigger (score 50–74)
Pipeline of signals building toward Tier 3.
Table: ticker, score, setup, days watched, note.

## Weakening Watch
Previously Tier 2+ signals now deteriorating.
Table: ticker, current score, prior score, delta, reassessment label, note.

## Sector ETF Snapshot
XLK / XLE / XLV / XLU / XLI — score, setup, trend direction.
Macro context for Tony's analysis.

## Cluster Risk Flags
Auto-detected when 3+ active signals share a sector.
Warning + ETF context + risk note per cluster.

## Outcomes Since Last Brief
Table: ticker, result (target/stop/active), entry date, days held, P/L.

## Signal Scorecard (running totals)
Target/stop rate by setup — cumulative across all trading days.

## Rule Suggestions Pending Review
Confidence-tagged suggestions for Tony to consider.

## For Tony
Action items: which Tier 1 signals need deep analysis,
cluster risks to review, weakening positions to update in Vault 2.
Link to previous brief.
```

**Sector lookup:** Static `sector_map.py` dict maps each universe ticker to its sector and parent ETF. Starts populated from the existing universe, extensible.

---

## No MCP in Any Write Path

All vault and bridge files are written by Python directly to disk (`open(path, 'w')`). Obsidian watches the folder and updates instantly. No Obsidian plugin, no API layer, no character limits. Tony reads bridge files using the Read tool directly on the filesystem path — not through any MCP server.

---

## Code Changes

### New module: `src/trading_bot/vault/`

| File | Responsibility |
|------|---------------|
| `__init__.py` | Exports public functions |
| `writer.py` | `write_daily_note()`, `upsert_ticker_page()`, `update_vault_index()` |
| `bridge.py` | `write_bridge_export()` — builds and writes the full analyst brief |
| `sector_map.py` | Static `SECTOR_MAP` dict: ticker → `{sector, etf}` |

### Changes to existing files

**`src/trading_bot/cli.py` — `run_after_market_review()`**

Two calls added at the end, after all existing EOD steps complete:
```python
vault_writer.write_daily_note(report_date, eod_result, vault_dir)
vault_bridge.write_bridge_export(report_date, eod_result, command_center_dir)
```
No changes to scoring, triggers, rotation, or trading logic.

**`config/default_config.yaml`** — new `vault:` block:
```yaml
vault:
  enabled: true
  vault_dir: vault
  command_center_dir: C:/Users/alexa/Downloads/AI Operations Command Center
  bridge_enabled: true
```

### One-time seeding script: `scripts/seed_vault.py`

Reads all existing scan results, snapshots, and EOD data from the SQLite database and generates backfilled vault notes for every past trading day. Run once during setup. After that, `after-market-review` keeps everything current automatically.

### New tests

| File | Covers |
|------|--------|
| `tests/test_vault_writer.py` | Daily note generation, ticker page upsert, index update |
| `tests/test_vault_bridge.py` | Bridge export format, cluster flag detection, sector snapshot, weakening watch |

---

## Trigger

Bridge export fires automatically at the end of every `after-market-review` run. Also triggerable manually:
```
python -m trading_bot.cli export-to-vault
```
Standalone CLI command — re-exports without re-running the full EOD.

---

## Phase Roadmap

### Phase 1 — EOD Memory Layer (this weekend) ← IN SCOPE
Vault 1 structure, full daily notes, ticker pages, EOD bridge export to Command Center. Seeding script backfills from existing DB. Markets reopen Tuesday — vault is live and populated.

### Phase 2 — Live Signal Handoff (next sprint)
During watch cycles, bot writes live alert files to `bridge/tony-stocks/live/` when a new high-conviction signal is detected. Tony runs a `/loop` session in the Command Center watching that folder. Tony writes verdicts back to `bridge/tony-stocks/verdicts/`. Bot incorporates Tony's conviction score and notes into the snapshot on its next cycle. Dashboard shows Tony's verdict on Watchlist cards. Latency ~5–10 min — acceptable for swing trading.

### Phase 3 — MCP Live Alerts (future)
Bot pushes real-time signal alerts via MCP when a signal triggers intraday. Alert includes entry level, target, stop, R/R, Tony's prior verdict if available.

### Phase 4 — MCP Paper Trading (future)
Bot initiates and manages paper trades via MCP. Live P/L updates streamed back. Full trade lifecycle tracked in Vault 1.

### Phase 5 — MCP Live Trading (future)
Bot initiates actual live trades via MCP. All Phase 4 safety gates must be met and verified. Requires explicit human approval gate before any live order is placed. Never enabled by default.

**Forward-compatibility constraint:** The `outcomes/` vault format and ticker page schema must accommodate execution data fields (fill price, order ID, broker confirmation) from day one, so Phase 4–5 don't require vault restructuring.

---

## Safety

- No changes to scoring, trigger rules, rotation behavior, or trading execution in Phase 1.
- Vault writes are additive only — no existing data is modified or deleted.
- Bridge export is one-way — the bot writes a file, Tony reads it. No feedback loop in Phase 1.
- `vault_dir` and `command_center_dir` are configurable — no hardcoded paths in code.
- Live trading (Phase 5) requires explicit safety gate approval and is never enabled by default.
