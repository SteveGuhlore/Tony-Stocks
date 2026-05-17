$ErrorActionPreference = "Stop"

Write-Host "Trading Bot Project - candidate snapshot follow-up update"

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv..."
    . .\.venv\Scripts\Activate.ps1
}

Write-Host "Updating candidate snapshots with config/default_config.yaml..."
$env:PYTHONPATH = "src"
python -m trading_bot.cli update-snapshots --config config/default_config.yaml
