# Trading Bot Agent Project

This is a Python stock scanner and research workspace designed for rotating AI-agent development with Codex, Claude, and Cursor. The V1 goal is a practical scanner that ranks stocks for manual research and paper tracking. It does not place real trades.

## What V1 Does

- Loads a starter stock universe from `config/universe_config.yaml`.
- Generates deterministic demo OHLCV data without API keys.
- Calculates SMA, EMA, RSI, ATR, volatility, returns, relative volume, dollar volume, and rolling highs/lows.
- Scores stocks from 0 to 100 using transparent configurable weights in `config/scoring_config.yaml`.
- Saves each scan run and result set to SQLite at `data/trading_bot.db`.
- Exports latest ranked results to `outputs/latest_scan_results.csv`.
- Provides a Streamlit dashboard for ranked stocks, stock detail, manual picks, paper trade journal, and performance summaries.

## What V1 Does Not Do

- No live trading.
- No broker order execution.
- No margin, leverage, options, or short-selling logic.
- No hardcoded API keys.
- No black-box AI trade decisions.
- No profitability guarantees or investment advice.

## Setup

Windows PowerShell:

```powershell
cd "C:\Users\alexa\Downloads\TradingBotAgentProject"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If `python` is not recognized, install Python from python.org or the Microsoft Store, then reopen PowerShell.

## Run Tests

```powershell
.\scripts\run_tests.ps1
```

Equivalent manual commands:

```powershell
$env:PYTHONPATH = "src"
python -m compileall src
python -m pytest
```

## Run First Scan

```powershell
.\scripts\run_scanner.ps1
```

Equivalent manual command:

```powershell
$env:PYTHONPATH = "src"
python -m trading_bot.cli scan --config config/default_config.yaml
```

The scanner writes:

- SQLite database: `data/trading_bot.db`
- Latest CSV export: `outputs/latest_scan_results.csv`
- Log file: `logs/trading_bot.log`

## Open Dashboard

Run a scan first, then:

```powershell
.\scripts\run_dashboard.ps1
```

Equivalent manual command:

```powershell
streamlit run src/trading_bot/dashboard/app.py
```

## API Keys Later

Copy `.env.example` to `.env` and fill keys only on your machine:

```text
POLYGON_API_KEY=
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
FINNHUB_API_KEY=
FMP_API_KEY=
TWELVE_DATA_API_KEY=
```

Real provider adapters are placeholders in V1. API keys must stay in environment variables or `.env`, never in committed code.

## Safety

This project is a research and paper-tracking tool. Scores are ranking signals for manual review, not investment advice. Live trading remains disabled by default with `live_trading_enabled: false` and requires explicit future approval plus separate risk gates.
