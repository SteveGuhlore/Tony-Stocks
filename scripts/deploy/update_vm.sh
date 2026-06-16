#!/usr/bin/env bash
# update_vm.sh — pull latest code for the bot + Command Center and (re)deploy.
#
# RUN THIS ON THE VM:  bash /opt/trading-bot/scripts/deploy/update_vm.sh
#
# Order matters: pull -> deps -> RESTART BACKEND FIRST -> dashboard build LAST (hard-timeout +
# heap-capped). The Next.js build is the slow/memory-heavy step; doing it last and bounded means a
# slow, hung, or OOM-ing build can never block the backend deploy or wedge this script (the bug that
# burned us on 2026-06-16). Read-only on trading surfaces; safe to run anytime.
#
# Tunables (env): DASHBOARD_BUILD_TIMEOUT (s, default 420; 0 = skip the build entirely)
#                 DASHBOARD_NODE_HEAP_MB (V8 heap cap, default 2048)
set -euo pipefail

BOT_DIR="${BOT_DIR:-/opt/trading-bot}"
CC_DIR="${CC_DIR:-/opt/command-center}"
BUILD_TIMEOUT="${DASHBOARD_BUILD_TIMEOUT:-420}"
NODE_HEAP_MB="${DASHBOARD_NODE_HEAP_MB:-2048}"

echo ">> Pulling trading-bot ($BOT_DIR)..."
git -C "$BOT_DIR" pull --ff-only
"$BOT_DIR/.venv/bin/pip" install -q -r "$BOT_DIR/requirements.txt" || true
"$BOT_DIR/.venv/bin/pip" install -q "google-genai>=1.0.0" || true

if [ -d "$CC_DIR/.git" ]; then
  echo ">> Pulling command-center ($CC_DIR)..."
  git -C "$CC_DIR" pull --ff-only
  [ -f "$CC_DIR/requirements.txt" ] \
    && "$CC_DIR/.venv/bin/pip" install -q -r "$CC_DIR/requirements.txt" || true
fi

# --- Restart the BACKEND first so a slow/hung dashboard build can never delay the live fixes. ---
echo ">> Restarting backend services..."
BACKEND="tradingbot-api tradingbot-offhours tradingbot-watch cc-runner"
for svc in $BACKEND; do
  if systemctl list-unit-files "$svc.service" >/dev/null 2>&1 \
     && systemctl cat "$svc.service" >/dev/null 2>&1; then
    sudo systemctl restart "$svc" && echo "   restarted $svc" \
      || echo "   WARN: failed to restart $svc"
  else
    echo "   skip $svc (no unit installed)"
  fi
done

# --- Dashboard build LAST: hard timeout + heap cap. tradingbot-web restarts ONLY on success, so a
#     failed/timed-out build leaves the previous good build serving (never a partial .next). ---
if [ -d "$BOT_DIR/dashboard-web" ] && [ "${BUILD_TIMEOUT}" -gt 0 ]; then
  node_major="$(node -v 2>/dev/null | sed 's/v\([0-9]*\).*/\1/')"
  if [ "${node_major:-0}" -ge 20 ]; then
    echo ">> Building dashboard (timeout ${BUILD_TIMEOUT}s, heap ${NODE_HEAP_MB}MB)..."
    if timeout "${BUILD_TIMEOUT}" bash -c \
        "cd '$BOT_DIR/dashboard-web' && npm install --silent && NODE_OPTIONS='--max-old-space-size=${NODE_HEAP_MB}' npm run build"; then
      echo "   dashboard build OK — restarting tradingbot-web"
      systemctl list-unit-files "tradingbot-web.service" >/dev/null 2>&1 \
        && { sudo systemctl restart tradingbot-web && echo "   restarted tradingbot-web" \
             || echo "   WARN: failed to restart tradingbot-web"; }
    else
      echo "   WARN: dashboard build failed/timed out — backend already updated; tradingbot-web left on its previous build."
      echo "        (Prefer building in CI; see docs/DEPLOY.md. Or raise DASHBOARD_BUILD_TIMEOUT / add swap.)"
    fi
  else
    echo ">> Skipping dashboard build (needs Node 20; have $(node -v 2>/dev/null || echo none))."
  fi
fi

echo ">> Done. Current status:"
systemctl --no-pager --lines=0 status \
  tradingbot-api tradingbot-offhours tradingbot-watch cc-runner 2>/dev/null || true
