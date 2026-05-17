# Trading Bot Project - Testing Checklist

_Last updated: 2026-05-17_

Use this after every meaningful code change.

## Before coding

- Read `AGENTS.md`.
- Read `AGENT_STATE.md`.
- Run `git status --short` if git is initialized.
- Confirm no other agent has active edits.

## Environment checks

```powershell
python --version
pip --version
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Static sanity checks

```powershell
$env:PYTHONPATH = "src"
python -m compileall src
```

## Unit tests

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

Required test areas:

- indicators,
- scoring engine,
- long trade-plan validation,
- snapshot follow-up outcome calculation,
- universe loader,
- database,
- risk manager,
- backtester.

## Scanner smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli scan --config config/default_config.yaml
```

Expected:

- no crash,
- top ranked stocks print,
- `data/trading_bot.db` exists,
- `outputs/latest_scan_results.csv` exists,
- `logs/trading_bot.log` exists.

## Candidate snapshot smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli snapshot --config config/default_config.yaml
```

Expected:

- no crash,
- scan results are still saved,
- candidate snapshot summary prints,
- `candidate_snapshots` table has open/watch rows,
- no paper trades are created.

## Candidate snapshot follow-up smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli update-snapshots --config config/default_config.yaml
```

Expected:

- no crash,
- open/watch snapshots are checked,
- follow-up fields are updated when future bars exist,
- same-day daily demo snapshots may be labeled `insufficient_future_data`,
- no paper trades or orders are created.

## Demo snapshot seed smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli seed-demo-snapshots --config config/default_config.yaml
```

Expected:

- no crash,
- historical demo snapshots are created or skipped as duplicates,
- rows are clearly labeled as demo/testing snapshots,
- seeded rows are not treated as evidence of real market edge,
- no paper trades or orders are created.

## Scheduled Watch Mode smoke test

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1
```

Expected:

- no crash,
- one scan cycle runs,
- eligible candidate snapshots are created or skipped by dedupe cleanly,
- snapshot follow-up update runs if enabled,
- no paper trades or orders are created.

To run while the computer is on:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_watch_mode.ps1
```

To stop: press Ctrl+C in the PowerShell window, or create `data/STOP_WATCH_MODE`.

## Dashboard smoke test

```powershell
streamlit run src/trading_bot/dashboard/app.py
```

Expected:

- dashboard opens,
- latest scan overview is visible,
- ranked stocks table loads.

## Safety checks

- `live_trading_enabled` remains false.
- No real API keys are committed.
- No broker order execution exists in V1 scanner.
- Every scored stock includes entry, stop, target, risk/reward, reasons, and warnings.
- Long setup trade levels must be validated before snapshots, paper trades, or outcome tracking can trust scanner output.
- Eligible buy-opportunity rows must have `stop < entry`, `target > entry`, and positive risk/reward.
- Candidate snapshots are saved as research records only and do not create paper trades or orders.
- Candidate snapshots exclude invalid trade plans by default.
- Snapshot follow-up updates must not create paper trades, broker orders, or live orders.
- Seeded demo snapshots are for dashboard/outcome tracker testing only and are not evidence of real market edge.
- Scheduled Watch Mode is scanning/snapshot collection only. It does not place paper trades or live trades.

## Agent handoff checks

- Update `AGENT_STATE.md`.
- List files changed.
- List commands run.
- Note failures.
- Note next step.
