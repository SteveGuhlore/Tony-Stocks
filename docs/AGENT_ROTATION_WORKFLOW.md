# Agent Rotation Workflow

_Last updated: 2026-05-17_

This project is built for the user’s real workflow: using Codex, Claude, and Cursor based on whichever one still has available usage limits.

## Core principle

Any agent can do any role, but every agent must follow the same project rules.

Do not rely on “Codex always codes” or “Claude only plans.” The actual workflow is:

```text
Available agent works
→ agent documents work
→ next available agent continues from AGENT_STATE.md
```

## Safe rotation process

### Step 1 — Start with a clean status check

```powershell
git status --short
```

If files are modified, the agent must understand why before editing.

### Step 2 — Read shared docs

Required docs:

- `AGENTS.md`
- `AGENT_STATE.md`
- `CURRENT_STATUS.md`
- `ROADMAP.md`
- `TESTING_CHECKLIST.md`

### Step 3 — Scope one task

Bad:

```text
Build the whole trading bot.
```

Good:

```text
Add buy-and-hold baseline comparison to the backtester and tests.
```

### Step 4 — Make the change

Keep the change focused. Avoid touching unrelated modules.

### Step 5 — Run checks

At minimum:

```powershell
pytest
python -m compileall src
```

### Step 6 — Update handoff

Update `AGENT_STATE.md` using `HANDOFF_TEMPLATE.md`.

### Step 7 — Switch agents

The next agent starts by reading `AGENT_STATE.md`, not by guessing.

## What not to do

- Do not let multiple agents edit simultaneously.
- Do not start a new feature before the previous one is tested or documented.
- Do not let a new agent overwrite a previous agent’s work because it did not read context.
- Do not accept giant multi-file rewrites unless the plan is extremely clear.

