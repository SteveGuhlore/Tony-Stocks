#!/usr/bin/env bash
# promote_staging.sh — the promotion gate between a scanner staging soak and main.
#
#   bash /opt/trading-bot/scripts/promote_staging.sh
#
# Mirror of the Command Center's promote gate. Runs, IN THE STAGING CHECKOUT:
#   1. the full pytest suite (staging venv)
#   2. the tandem sandbox test: scripts/full_e2e_sync_test.py --quick --no-live-llm
#   3. a liveness probe of the staging API (:8002)
#
# Only if ALL pass does it print the exact commands to fast-forward main and
# deploy production. It NEVER pushes, merges, or restarts anything itself.
set -uo pipefail

STAGING_DIR="${STAGING_DIR:-/opt/trading-bot-staging}"
PROD_DIR="${PROD_DIR:-/opt/trading-bot}"
STAGING_API_PORT="${STAGING_API_PORT:-8002}"
PY="$STAGING_DIR/.venv/bin/python"

fail() { echo; echo "PROMOTION BLOCKED: $1"; exit 1; }

[ -d "$STAGING_DIR" ]  || fail "no staging checkout at $STAGING_DIR (run scripts/setup_staging.sh first)"
[ -x "$PY" ]           || fail "no staging venv at $STAGING_DIR/.venv"

BRANCH="$(git -C "$STAGING_DIR" rev-parse --abbrev-ref HEAD)"
COMMIT="$(git -C "$STAGING_DIR" rev-parse --short HEAD)"
echo "Candidate: branch '$BRANCH' @ $COMMIT (soaked in $STAGING_DIR)"
[ "$BRANCH" != "main" ] && [ "$BRANCH" != "HEAD" ] || \
    fail "staging is on '$BRANCH' — check out the dev branch you soaked before promoting"

if ! git -C "$STAGING_DIR" diff --quiet || ! git -C "$STAGING_DIR" diff --cached --quiet; then
    fail "staging working tree is dirty — commit or discard local edits so what you promote is what you soaked"
fi

echo
echo "=== GATE 1/3: full pytest suite (staging venv) ==="
( cd "$STAGING_DIR" && PYTHONPATH=src "$PY" -m pytest -q ) || fail "pytest failed"
echo "pytest: PASS"

echo
echo "=== GATE 2/3: tandem sandbox test (bot<->CC contract, sandboxed) ==="
( cd "$STAGING_DIR" && PYTHONPATH=src "$PY" scripts/full_e2e_sync_test.py --quick --no-live-llm ) \
    || fail "full_e2e_sync_test.py failed"
echo "tandem sandbox test: PASS"

echo
echo "=== GATE 3/3: staging API liveness (:$STAGING_API_PORT) ==="
HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$STAGING_API_PORT/api/health" 2>/dev/null || echo 000)"
[ "$HTTP_CODE" = "200" ] || \
    HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$STAGING_API_PORT/" 2>/dev/null || echo 000)"
if [ "$HTTP_CODE" != "200" ]; then
    fail "staging API not answering on :$STAGING_API_PORT (got $HTTP_CODE) — did the soak actually run? (systemctl status tradingbot-api-staging)"
fi
echo "API :$STAGING_API_PORT -> 200 OK"

cat <<EOF

============================================================
 ALL GATES PASSED — '$BRANCH' @ $COMMIT is clear to promote.
============================================================
Nothing has been pushed or restarted. After market close, run BY HAND:

  # 1. Make the soaked branch reachable from origin (skip if already pushed)
  git -C $STAGING_DIR push origin $BRANCH

  # 2. Fast-forward main in the PRODUCTION checkout (ff-only: refuses
  #    anything that isn't exactly what staging soaked)
  git -C $PROD_DIR fetch origin
  git -C $PROD_DIR checkout main
  git -C $PROD_DIR merge --ff-only $COMMIT
  git -C $PROD_DIR push origin main

  # 3. Restart production on the new code
  sudo systemctl restart tradingbot-api tradingbot-watch tradingbot-offhours
  curl -s -o /dev/null -w 'prod API -> %{http_code}\n' http://127.0.0.1:8001/

  # 4. Stop the staging twin until next time (on-demand rule)
  sudo systemctl stop tradingbot-watch-staging
============================================================
EOF
