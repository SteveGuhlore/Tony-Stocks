# scripts/register_learning_task.ps1
# Registers a nightly (default 1:30am) self-learning run. The job is READ-ONLY on all
# trading surfaces (no orders, no config edits) so it is safe to run unattended.
#
#   Register:  powershell -ExecutionPolicy Bypass -File .\scripts\register_learning_task.ps1
#   Retime:    ... -Time 02:15
#   Remove:    ... -Remove
param(
  [string]$Time = "01:30",
  [string]$TaskName = "TradingBot-NightlyLearning",
  [switch]$Remove
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

if ($Remove) {
  schtasks /Delete /TN $TaskName /F 2>$null
  Write-Host "Removed scheduled task $TaskName"
  return
}

$inner = "`$env:PYTHONPATH='src'; & '$python' -m trading_bot.cli learn --config config/default_config.yaml *>> logs\learning.err"
$action = "powershell.exe -ExecutionPolicy Bypass -NoProfile -Command `"Set-Location '$repo'; $inner`""

schtasks /Create /TN $TaskName /SC DAILY /ST $Time /F /TR $action /RL LIMITED | Out-Null
Write-Host "Registered '$TaskName' daily at $Time."
Write-Host "  Disable:  schtasks /Change /TN $TaskName /DISABLE"
Write-Host "  Run now:  schtasks /Run /TN $TaskName"
Write-Host "  Remove:   .\scripts\register_learning_task.ps1 -Remove"
