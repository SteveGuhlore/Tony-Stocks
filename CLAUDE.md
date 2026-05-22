# Claude Instructions — Trading Bot Project

Claude may be used as planner, coder, reviewer, or debugger depending on user limits. Do not assume Claude is only a planner.

## Project status

Currently at **V34A**. See `CURRENT_STATUS.md` for full status. See `AGENT_STATE.md` for the latest handoff.

## Quick-start commands (Windows PowerShell)

```powershell
# Run full test suite (preferred — sets correct basetemp)
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1

# Run tests directly (also works)
$env:PYTHONPATH = "src"; python -m pytest

# Launch dashboard (opens http://localhost:8501)
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1

# End-of-day report
$env:PYTHONPATH = "src"; python -m trading_bot.cli eod-report --config config/default_config.yaml

# Full post-session review
$env:PYTHONPATH = "src"; python -m trading_bot.cli after-market-review --config config/default_config.yaml

# One-cycle watch smoke test
$env:PYTHONPATH = "src"; python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1
```

> **Windows gotcha:** Always set `$env:PYTHONPATH = "src"` before running CLI commands directly — the scripts do this automatically.

## Required behavior

Before editing or advising, read:

- `AGENTS.md`
- `PROJECT_CONTEXT.md`
- `CURRENT_STATUS.md`
- `ROADMAP.md`
- `ARCHITECTURE_RULES.md`
- `DESIGN_RULES.md`
- `TESTING_CHECKLIST.md`
- `FILE_STRUCTURE.md`
- `KNOWN_BACKLOG.md`
- `AGENT_STATE.md`

## Environment setup

- Copy `.env.example` → `.env` and fill in `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` for real data.
- Without keys, all commands run in demo mode — safe for testing.
- Never commit `.env` or API keys.

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

