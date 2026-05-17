$ErrorActionPreference = "Stop"

Write-Host "Trading Bot Project - seed demo snapshots"

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv..."
    . .\.venv\Scripts\Activate.ps1
}

Write-Host "Seeding demo-only historical candidate snapshots..."
$env:PYTHONPATH = "src"
python -m trading_bot.cli seed-demo-snapshots --config config/default_config.yaml
