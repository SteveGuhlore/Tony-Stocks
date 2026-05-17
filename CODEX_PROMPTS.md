# Trading Bot Project — Prompt Templates

_Last updated: 2026-05-17_

Use these with Codex, Claude, Cursor, or any available agent. The user may rotate agents as limits allow.

## 1. First inspection prompt

```text
Read AGENTS.md, AGENT_STATE.md, PROJECT_CONTEXT.md, CURRENT_STATUS.md, ROADMAP.md, ARCHITECTURE_RULES.md, DESIGN_RULES.md, TESTING_CHECKLIST.md, FILE_STRUCTURE.md, and KNOWN_BACKLOG.md.

Do not edit yet.

Inspect the project and tell me:
1. what the project currently contains,
2. whether the code structure matches FILE_STRUCTURE.md,
3. what tests exist,
4. whether live trading is disabled,
5. the safest next task.
```

## 2. Start a scoped task prompt

```text
Read AGENTS.md and AGENT_STATE.md first.

Task:
[describe task]

Before editing, tell me:
1. files you will inspect,
2. files you expect to change,
3. risks,
4. tests you will run.

Then implement only the scoped task.

After editing:
1. summarize changed files,
2. show commands/tests run,
3. update AGENT_STATE.md with a handoff.
```

## 3. Backtester improvement prompt

```text
Read AGENTS.md, AGENT_STATE.md, ARCHITECTURE_RULES.md, TESTING_CHECKLIST.md, and src/trading_bot/backtester.py.

Improve the backtester without changing strategy behavior.

Goals:
- clearer metrics,
- cleaner trade logs,
- no live trading,
- tests updated.

Keep changes scoped and update AGENT_STATE.md.
```

## 4. Strategy implementation prompt

```text
Read AGENTS.md, DESIGN_RULES.md, docs/STRATEGY_GUIDELINES.md, and AGENT_STATE.md.

Create or improve a simple explainable strategy.

Rules:
- no black-box ML,
- no live trading,
- use RiskManager,
- include tests,
- document assumptions,
- update AGENT_STATE.md.
```

## 5. Handoff prompt

```text
Create a handoff for the next agent using HANDOFF_TEMPLATE.md.

Include:
- what changed,
- files touched,
- commands run,
- tests passed/failed,
- next step,
- stop conditions.

Update AGENT_STATE.md if you can edit files. Otherwise output the handoff text for me to paste.
```

