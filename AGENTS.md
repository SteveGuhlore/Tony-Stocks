# Trading Bot Project — Agent Rules

_Last updated: 2026-05-17_

This file is the highest-priority local rule file for all AI coding agents used in this project.

## 1. Your actual agent workflow

The user will use **Codex, Claude, and Cursor as their usage limits allow**. That means agents are not permanently locked into one role. Any available agent may be used for reading, planning, coding, debugging, documentation, or review.

This changes the workflow from role-based to **rotating-agent development**.

```text
Use whichever agent is available
→ require that agent to read the same project docs
→ make one scoped change
→ run checks
→ update handoff notes
→ switch agents only after the current work state is documented
```

## 2. Universal rule for all agents

Every agent must behave like a responsible senior developer, not like a random code generator.

All agents must:

- Read the required context before editing.
- Check current project status before changing files.
- Keep changes scoped.
- Preserve risk controls.
- Never hard-code secrets or broker keys.
- Avoid making profitability claims.
- Prefer paper trading and backtesting before live trading.
- Update `AGENT_STATE.md` before handing off to another agent.
- Explain exactly what changed and how to test it.

## 3. Required reading before edits

Before any code change, the active agent must read:

1. `AGENTS.md`
2. `PROJECT_CONTEXT.md`
3. `CURRENT_STATUS.md`
4. `ROADMAP.md`
5. `ARCHITECTURE_RULES.md`
6. `DESIGN_RULES.md`
7. `TESTING_CHECKLIST.md`
8. `KNOWN_BACKLOG.md`
9. `FILE_STRUCTURE.md`
10. `AGENT_STATE.md`

For trading-specific work, also read the relevant file in `docs/`:

- Strategy work: `docs/STRATEGY_GUIDELINES.md`
- Broker/API work: `docs/BROKER_SETUP.md`
- Risk work: `docs/LEGAL_AND_RISK.md`
- Data work: `docs/DATA_SOURCES.md`
- AI workflow work: `docs/AGENT_ROTATION_WORKFLOW.md`

## 4. Agent handoff rule

Before the user switches from one agent to another, the current agent must update or produce a handoff using `HANDOFF_TEMPLATE.md`.

The handoff must include:

- Current task.
- Files changed.
- Files inspected.
- Tests/checks run.
- Known failures.
- Next recommended step.
- Any risky assumptions.
- Whether the repo is safe to continue from.

If the current agent cannot edit files, it should output the handoff text so the user can paste it into `AGENT_STATE.md`.

## 5. No concurrent editing

Do not let two agents edit the project at the same time. This is the fastest way to create conflicting code and stale context.

Use this rule:

```text
One active coding agent at a time.
One committed or clearly documented state before switching.
```

## 6. Git safety rules

Before edits:

```powershell
git status --short
```

After edits:

```powershell
git diff --check
pytest
```

Do not auto-commit unless the user explicitly asks. If committing, use clear messages like:

```text
2026-05-17 1530 - Backtest - Add moving average strategy report
```

## 7. Trading safety rules

No agent may implement live trading by default.

Live trading requires all of these first:

- Passing unit tests.
- Passing backtest sanity checks.
- Passing paper-trading tests.
- Explicit user approval.
- API keys stored only in environment variables or `.env` ignored by git.
- Risk controls enabled by default.
- Emergency stop/kill switch available.
- Logs written for every decision and order.

## 8. Code delivery rules

- Small files: provide full updated file content.
- Large files: edit file directly and summarize changes.
- Do not say “the rest remains unchanged” as the only delivery for a changed file.
- Give exact paths relative to the project root.

## 9. Documentation update rule

After meaningful changes, update documentation only where relevant:

- `CURRENT_STATUS.md` for confirmed current state.
- `KNOWN_BACKLOG.md` for bugs, risks, or deferred improvements.
- `ROADMAP.md` for milestone or phase changes.
- `FILE_STRUCTURE.md` if files/folders were added or moved.
- `AGENT_STATE.md` for handoff context.

Do not rewrite the whole roadmap after every small code change.

## 10. Current project priority

The current priority is not to make a bot that trades real money immediately.

The correct order is:

1. Build clean research/backtesting infrastructure.
2. Add simple explainable strategies.
3. Add risk controls.
4. Add reporting.
5. Add paper trading.
6. Run enough tests to understand failures.
7. Only then consider live trading with tiny size and explicit approval.

