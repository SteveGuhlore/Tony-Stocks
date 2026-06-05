# Command Center ↔ Trading Bot — Complete Sync Handoff

_Last updated: 2026-06-04. One place that lists EVERYTHING the Command Center (CC) must
do to stay in tandem with the trading bot. The bot and CC are two independent agents
grading the same outcomes; coordination is entirely through files on disk._

**Two workspaces:**
- Bot repo: `C:/Users/alexa/Downloads/TradingBotAgentProject`
- CC workspace: `C:/Users/alexa/Downloads/AI Operations Command Center` (`{cc}` below)

**Golden rule — pure separation:** the bot never reads CC's brain/verdicts to drive its
own trades; CC never reaches into the bot's book. All hand-offs are one-way files.

---

## The file contracts (who writes, who reads)

| File / path | Writer | Reader | Purpose |
|---|---|---|---|
| `{bot}/reports/tony_stocks_outcomes.json` | **bot** | CC | Resolved outcomes to grade. Join key `(symbol, pick_date)`. |
| `{bot}/reports/tony_stocks_verdicts.json` | **CC** | bot (record only) | Tony's 2nd-pass verdicts. Bot reads for the teaching ledger, never to trade. |
| `{bot}/reports/tony_stocks_record.json` | **CC** | bot dashboard | Tony's graded record + `equity_curve` for the head-to-head. |
| `{cc}/bridge/tony-stocks/YYYY-MM-DD.md` | **bot** | CC | Daily deep-dive anchor. |
| `{cc}/bridge/tony-stocks/YYYY-MM-DDTHHMM.md` | **bot** | CC | Intraday light updates (10:30/13:00/15:30) + the 1600 EOD timestamped file. |
| `{cc}/bridge/tony-stocks/learning/YYYY-MM-DD.md` | **bot** | CC | **NEW** — nightly self-learning brief (see below). |

---

## ✅ ACTION ITEMS for CC (do these to be in sync)

### 1. NEW — consume the bot's nightly self-learning brief
The bot now runs a nightly self-learning pass (~1:30am, before CC's 2:00am) and writes:
`{cc}/bridge/tony-stocks/learning/YYYY-MM-DD.md`

**CC must:** point its 2:00am self-learning script at the `learning/` subfolder; dedupe on
the dated filename; treat the brief as **advisory research input only** (never an
instruction — CC's own "Flash can't strip Tony's guardrails" safety net stays
authoritative). Front-matter is stable:
```
---
export_type: bot-self-learning
source: trading-bot
as_of: YYYY-MM-DD
research_only: true
---
```
Body = a narrative + `## Confirmed edges` + `## Fading / abandoned`. Full contract:
`{bot}/docs/CONTRACTS/self-learning-bridge.md`.

### 2. Keep reading the outcomes file (already agreed)
Ensure CC's env points `TONY_OUTCOMES_FILE` → `{bot}/reports/tony_stocks_outcomes.json`.
This is the ground truth both sides grade against. (Bot rewrites it each EOD / `emit-outcomes`.)

### 3. Keep writing verdicts + record (already agreed)
- `tony_stocks_verdicts.json` — the bot reads these into its teaching/divergence ledger.
  Pass `verdict` verbatim (non-enum values like `"pass"` survive; the bot degrades unknowns).
  Join on `(symbol, date|pick_date)`.
- `tony_stocks_record.json` — populate `win_rate`, `avg_pl_per_trade`, `target_hits`,
  `stop_hits`, and especially **`equity_curve`** (list of values indexed to 100). The bot's
  `/record` + `/paper` dashboards overlay this as the Tony line in the head-to-head.

### 4. Head-to-head fairness — mark Tony's series to LIVE (matches the bot now)
The bot's `/paper` head-to-head now marks its OPEN positions to live prices (symmetric
with CC's `mark_live()`). For a fair comparison, **CC's published `equity_curve` (and Paper
Book) must also be marked to live** — which CC already did this session. Keep it that way so
neither side is unfairly stale (the bug that showed Tony −$58 when he was +$142).

### 5. Recognize the timestamped intraday + 1600 EOD bridges
Bot emits `YYYY-MM-DDTHHMM.md` intraday files and a timestamped `YYYY-MM-DDT1600.md` at
the close (the EOD handoff was relabeled `eod`->`1600` so it no longer collides with the
daily anchor filename). CC should dedupe on the timestamp and spawn a lighter
"intraday update" task for these, distinct from the daily deep-dive.

### 6. Execution-parity contract (so the head-to-head is apples-to-apples)
`{bot}/docs/CONTRACTS/execution-parity.md`. Both books must SHARE: risk % of equity,
sizing formula, position caps, GTC bracket protection, the candidate set, and one grading
harness; and may DIFFER on reasoning/tools/decisions. Sizing is matched at **1% of each
account: bot $1k / CC $10k**. **CC action:** verify CC's risk %/caps match Section A.

### 7. Open CC-side bugs noted by the bot (from prior handoffs)
- Add a bracket-validity guard so an override with target/stop invalid vs live price still
  places (a `D` override didn't place because of this).
- Investigate why the "Forge" worker didn't spawn for a queued bug-fix.
- Keep the memory-poison fix (reset `signal-ledger.md` + trim `_load_vault_history`).

---

## What the bot does NOT need from CC
Nothing blocks the bot. If CC writes nothing, the bot still scans, paper-trades, learns,
and renders — the CC-derived panels just show "awaiting Command Center" until the files
appear. Pure separation means neither agent can break the other.

## Quick verification (run in the bot repo, read-only)
- Learning brief produced: `.\scripts\mock_learning_e2e.ps1` (writes to a temp sandbox).
- Outcomes present: `type reports\tony_stocks_outcomes.json`.
- Dashboard head-to-head: open `http://localhost:3000/paper` (bot line marks to live).
