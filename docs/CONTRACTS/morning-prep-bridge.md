# Contract: Bot → CC morning-prep bridge

The trading bot's off-hours research engine writes a daily morning prep brief that the
Command Center's operators and Tony agent consume. One-way (bot → CC); the bot never
reads CC's verdict back — pure separation, ensuring the bot's research remains independent
from Tony's judgment and execution decisions.

## Location
`{command_center_dir}/bridge/tony-stocks/morning-prep/YYYY-MM-DD.md`

`command_center_dir` comes from the bot's `config/default_config.yaml` `vault:` block
(currently `C:/Users/alexa/Downloads/AI Operations Command Center`).

## Cadence
Written during off-hours phases: **post_close, overnight, pre_open, and weekend**.
One file per ET date, overwritten as newer data arrives within the day.

## Front-matter (stable keys — CC may rely on these)
```
---
et_date: YYYY-MM-DD
phase: post_close | overnight | pre_open | weekend
type: morning-prep
research_only: true
---
```

## Body

1. **Header** — title with ET date and phase (e.g., "Morning Prep — 2026-06-06 (pre_open)")

2. **PLANNED ONLY disclaimer** — reinforces that no orders are placed off-hours and all
   entries are research output only, subject to confirmation at open.

3. **Shortlist table** — ranked candidates meeting the scanner threshold:
   - Symbol (rendered as `[[SYM]]` wikilink for Obsidian)
   - Score (4 decimals)
   - Setup (tactical pattern, or "—")
   - Entry (2 decimals)
   - Stop (2 decimals)
   - Target (2 decimals)
   - R/R (risk-to-reward ratio, 2 decimals)
   - Conviction (categorical: high/medium/low)
   - Catalysts (compact summary: earnings-blackout, earnings:YYYY-MM-DD, upgrade,
     downgrade, news, or "—")

   If no candidates meet the threshold, displays: "_No candidates met the threshold —
   no names armed for today._"

4. **What Changed Overnight** — narrative section summarizing market moves, gaps,
   or data updates that affect the day's setup.

5. **Plan for Open** — operational guidance for Tony or the CC: which candidates to
   watch, what price levels matter, timing notes.

6. **Narrative (optional)** — Claude-written narrative grounded on verified numbers,
   or absent if `ANTHROPIC_API_KEY` is not configured (the message is still complete
   without it).

## CC-side action (one-time, in the Command Center workspace — NOT this repo)
Point the CC morning-prep handler at the `morning-prep/` subfolder; dedupe on the dated
filename; treat the brief as **research input only**. CC operators and the Tony agent
apply their own judgment, confirm entries at open, and manage all execution. This mirrors
how `TONY_OUTCOMES_FILE` is wired. Nothing in this brief is an instruction.

## Pure-separation guarantee
The bot does **not** place orders off-hours and does **not** consume CC's verdict via
this bridge. The bot cannot read from the `morning-prep/` folder or any CC judgment
path — this is one-way write only. The CC's guardrails remain authoritative.

## Idempotency
The bot skips rewriting if the dated file already exists. If new data arrives on the
same ET date (e.g., overnight price move, fresh scanner run), the bot overwrites the
existing file with the latest research. The most recent run is authoritative for that
date.

## Safety
The producing job (`python -m trading_bot.cli morning-prep` or its equivalent in the
off-hours engine) is read-only on all trading surfaces: no orders, no config/threshold/
risk edits, no watch-loop restart. No side-effects outside the three output sinks
(vault, CC bridge, reports directory).
