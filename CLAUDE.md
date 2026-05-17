# Claude Instructions — Trading Bot Project

Claude may be used as planner, coder, reviewer, or debugger depending on user limits. Do not assume Claude is only a planner.

## Required behavior

Before editing or advising, read:

- `AGENTS.md`
- `PROJECT_CONTEXT.md`
- `CURRENT_STATUS.md`
- `ROADMAP.md`
- `ARCHITECTURE_RULES.md`
- `DESIGN_RULES.md`
- `TESTING_CHECKLIST.md`
- `AGENT_STATE.md`

## If Claude is coding

Claude must:

- keep changes scoped,
- update tests when needed,
- run or instruct the user to run tests,
- update `AGENT_STATE.md` before handoff,
- avoid live trading unless explicitly requested and all safety gates are met.

## If Claude is planning

Claude must produce:

- exact files to change,
- risk notes,
- test checklist,
- a clear prompt for the next agent if the user switches.

## Guardrails

- Do not claim profitability.
- Do not bypass risk rules.
- Do not hard-code API keys.
- Do not enable live trading by default.

