#!/usr/bin/env bash
# update_vm.sh — pull latest code for the bot + Command Center and restart services.
#
# RUN THIS ON THE VM whenever you've pushed changes to GitHub:
#   bash /opt/trading-bot/scripts/deploy/update_vm.sh
#
# It does NOT re-clone — the repos are already in /opt. It git-pulls both,
# refreshes dependencies if they changed, rebuilds the dashboard, and restarts
# the systemd services. Read-only on trading surfaces; safe to run anytime.
set -euo pipefail

BOT_DIR="${BOT_DIR:-/opt/trading-bot}"
CC_DIR="${CC_DIR:-/opt/command-center}"

echo ">> Updating trading-bot ($BOT_DIR)..."
git -C "$BOT_DIR" pull --ff-only
"$BOT_DIR/.venv/bin/pip" install -q -r "$BOT_DIR/requirements.txt" || true
"$BOT_DIR/.venv/bin/pip" install -q "google-genai>=1.0.0" || true
if [ -d "$BOT_DIR/dashboard-web" ]; then
  echo ">> Rebuilding dashboard..."
  ( cd "$BOT_DIR/dashboard-web" && npm install --silent && npm run build ) \
    || echo "   (dashboard build skipped/failed — API still updates)"
fi

if [ -d "$CC_DIR/.git" ]; then
  echo ">> Updating command-center ($CC_DIR)..."
  git -C "$CC_DIR" pull --ff-only
  [ -f "$CC_DIR/requirements.txt" ] \
    && "$CC_DIR/.venv/bin/pip" install -q -r "$CC_DIR/requirements.txt" || true
fi

echo ">> Restarting services..."
sudo systemctl restart tradingbot-api tradingbot-offhours cc-dashboard cc-runner
sudo systemctl is-enabled tradingbot-web >/dev/null 2>&1 \
  && sudo systemctl restart tradingbot-web || true

echo ">> Done. Current status:"
systemctl --no-pager --lines=0 status \
  tradingbot-api tradingbot-offhours cc-dashboard cc-runner || true
