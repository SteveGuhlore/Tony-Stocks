$ErrorActionPreference = "Stop"

Write-Host "Trading Bot Project - tests"

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv..."
    . .\.venv\Scripts\Activate.ps1
}

$localTemp = Join-Path (Get-Location) ".pytest_tmp"
New-Item -ItemType Directory -Force $localTemp | Out-Null
$env:TMP = $localTemp
$env:TEMP = $localTemp

Write-Host "Running compile check..."
$env:PYTHONPATH = "src"
python -m compileall src

Write-Host "Running pytest..."
python -m pytest --basetemp .pytest_tmp
