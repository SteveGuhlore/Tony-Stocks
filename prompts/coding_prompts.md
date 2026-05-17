# Coding Prompts

## Add a module safely

```text
Read AGENTS.md and AGENT_STATE.md first.

I want to add [module/feature].

Before editing, identify:
1. files to inspect,
2. files to change,
3. risks,
4. tests to add/run.

Then implement the smallest safe version.

After editing, run tests if possible and update AGENT_STATE.md.
```

## Fix a bug safely

```text
Read AGENTS.md, AGENT_STATE.md, TESTING_CHECKLIST.md, and the relevant code.

Bug:
[describe bug]

Do not rewrite unrelated files.
Find the smallest safe fix, add/update tests, and update AGENT_STATE.md.
```

## Improve backtest report

```text
Read src/trading_bot/backtester.py, src/trading_bot/metrics.py, tests/, and AGENT_STATE.md.

Improve report output without changing strategy behavior.
Include tests and update AGENT_STATE.md.
```
