# CLI Setup Guide

## Windows PowerShell setup

```powershell
cd "C:\Path\To\trading_bot_agent_project"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pytest
```

## Run sample backtest

```powershell
python src/main.py backtest --ticker SPY --period 1y
```

## Run from CSV later

```powershell
python src/main.py backtest --csv data/raw/SPY.csv
```

## Start an agent session

```powershell
.\scripts\agent_start_check.ps1
```

Then paste the output into whichever AI agent you are using.

