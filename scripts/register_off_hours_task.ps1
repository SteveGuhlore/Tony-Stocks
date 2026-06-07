# scripts/register_off_hours_task.ps1
# Registers a daily (default at logon) off-hours research engine run. The job is READ-ONLY on
# all trading surfaces (no orders, no broker calls, no config/risk edits) so it is safe to run
# unattended. It places ZERO trades — the engine only prepares a ranked Morning Watchlist plan
# for the next open. Entries fire exclusively during market hours via the existing live watch loop.
#
# The task points at scripts\run_off_hours_watch.cmd, which runs:
#   .venv\Scripts\python.exe -m trading_bot.cli off-hours-watch --config config/default_config.yaml
# The off-hours-watch command is an inverse loop: during market hours it sleeps; off-hours it
# runs off-hours-prep once per date+phase (idempotent). Honors data\STOP_OFF_HOURS kill file.
#
# PREREQUISITE: set off_hours.enabled: true in config/default_config.yaml (default OFF).
#
#   Register:  powershell -ExecutionPolicy Bypass -File .\scripts\register_off_hours_task.ps1
#   Retime:    ... -Time 16:35
#   Remove:    ... -Remove
param(
  [string]$Time = "16:35",
  [string]$TaskName = "TradingBot-OffHoursWatch",
  [switch]$Remove
)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$launcher = Join-Path $repo "scripts\run_off_hours_watch.cmd"

if ($Remove) {
  schtasks /Delete /TN $TaskName /F 2>$null
  Write-Host "Removed scheduled task $TaskName"
  return
}

if (-not (Test-Path $launcher)) { throw "Launcher not found: $launcher" }

# Point the task at a launcher .cmd — schtasks mangles nested-quoted inline commands.
schtasks /Create /TN $TaskName /SC DAILY /ST $Time /F /TR "$launcher" /RL LIMITED | Out-Null
Write-Host "Registered '$TaskName' daily at $Time."
Write-Host "  NOTE: Ensure off_hours.enabled: true in config/default_config.yaml to activate."
Write-Host "  Disable:  schtasks /Change /TN $TaskName /DISABLE"
Write-Host "  Run now:  schtasks /Run /TN $TaskName"
Write-Host "  Remove:   .\scripts\register_off_hours_task.ps1 -Remove"
