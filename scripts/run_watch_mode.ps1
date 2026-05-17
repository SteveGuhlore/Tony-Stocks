param(
    [int]$MaxCycles = 0
)

$ErrorActionPreference = "Stop"

Write-Host "Trading Bot Project - Scheduled Watch Mode"
Write-Host "Research mode only: this scans, saves candidate snapshots, and optionally updates snapshot outcomes."
Write-Host "This does not create paper trades, broker orders, or live trades."
Write-Host ""
Write-Host "Leave this PowerShell window open while watch mode runs."
Write-Host "Press Ctrl+C to stop. Keep the computer awake."
Write-Host "You can also create data/STOP_WATCH_MODE to request a clean stop."
Write-Host ""

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv..."
    . .\.venv\Scripts\Activate.ps1
}

$env:PYTHONPATH = "src"

if ($MaxCycles -gt 0) {
    Write-Host "Running watch mode for $MaxCycles cycle(s)..."
    python -m trading_bot.cli watch --config config/default_config.yaml --max-cycles $MaxCycles
}
else {
    Write-Host "Running watch mode until Ctrl+C or data/STOP_WATCH_MODE..."
    python -m trading_bot.cli watch --config config/default_config.yaml
}
