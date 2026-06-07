#!/usr/bin/env bash
# One-shot VM deploy for the Kinetic Tape dashboard. RUN ON THE VM (you, attended).
#
# Dashboard-ONLY and trading-safe:
#   - installs Node 20 (only `tradingbot-web` uses node; `cc-runner` is Python — unaffected)
#   - builds the Next app same-origin (NEXT_PUBLIC_API_URL empty -> relative /api)
#   - restarts ONLY tradingbot-web  (does NOT touch tradingbot-watch / tradingbot-api / cc-runner)
#   - maps Tailscale :8443  /  -> dashboard :3000   and   /api -> API :8001  (CC dashboard on :443 untouched)
#
# After this, open on your phone:  https://trading-stack.tail0ae2dc.ts.net:8443/
set -euo pipefail
BOT_DIR="${BOT_DIR:-/opt/trading-bot}"
BRANCH="${BRANCH:-feat/kinetic-dashboard}"

echo "[1/6] git ownership + checkout $BRANCH"
sudo git config --global --add safe.directory "$BOT_DIR"
sudo git -C "$BOT_DIR" fetch origin --quiet
sudo git -C "$BOT_DIR" checkout "$BRANCH"
sudo git -C "$BOT_DIR" pull --ff-only origin "$BRANCH"

echo "[2/6] Node 20 (cc-runner is Python; only tradingbot-web uses node)"
NMAJ=$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/' || echo 0)
if [ "${NMAJ:-0}" -lt 20 ]; then
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
fi
echo "node: $(node -v)"

echo "[3/6] build dashboard same-origin (relative /api)"
cd "$BOT_DIR/dashboard-web"
printf 'NEXT_PUBLIC_API_URL=\n' | sudo tee .env.production.local >/dev/null
sudo npm install --no-audit --no-fund
sudo npm run build

echo "[4/6] restart tradingbot-web ONLY (trading loop untouched)"
sudo systemctl restart tradingbot-web
sleep 5
printf "tradingbot-web: "; systemctl is-active tradingbot-web || true

echo "[5/6] tailscale serve :8443 same-origin (dashboard + /api)"
sudo tailscale serve --bg --https=8443 --set-path=/api http://127.0.0.1:8001
sudo tailscale serve --bg --https=8443 --set-path=/     http://127.0.0.1:3000

echo "[6/6] verify"
sleep 2
curl -s -o /dev/null -w "VM web  :3000        -> %{http_code}\n" http://127.0.0.1:3000/ || true
curl -s -o /dev/null -w "VM api  :8001/cockpit -> %{http_code}\n" http://127.0.0.1:8001/api/cockpit || true
sudo tailscale serve status || true
echo
echo ">> Open on your phone:  https://trading-stack.tail0ae2dc.ts.net:8443/"
echo ">> Rollback if needed:  sudo tailscale serve --https=8443 off ; sudo git -C $BOT_DIR checkout main"
