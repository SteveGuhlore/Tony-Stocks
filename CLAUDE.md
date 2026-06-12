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

## Deployment (test-before-deploy — applies to bot AND Command Center)

See `docs/DEPLOY_RULES.md`. Hard rule, mirrored from the CC:

- **Never deploy untested code to the VM**, and never treat `main`/`master` as deployable unless
  the test gate is green (unit suite, plus the tandem sandbox test
  `scripts/full_e2e_sync_test.py --quick`). Quarantine unrelated pre-existing reds; don't normalize red.
- Deploy via the **tandem-safe ritual**: dev in the correct repo/session → push (bot=`main`,
  CC=`master`) → on the VM `bash scripts/deploy/update_vm.sh` → **verify before trusting** (tandem
  test + `systemctl is-active` + a real `/explain`/API hit) → only then resume live.
- Bot and CC must use **different Alpaca paper accounts**; only one operator home runs live at a time
  (VM = production, local = dev).

## Staging Twin Rules (ENFORCED — see docs/STAGING_WORKFLOW.md for the full runbook)

Production (`/opt/trading-bot`, services `tradingbot-{api,watch,web,offhours}`, deploys from
`main`) runs 24/7. **No change ever touches prod directly** — not a hot edit, not a direct
commit, not a restart-with-uncommitted-code. Every change travels:
**dev branch → staging soak (`/opt/trading-bot-staging`) → `scripts/promote_staging.sh` gate →
fast-forward `main` → prod restart (after market close).**

Staging is a tester/debugger ONLY — never a second producer:

- **$0 spend:** staging runs `TONY_LLM_OFFLINE=1` with ALL LLM keys (ANTHROPIC/GEMINI/GOOGLE)
  AND enrichment keys (FINNHUB/FMP/TWELVE_DATA/POLYGON) blank. Alpaca IEX data + paper trading
  are free and stay live. Never put real LLM/enrichment keys in staging except the documented
  full-fidelity opt-in, reverted after one soak.
- **Own paper account:** staging trades its OWN throwaway Alpaca paper account ($100k, matching
  scanner prod) — never prod's keys. Verify before every start:
  `grep -nE '^ALPACA_(API_KEY|SECRET_KEY)=' /opt/trading-bot-staging/.env`.
- **On-demand:** start for a soak, stop after promotion (`systemctl start/stop`, never `enable`
  — staging units must not survive a reboot).
- **Claude sessions never run VM commands against `/opt/trading-bot`.** Staging shell commands
  are given to the operator to run; prod deploys happen only via the promote-gate output.
- The Command Center (`/opt/command-center`, twin `/opt/command-center-staging`, flag
  `CC_LLM_OFFLINE`) follows the identical rules — its own CLAUDE.md carries them.

## Guardrails

- Do not claim profitability.
- Do not bypass risk rules.
- Do not hard-code API keys.
- Do not enable live trading by default.

