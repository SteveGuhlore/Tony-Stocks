@echo off
REM Nightly self-learning launcher, called by the Windows Scheduled Task.
REM Read-only on trading (no orders, no config/risk edits). Logs to logs\learning.err.
REM
REM Two steps, both read-only & fail-quiet:
REM   1) funnel-eval --save-report : refresh reports\<date>\funnel_eval.json (audit trail)
REM   2) learn                     : self-refreshes reports\funnel_eval.json then grades.
REM The learn step is self-contained (it re-runs the funnel eval into the path it reads),
REM so step 1 is belt-and-suspenders; if it errors, learning still runs and exits clean.
cd /d "%~dp0.."
set PYTHONPATH=src
if not exist logs mkdir logs
".\.venv\Scripts\python.exe" -m trading_bot.cli funnel-eval --config config/default_config.yaml --save-report >> "logs\learning.err" 2>&1
".\.venv\Scripts\python.exe" -m trading_bot.cli learn --config config/default_config.yaml >> "logs\learning.err" 2>&1
