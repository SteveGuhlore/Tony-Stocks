@echo off
REM Nightly self-learning launcher, called by the Windows Scheduled Task.
REM Read-only on trading (no orders, no config/risk edits). Logs to logs\learning.err.
cd /d "%~dp0.."
set PYTHONPATH=src
if not exist logs mkdir logs
".\.venv\Scripts\python.exe" -m trading_bot.cli learn --config config/default_config.yaml >> "logs\learning.err" 2>&1
