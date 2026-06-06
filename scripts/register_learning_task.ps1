# scripts/register_learning_task.ps1
# Registers a nightly (default 1:30am) self-learning run. The job is READ-ONLY on all
# trading surfaces (no orders, no config edits) so it is safe to run unattended.
#
# The task points at scripts\run_nightly_learning.cmd, which runs two read-only steps
# via .venv\Scripts\python.exe: (1) funnel-eval --save-report to refresh the funnel
# evaluation, then (2) learn, which self-refreshes reports\funnel_eval.json and grades
# outcomes. Both steps are fail-quiet so the 1:30am run always completes.
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
$launcher = Join-Path $repo "scripts\run_nightly_learning.cmd"

if ($Remove) {
  schtasks /Delete /TN $TaskName /F 2>$null
  Write-Host "Removed scheduled task $TaskName"
  return
}

if (-not (Test-Path $launcher)) { throw "Launcher not found: $launcher" }

# Point the task at a launcher .cmd — schtasks mangles nested-quoted inline commands.
schtasks /Create /TN $TaskName /SC DAILY /ST $Time /F /TR "$launcher" /RL LIMITED | Out-Null
Write-Host "Registered '$TaskName' daily at $Time."
Write-Host "  Disable:  schtasks /Change /TN $TaskName /DISABLE"
Write-Host "  Run now:  schtasks /Run /TN $TaskName"
Write-Host "  Remove:   .\scripts\register_learning_task.ps1 -Remove"
