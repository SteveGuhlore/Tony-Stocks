$ErrorActionPreference = "Stop"

Write-Host "Trading Bot Project - dashboard"

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv..."
    . .\.venv\Scripts\Activate.ps1
}

Write-Host "Starting Streamlit dashboard..."
streamlit run src/trading_bot/dashboard/app.py
