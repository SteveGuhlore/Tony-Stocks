# Trading Bot Project — UI and CLI Rules

_Last updated: 2026-05-17_

## 1. CLI first

Start with a reliable command-line interface before building dashboards.

Good commands:

```powershell
python src/main.py backtest --ticker SPY --period 1y
python src/main.py backtest --csv data/raw/SPY.csv
pytest
```

## 2. Error messages

Errors should tell the user what happened and what to do next.

Bad:

```text
KeyError: close
```

Better:

```text
Missing required column 'close'. Your CSV must include date, open, high, low, close, volume.
```

## 3. Reports

Backtest reports should be clear and not overcomplicated.

Show:

- ticker/date range,
- strategy name,
- starting capital,
- ending equity,
- return,
- max drawdown,
- trade count,
- win rate,
- warnings.

## 4. Future dashboard rule

Only build a dashboard after CLI reports are useful.

Dashboard candidates:

- Streamlit dashboard,
- equity curve chart,
- drawdown chart,
- trade list,
- strategy comparison table.

