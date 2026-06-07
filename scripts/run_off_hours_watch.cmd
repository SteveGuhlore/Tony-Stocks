@echo off
REM Off-hours research engine launcher, called by the Windows Scheduled Task.
REM READ-ONLY on all trading surfaces: no orders, no broker calls, no config/risk edits.
REM Places ZERO trades. The engine prepares a ranked Morning Watchlist plan for the next
REM open; entries fire only during market hours via the existing live watch loop.
REM
REM The off-hours-watch command runs an inverse watch loop:
REM   - During market hours (09:30-16:00 ET): sleeps, does nothing.
REM   - Off-hours (weekdays 16:30->09:00 ET + weekends): runs off-hours-prep once per
REM     date+phase (idempotent), writing to reports/morning_prep/, vault/morning_prep/,
REM     and the CC bridge. Honors data\STOP_OFF_HOURS kill file.
REM
REM To enable the engine, set off_hours.enabled: true in config/default_config.yaml.
REM Logs to logs\off_hours.err.
cd /d "%~dp0.."
set PYTHONPATH=src
if not exist logs mkdir logs
".\.venv\Scripts\python.exe" -m trading_bot.cli off-hours-watch --config config/default_config.yaml >> "logs\off_hours.err" 2>&1
