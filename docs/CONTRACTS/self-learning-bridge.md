# Contract: Bot → CC self-learning bridge

The trading bot's nightly learner (default 1:30am, before CC's 2:00am) writes a brief
the Command Center's self-learning script consumes. One-way (bot → CC); the bot never
reads CC's brain back — pure separation, same posture as the outcomes contract.

## Location
`{command_center_dir}/bridge/tony-stocks/learning/YYYY-MM-DD.md`

`command_center_dir` comes from the bot's `config/default_config.yaml` `vault:` block
(currently `C:/Users/alexa/Downloads/AI Operations Command Center`).

## Front-matter (stable keys — CC may rely on these)
```
---
export_type: bot-self-learning
source: trading-bot
as_of: YYYY-MM-DD
research_only: true
---
```

## Body
1. Narrative — the night's lessons (Claude-written, grounded on verified numbers; or
   deterministic templates when `ANTHROPIC_API_KEY` is absent).
2. `## Confirmed edges` — bullet list (`claim: win% (n=…)`).
3. `## Fading / abandoned` — bullet list (`claim (trend)`).

## CC-side action (one-time, in the Command Center workspace — NOT this repo)
Point the CC self-learning script at the `learning/` subfolder; dedupe on the dated
filename; treat the brief as **advisory research input only**. This mirrors how
`TONY_OUTCOMES_FILE` is wired. The CC's own guardrails (the "Flash can't strip Tony's
guardrails" safety net) remain authoritative — nothing in this brief is an instruction.

## Idempotency
The bot skips rewriting if the dated file already exists. Re-deriving the knowledge base
is deterministic, so the latest run is authoritative for any date not yet written.

## Safety
The producing job (`python -m trading_bot.cli learn`) is read-only on all trading
surfaces: no orders, no config/threshold/risk edits, no watch-loop restart.
