# Nightly Self-Learning Loop — Design Spec

_Date: 2026-06-04 · Status: approved design, pre-implementation_

## 1. Goal

Give the trading bot a **brain that learns and evolves every night** — the same
operating model the Command Center (CC) runs at 2:00am. Each night the bot looks
back at what worked and what didn't across its own resolved outcomes, grades its
setups/sectors/scores, synthesizes the lessons into prose, accumulates a living
knowledge base in the Obsidian vault, and hands a curated brief to the CC so Tony's
2:00am script can incorporate the bot's self-assessment.

**Why now:** the bot already *produces* learning signals (resolved outcomes, the
Tony teaching log, the funnel-eval harness) and already has the *surfaces* to hold
memory (`reports/agent_insights.json`, the Obsidian `vault/`, the CC bridge) — but
nothing connects them. `agent_insights.json` is an empty mailbox: a `record_agent_insight()`
writer with no producer. This spec builds the producer.

## 2. Operator decisions (locked)

| Decision | Choice |
|---|---|
| Autonomy | **Memory + insights only.** Never auto-changes trading params, config, universe, or risk. Read-only on everything money-adjacent. |
| CC coordination | **Bot learns AND feeds CC.** Writes local vault memory + dashboard insights, AND pushes a learning bridge into the CC vault. Pure separation preserved — the bot never reads CC's brain back. |
| Wording | **Deterministic facts → LLM narrative (A→B).** A pure core computes the hard numbers (guaranteed correct, unit-tested); Claude receives those verified facts and writes the lessons. The LLM interprets, never counts. Degrades to plain templates if the API key is absent. |
| Scheduling | **Windows Scheduled Task at 1:30am** (before CC's 2:00am), calling a new `learn` CLI. |
| Depth | **Maximally in-depth + cumulative.** Per-night facts across many dimensions PLUS a living `_knowledge.md` that compounds and is revised nightly (edges promoted/demoted with confidence + sample size + week-over-week trend). |

## 3. Non-goals (safety boundary)

- **No order placement.** The job never touches the broker or paper book.
- **No config/threshold/weight/universe mutation.** It emits *knowledge*, not edits.
- **No watch-loop restart.** It runs as an independent process.
- **No profitability claim.** Every artifact carries `research_only: true`.
- **No reading CC's internal memory.** One-way bridge out, same as the outcomes contract.

## 4. Architecture

```
                          ┌─────────────────────────── inputs (read-only) ───────────────────────────┐
reports/tony_stocks_outcomes.json   reports/tony_teaching_log.json   snapshot history (funnel_eval)
paper book closed trades (repo)     prior reports/learning_knowledge.json (continuity)
                          └──────────────────────────────────┬───────────────────────────────────────┘
                                                              ▼
                          analytics/nightly_learning.py  (pure deterministic core)
                            build_nightly_facts(...)  ->  NightlyFacts          # the verified numbers
                            update_knowledge(prior, facts) -> KnowledgeBase     # cumulative, deterministic merge
                                                              ▼
                          analytics/learning_narrator.py  (LLM layer, optional)
                            narrate(facts, knowledge, prior_notes) -> str       # Claude sonnet-4-6; falls back to templates
                                                              ▼
        ┌─────────────────────────────── sinks (write) ───────────────────────────────┐
        ▼                                   ▼                              ▼            ▼
vault/learning/YYYY-MM-DD.md     vault/learning/_knowledge.md   reports/agent_insights.json   CC bridge:
(dated lessons note)             (living knowledge, revised)    (dashboard mailbox)           {cc}/bridge/tony-stocks/
                                                                                              learning/YYYY-MM-DD.md
                                                              ▲
                          cli.py  `learn` subcommand  ──────┘   (orchestrator: read → facts → knowledge → narrate → write all sinks)
                                                              ▲
                          scripts/register_learning_task.ps1  (schtasks → 1:30am nightly)
```

Design principle: the **analysis is pure and testable**; the **orchestration is thin**;
the **LLM is an isolated, fail-safe enhancement layer**. Mirrors the existing
`funnel_eval` / `tony_divergence` (pure core, CLI wiring, fail-quiet) conventions.

## 5. Components & interfaces

### 5.1 `analytics/nightly_learning.py` (pure, no I/O)

```python
@dataclass(frozen=True)
class Dimension:           # one analyzed angle
    key: str               # "setup_edge" | "sector_signal" | "score_calibration" | ...
    title: str
    rows: list[dict]       # the computed table (e.g. per setup_category)
    headline: str          # deterministic one-liner ("Momentum: 71% win, n=14")
    confidence: str        # "high" | "med" | "low" | "insufficient"  (sample-size gated)
    sample_size: int

@dataclass(frozen=True)
class NightlyFacts:
    as_of: str             # ET date
    dimensions: list[Dimension]
    summary: dict          # totals: trades, win_rate, avg_r, net_tony_divergence, ...
    research_only: bool = True
    def to_dict(self) -> dict: ...

def build_nightly_facts(
    outcomes: list[dict],
    teaching: dict | None,         # tony_teaching_log.json contents
    funnel_report: dict | None,    # funnel_eval FunnelEvalReport.to_dict()
    closed_paper: list[dict] | None,
    *, min_sample: int = 5,
) -> NightlyFacts: ...
```

**Dimensions computed (deterministic):**
1. **Setup edge** — win-rate + avg-R per `setup_category`.
2. **Sector signal** — win-rate + current win/loss streak per sector (via `vault/sector_map`).
3. **Score calibration** — win-rate by `total_score` bucket (does a higher score actually win more? is the model predictive or noise).
4. **R-multiple distribution** — avg winner-R vs avg loser-R, expectancy; flags "death by a thousand stops."
5. **Hold-time** — avg `days_held` for winners vs losers (exiting too early/late?).
6. **Entry timing** — triggered-then-reversed vs clean-run rate (from snapshot history).
7. **Funnel value** — wraps `funnel_eval.evaluate_funnel_stages`: per stage helps/hurts/neutral.
8. **Tony divergence** — wraps `tony_divergence`: net of his overrides (is the 2nd pass helping).
9. **Time-stop / expiry** — share of picks dying by expiry vs target/stop.
10. **Regime/streak** — recent overall win/loss run; anomaly flag vs trailing baseline.

Every dimension is **sample-size gated**: below `min_sample` it reports
`confidence: "insufficient"` rather than overfitting to a handful of trades.

### 5.2 Cumulative knowledge (pure, deterministic merge)

```python
@dataclass(frozen=True)
class KnowledgeItem:
    key: str               # stable id, e.g. "setup:momentum"
    claim: str             # "Momentum setups carry a positive edge"
    status: str            # "confirmed" | "emerging" | "decaying" | "rejected"
    win_rate: float | None
    sample_size: int
    confidence: str
    first_seen: str        # ET date
    last_updated: str
    trend: str             # "up" | "down" | "flat"  (week-over-week)
    history: list[dict]    # [{date, win_rate, n}] rolling, capped

@dataclass(frozen=True)
class KnowledgeBase:
    items: list[KnowledgeItem]
    as_of: str
    def to_dict(self) -> dict: ...

def update_knowledge(prior: KnowledgeBase | None, facts: NightlyFacts) -> KnowledgeBase:
    """Merge tonight's facts into the running knowledge. Deterministic:
    promote (emerging->confirmed) on sustained edge + sample growth, demote
    (confirmed->decaying->rejected) on win-rate erosion, set trend from history.
    This is the 'evolve' — lessons compound instead of resetting nightly."""
```

`_knowledge.md` is rendered from `KnowledgeBase`; a machine-readable
`reports/learning_knowledge.json` is the source of truth that `update_knowledge`
reads back each night (the markdown is the human view).

### 5.3 `analytics/learning_narrator.py` (LLM layer, fail-safe)

```python
def narrate(facts: NightlyFacts, knowledge: KnowledgeBase,
            prior_note: str | None, *, client=None) -> NarrationResult:
    """Send the VERIFIED facts + current knowledge + last night's note to Claude
    and get back: (1) a prose 'lessons learned' narrative, (2) a short list of
    insight lines for agent_insights.json. The model never sees raw trade rows it
    could miscount — only the computed NightlyFacts. On any error or missing
    ANTHROPIC_API_KEY, returns deterministic templated text (template_fallback=True)."""
```

- **Model:** `claude-sonnet-4-6` (strong reasoning, ~pennies/night for one call).
  Configurable via `learning.model`. (`claude-api` skill consulted at implementation
  time for current SDK + params.)
- **Key:** `ANTHROPIC_API_KEY` from `.env`. Absent → templated fallback, no crash.
- **Grounding rule (anti-hallucination):** the prompt forbids inventing numbers; all
  figures must come from the provided facts. Numeric claims are template-rendered;
  the LLM supplies the connective reasoning and emphasis. Continuity comes from
  passing last night's note + the knowledge base ("you previously said X — is it
  still true?").
- **Output contract:** structured (JSON) so the orchestrator can split narrative vs
  the discrete insight lines reliably.

### 5.4 `cli.py` — `learn` subcommand (orchestrator, thin)

```
python -m trading_bot.cli learn --config config/default_config.yaml
    [--date YYYY-MM-DD]   # default: today ET
    [--no-llm]            # force deterministic templates (offline/testing)
    [--no-bridge]         # skip the CC push (local-only run)
    [--days N]            # lookback window for outcomes/funnel (default 120)
```

Steps: load config → read inputs (fail-quiet per source) → `build_nightly_facts`
→ load prior knowledge → `update_knowledge` → `narrate` → write the four sinks
(each wrapped) → print a summary. Idempotent: re-running a date overwrites that
date's note + re-merges knowledge from history (deterministic).

### 5.5 Sinks
- `vault/learning/YYYY-MM-DD.md` — dated lessons note (narrative + facts tables + links).
- `vault/learning/_knowledge.md` + `reports/learning_knowledge.json` — living knowledge.
- `reports/agent_insights.json` — appended insight lines (existing `agent_bridge` schema:
  `{date, category, insight, confidence, symbols, status}`); a new
  `record_agent_insights_batch()` helper writes many at once and dedups by (date, insight).
- CC bridge — see §6.

## 6. CC bridge contract (feeds Tony's 2:00am)

- **Path:** `{command_center_dir}/bridge/tony-stocks/learning/YYYY-MM-DD.md`
  (a `learning/` subfolder beside the existing daily bridges; `command_center_dir`
  already in config = `C:/Users/alexa/Downloads/AI Operations Command Center`).
- **Front-matter:** `export_type: bot-self-learning`, `as_of`, `research_only: true`,
  `source: trading-bot`.
- **Body:** the night's narrative + the confirmed/decaying knowledge headlines +
  the dimension tables. Curated for an agent reader, not a dump.
- **Idempotent:** skip if the dated file already exists (same guard as existing bridges).
- **Operator action (one-time, outside this repo):** point CC's 2:00am script at the
  `learning/` subfolder — exact same coordination pattern as `TONY_OUTCOMES_FILE`.
  Documented in `docs/CONTRACTS/`.

## 7. Scheduling — `scripts/register_learning_task.ps1`

Registers a Windows Scheduled Task `TradingBot-NightlyLearning` running daily at
1:30am: `python -m trading_bot.cli learn --config config/default_config.yaml`
with `PYTHONPATH=src`, logging to `logs/learning.err`. Idempotent (delete+recreate).
Script also prints the manual `schtasks` command and how to disable/retime. Safe
unattended because the job is read-only on all trading surfaces (§3).

## 8. Config — new `learning:` block in `default_config.yaml`

```yaml
learning:
  enabled: true
  model: claude-sonnet-4-6
  use_llm: true            # false => deterministic templates only
  min_sample: 5            # per-dimension sample floor before a confident verdict
  lookback_days: 120
  knowledge_history_cap: 30   # rolling points kept per knowledge item
  bridge_to_cc: true
```

Loaded onto `settings` like the existing `pre_screener` / `research_funnel` blocks.

## 9. Error handling & safety

- Every input read and every sink write is individually try/except'd and logged —
  one missing/corrupt file degrades that piece, never the whole run.
- LLM failure → deterministic templates (run still completes fully).
- Missing CC dir → skip bridge, complete locally.
- No exceptions propagate out of `run_learn` to the scheduler (exit 0 on partial).
- Deterministic numbers are the contract; the LLM is decoration that can't corrupt facts.

## 10. Testing strategy

**Unit (pure, TDD):**
- `build_nightly_facts` — each of the 10 dimensions with synthetic fixtures; sample-size
  gating; empty/thin-data → `insufficient`; numeric correctness (win-rate, avg-R, expectancy).
- `update_knowledge` — promote/demote transitions, trend computation, history cap,
  first-seen preservation, idempotent re-merge.
- `narrate` — with a fake/stub client (verify it only receives facts, never raw rows);
  fallback path when client raises / key missing; output-contract parsing.

**Integration (tmp paths):**
- Sink writers — vault note, knowledge md+json round-trip, `agent_insights` batch append +
  dedup, CC bridge file + idempotency skip.
- `learn` CLI smoke — `--no-llm` end-to-end on fixtures produces all four artifacts.

Targets the project's TDD norm; full suite must stay green.

## 11. Final comprehensive mock test (the tandem dress-rehearsal)

A single end-to-end harness (`scripts/mock_learning_e2e.ps1` + a pytest e2e marker)
that exercises the **whole process in tandem with the CC contract**, against an
isolated temp vault + temp CC dir (never the live one), using a seeded synthetic
dataset (a realistic mix of target/stop/closed/expired outcomes + Tony verdicts):

1. Seed synthetic outcomes + teaching + snapshot history.
2. Run `learn` (real deterministic core; LLM in `--no-llm` for determinism, plus one
   live-LLM pass guarded by key-present to confirm the API path).
3. Assert all four sinks produced, schemas valid, numbers match hand-computed expectations.
4. Assert the CC bridge file lands in `{tempCC}/bridge/tony-stocks/learning/` with the
   agreed front-matter — i.e. exactly what CC's 2:00am script will read.
5. Re-run → assert idempotency (no dup insights, bridge skip, knowledge re-merge stable).
6. Simulate "next night" with evolved data → assert an edge **promotes** and a decayed
   edge **demotes** (proves the evolve loop works over time).
7. Run the full pytest suite → green.
8. Manual dashboard check: insights surface in the existing `agent_insights` UI.

This is the gate before we call it done: prove the brain learns, evolves, and the
hand-off to CC is byte-correct — without ever touching the live vault, CC, or any order.

## 12. Files

**New**
- `src/trading_bot/analytics/nightly_learning.py` — facts + knowledge (pure)
- `src/trading_bot/analytics/learning_narrator.py` — LLM layer (fail-safe)
- `tests/test_nightly_learning.py`, `tests/test_learning_narrator.py`, `tests/test_learning_cli.py`
- `scripts/register_learning_task.ps1` — scheduled-task setup
- `scripts/mock_learning_e2e.ps1` — §11 harness
- `docs/CONTRACTS/self-learning-bridge.md` — the CC hand-off contract

**Edit**
- `src/trading_bot/cli.py` — `learn` subcommand + `run_learn`
- `src/trading_bot/agent_bridge.py` — `record_agent_insights_batch()` + dedup
- `src/trading_bot/vault/writer.py` (or new `vault/learning_writer.py`) — vault note + `_knowledge.md` renderers
- `src/trading_bot/settings.py` — `learning` config field
- `config/default_config.yaml` — `learning:` block
- `AGENT_STATE.md`, `ROADMAP.md` — handoff + roadmap entry

## 13. Risks & mitigations

| Risk | Mitigation |
|---|---|
| LLM hallucinates P&L | LLM only ever sees computed `NightlyFacts`; numbers are template-rendered; grounding rule in prompt. |
| Overfitting to tiny samples | `min_sample` gating → `insufficient` confidence; week-over-week trend before promoting. |
| Nightly job crashes the box / hits orders | Read-only on all trading; isolated process; fail-quiet; exit 0 on partial. |
| CC contract drift | Front-matter + path fixed in `docs/CONTRACTS/`; idempotent; §11 asserts the exact bridge output. |
| API cost | One sonnet call/night (~pennies); `use_llm:false` kill switch. |
| Live data clobbered during testing | §11 runs entirely in temp vault + temp CC dir; never the live paths. |
