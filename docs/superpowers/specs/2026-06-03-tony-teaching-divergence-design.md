# Design Spec — Tony Teaching / Divergence Memory layer

**Date:** 2026-06-03
**Status:** Draft for review (build in a fresh session)
**Scope:** Turn Tony's verdicts into a *learning* layer instead of an execution cross-link.
The bot trades its own picks independently (pure separation); Tony grades and **explains**
his view on each bot pick; when outcomes resolve we attribute **who was right** and keep a
running teaching record. No Tony order ever touches the bot's paper book.

## Why
Decision (2026-06-03): execution is **pure separation** —
`paper_trading.close_on_command_center_exit: false`. The bot's account = bot entries + bot
stops/targets only; Tony's account = Tony's own calls. That keeps the head-to-head A/B clean.
But Tony's second-pass *reasoning* is valuable signal we shouldn't throw away — so capture it
as memory: "Tony disagreed here and said X because Y → the outcome proved him right/wrong."
Over time this builds an evidence base of **where the 2nd pass actually adds value**, and can
later feed (gated, human-approved) adjustments back into the bot's scoring — closing the
learning loop without ever letting Tony silently take over the bot's book.

## Inputs (all already produced)
- **Bot picks / positions** — `candidate_snapshots` + `paper_positions` (the bot's own action).
- **Tony verdicts + reasoning** — `reports/tony_stocks_verdicts.json` (reaffirm | adjust |
  override | close + reasoning text), keyed `(symbol, date)`.
- **Resolved outcomes** — `reports/tony_stocks_outcomes.json` / `paper_positions` (target/stop/
  closed + return), keyed `(symbol, pick_date)`.

## Core (pure, TDD)
`build_tony_divergence(bot_picks, verdicts, outcomes) -> list[TeachingRecord]`, one per
`(symbol, pick_date)`, joining the three sources and classifying:

| Class | Meaning |
|---|---|
| `agreed_both_right` | Tony reaffirmed, bot held, outcome won |
| `agreed_both_wrong` | Tony reaffirmed, bot held, outcome lost |
| `diverged_tony_right` | Tony said close/adjust/override; the bot's path lost vs Tony's call |
| `diverged_bot_right` | Tony said close/adjust/override; the bot's path won anyway |
| `pending` | Outcome not yet resolved |

Each record preserves Tony's **reasoning text** ("teaches why") + the bot's rationale + the
actual result + return. The "circle back" = when an outcome resolves, a `pending` record is
graded and moves to a resolved class.

## Storage
A `tony_teaching` table (or append-only `reports/tony_teaching_log.json`) accumulating records
with reasoning preserved. Keyed by a stable `pick_id` (SYMBOL-firstdate) for clean re-grading.

## Reporting / surface
- EOD section + a dashboard panel: running tallies per class + a feed of recent divergences
  (symbol, Tony's verdict + why, bot's action, who was right, return). This is the bot-side
  mirror of the CC's scorecard, focused on **Tony-vs-bot divergence with reasoning retained**.
- Reconciles with the CC's own grading (CC grades its verdicts vs outcomes; this adds the
  bot-vs-Tony framing + the teaching memory).

## Phases
1. **Pure divergence builder** — `build_tony_divergence(...)`, TDD with synthetic inputs.
2. **Storage + grader** — persist records; re-grade `pending` when outcomes resolve.
3. **EOD report + dashboard panel** — tallies + reasoning feed.
4. **(Future, gated) learned adjustments** — high-confidence, repeatedly-right Tony divergences
   become *suggested* scoring/rule tweaks routed through the existing approval flow
   (`generate_tony_rule_suggestions` / record-decision), never auto-applied.

## Guardrails
- Tony never executes on the bot's account (pure separation stays).
- Research only; no profitability claims. Teaching adjustments are human-approved, not automatic.
- Preserve reasoning verbatim; grade only against real resolved outcomes.

## Open questions
- `pick_id` stamping on both sides (bot + CC) for bulletproof joins (vs the current
  `(symbol, pick_date)` range-join)?
- How is a "divergence" scored when Tony said *adjust* (not a clean close/hold)? Define the
  adjust→right/wrong rule.
- Confidence threshold + sample size before a teaching record influences a rule suggestion.
