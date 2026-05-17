$ErrorActionPreference = "Stop"

Write-Host "Trading Bot Project - swing research scanner"

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv..."
    . .\.venv\Scripts\Activate.ps1
}

Write-Host "Running scanner with config/default_config.yaml..."
$env:PYTHONPATH = "src"
python -m trading_bot.cli scan --config config/default_config.yaml
