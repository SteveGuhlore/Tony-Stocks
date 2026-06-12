#!/usr/bin/env bash
# setup_staging.sh — build the scanner-bot STAGING twin on the production VM.
#
#   sudo-less, idempotent. Run as the same user that owns /opt/trading-bot:
#       bash /opt/trading-bot/scripts/setup_staging.sh [branch]
#
# Mirror of the Command Center's scripts/setup_staging.sh: creates
# /opt/trading-bot-staging (git worktree of the production clone), its own
# .venv, an isolated .env + config, and writes tradingbot-*-staging.service
# units to /tmp for you to sudo-install. It NEVER writes into /opt/trading-bot's
# working tree, never touches the production .env, and never restarts any
# tradingbot-* service. (Exception, by design: `git worktree add` records
# lightweight metadata under /opt/trading-bot/.git/worktrees/ — repo
# bookkeeping only, invisible to the running services.)
#
# THE POINT: close the tandem loop inside the staging sandbox. The staging bot
# exchanges files with STAGING-CC (/opt/command-center-staging), never with
# production-CC or the live bot reports dir — so scanner changes (and CC
# changes to the verdict/outcome/record schema) can be soaked end-to-end with
# zero contact with either production service or the live $1M paper account.
#
# ISOLATION GUARANTEES (each verified against the code on this branch):
#   state   — database_path (data/trading_bot.db), cache_dir (data/cache),
#             log_dir (logs/), outputs_dir (outputs/), vault_dir (vault/),
#             reports/ and the STOP_WATCH_MODE flag all resolve RELATIVE TO
#             THE CHECKOUT (src/trading_bot/settings.py:29-32,
#             config/default_config.yaml vault block) — staging automatically
#             gets fresh copies. No override needed.
#   SHARED! — the two-way exchange with the Command Center. Repointed at
#             staging-CC below, var by var:
#       vault.command_center_dir  (config/default_config.yaml:247) — where the
#             bot WRITES bridge briefs ({cc}/bridge/tony-stocks/). Hardcoded
#             /opt/command-center in the default config → staging gets its own
#             generated config pointing at $CC_STAGING_DIR.
#       TONY_VERDICTS_FILE  (api/routes/command_center.py, execution/cc_verdicts.py)
#             — Tony's verdicts the bot READS. → staging-CC's trading-reports.
#       TONY_RECORD_FILE    (api/routes/command_center.py) — Tony's scorecard
#             the bot READS. → staging-CC's trading-reports.
#       TONY_OUTCOMES_FILE  (vault/outcomes_bridge.py, cli.py) — resolved
#             outcomes the bot WRITES for Tony to grade. → staging-CC's
#             trading-reports (where staging-CC's TONY_OUTCOMES_FILE reads).
#       TONY_INSIGHTS_FILE  (agent_bridge.py) — nightly-learner insights the
#             bot WRITES and Tony/the dashboard read. → staging-CC's
#             trading-reports.
#       TONY_TEACHING_FILE stays UNSET on purpose: tony_teaching_log.json is
#             bot-owned (written+read only by this checkout) → defaults to
#             staging's own reports/ — already isolated.
#   port    — staging API binds 127.0.0.1:8002 (production: 8001). The Next.js
#             dashboard and the eod/learn/offhours/reprotect timers are NOT
#             twinned — the staging twin is on-demand (watch + api only).
#   alpaca  — paper_trading.base_url is locked to the paper endpoint and
#             live_trading_enabled is hardcoded false in code, BUT staging
#             inherits the PRODUCTION paper keys unless you fill in the
#             placeholders. See the loud warning printed at the end.
#   sends   — the bot has no Telegram/email/social senders (verified by grep —
#             outputs are files + the bridge only), so there is nothing to
#             disable. LIVE_TRADING_ENABLED is forced false anyway.
#
# ⚠️ MIRROR-BRIDGE EITHER/OR: while this staging bot is running, CC-staging
# must run WITHOUT --mirror-bridge (or stop that cron: crontab -e, remove the
# cc-staging-bridge-mirror line). Otherwise production scan output AND staging
# scan output both land in staging-CC's bridge and the soak grades garbage.
set -euo pipefail

PROD_DIR="${PROD_DIR:-/opt/trading-bot}"
STAGING_DIR="${STAGING_DIR:-/opt/trading-bot-staging}"
CC_STAGING_DIR="${CC_STAGING_DIR:-/opt/command-center-staging}"
STAGING_API_PORT="${STAGING_API_PORT:-8002}"
UNIT_TMP_API="/tmp/tradingbot-api-staging.service"
UNIT_TMP_WATCH="/tmp/tradingbot-watch-staging.service"

BRANCH="${1:-}"
case "$BRANCH" in -h|--help) grep '^#' "$0" | head -25; exit 0 ;; esac

[ -d "$PROD_DIR/.git" ] || { echo "FATAL: $PROD_DIR is not a git checkout"; exit 1; }
case "$STAGING_DIR" in
    "$PROD_DIR"|"$PROD_DIR"/*) echo "FATAL: STAGING_DIR must not be inside $PROD_DIR"; exit 1 ;;
esac
if [ ! -d "$CC_STAGING_DIR" ]; then
    echo "WARNING: $CC_STAGING_DIR not found — build CC staging first"
    echo "         (bash /opt/command-center/scripts/setup_staging.sh). Continuing anyway;"
    echo "         the exchange dirs will be created when CC staging exists."
fi

if [ -z "$BRANCH" ]; then
    BRANCH="$(git -C "$PROD_DIR" rev-parse --abbrev-ref HEAD)"
    echo "No branch given — defaulting to production's current branch: $BRANCH"
fi

echo "=== [1/6] Staging checkout at $STAGING_DIR (branch: $BRANCH) ==="
git -C "$PROD_DIR" fetch origin --prune

if [ -e "$STAGING_DIR/.git" ]; then
    echo "Staging checkout already exists — updating to $BRANCH (idempotent re-run)."
    git -C "$STAGING_DIR" fetch origin --prune
    if git -C "$STAGING_DIR" checkout "$BRANCH" 2>/dev/null; then
        git -C "$STAGING_DIR" pull --ff-only origin "$BRANCH" || \
            echo "NOTE: ff-only pull skipped (local-only branch or diverged) — staging is on local $BRANCH as-is."
    else
        echo "NOTE: '$BRANCH' is checked out elsewhere — detaching staging at its tip."
        git -C "$STAGING_DIR" checkout --detach "$BRANCH"
    fi
else
    PROD_BRANCH="$(git -C "$PROD_DIR" rev-parse --abbrev-ref HEAD)"
    if [ "$BRANCH" = "$PROD_BRANCH" ]; then
        WT_REF="--detach $BRANCH"
    else
        WT_REF="$BRANCH"
    fi
    # shellcheck disable=SC2086
    if git -C "$PROD_DIR" worktree add "$STAGING_DIR" $WT_REF 2>/dev/null; then
        echo "Created git worktree (shared object store with production)."
    else
        echo "Worktree creation failed — falling back to a full clone."
        ORIGIN_URL="$(git -C "$PROD_DIR" remote get-url origin)"
        git clone "$ORIGIN_URL" "$STAGING_DIR"
        git -C "$STAGING_DIR" checkout "$BRANCH"
    fi
fi

echo "=== [2/6] Python venv + requirements ==="
if [ ! -x "$STAGING_DIR/.venv/bin/python" ]; then
    python3 -m venv "$STAGING_DIR/.venv"
fi
"$STAGING_DIR/.venv/bin/pip" install --quiet --upgrade pip
"$STAGING_DIR/.venv/bin/pip" install --quiet -r "$STAGING_DIR/requirements.txt"
echo "venv ready: $("$STAGING_DIR/.venv/bin/python" --version)"

echo "=== [3/6] Isolated state dirs + staging config ==="
mkdir -p "$STAGING_DIR/data" "$STAGING_DIR/logs" "$STAGING_DIR/reports" \
         "$STAGING_DIR/outputs" "$STAGING_DIR/vault"
mkdir -p "$CC_STAGING_DIR/bridge/tony-stocks" \
         "$CC_STAGING_DIR/workspace/trading-reports" 2>/dev/null || true

# Staging config = default config with vault.command_center_dir repointed at
# staging-CC. Lives in .venv/ so git status in the staging checkout stays clean.
# Regenerated on every run so it always tracks the checked-out default config.
STAGING_CONFIG="$STAGING_DIR/.venv/staging_config.yaml"
sed "s|^\([[:space:]]*command_center_dir:\).*|\1 $CC_STAGING_DIR  # staging-CC (set by setup_staging.sh)|" \
    "$STAGING_DIR/config/default_config.yaml" > "$STAGING_CONFIG"
grep -q "command_center_dir: $CC_STAGING_DIR" "$STAGING_CONFIG" || \
    { echo "FATAL: failed to repoint vault.command_center_dir in $STAGING_CONFIG"; exit 1; }
echo "Wrote $STAGING_CONFIG (bridge briefs -> $CC_STAGING_DIR/bridge/tony-stocks)."

echo "=== [4/6] .env (production copy + staging overrides appended) ==="
STAGING_ENV="$STAGING_DIR/.env"
ENV_MARKER="STAGING OVERRIDES — appended by scripts/setup_staging.sh"
if [ -f "$STAGING_ENV" ] && grep -qF "$ENV_MARKER" "$STAGING_ENV"; then
    # Idempotent re-run: NEVER regenerate — the user may have filled in staging
    # Alpaca keys. Delete the file yourself if you want a fresh copy.
    echo "Staging .env already has the staging block — leaving it untouched."
else
if [ -f "$PROD_DIR/.env" ]; then
    cp "$PROD_DIR/.env" "$STAGING_ENV"
else
    echo "WARNING: $PROD_DIR/.env not found — staging .env starts empty; fill in API keys."
    : > "$STAGING_ENV"
fi
chmod 600 "$STAGING_ENV"

# Comment out any production value first so the staging block below is the
# ONLY live definition (correct regardless of first/last-wins parsing).
OVERRIDE_KEYS="
TONY_VERDICTS_FILE TONY_RECORD_FILE TONY_OUTCOMES_FILE TONY_INSIGHTS_FILE
LIVE_TRADING_ENABLED
"
for key in $OVERRIDE_KEYS; do
    sed -i "s|^[[:space:]]*${key}=|# [prod, overridden by staging block] ${key}=|" "$STAGING_ENV"
done

CC_REPORTS="$CC_STAGING_DIR/workspace/trading-reports"
cat >> "$STAGING_ENV" <<EOF

# ============================================================================
# STAGING OVERRIDES — appended by scripts/setup_staging.sh $(date -u +%Y-%m-%dT%H:%MZ)
# Everything below closes the tandem loop into STAGING-CC and away from the
# 24/7 production services. The four TONY_* repoints MUST stay overridden —
# without them this checkout reads production-Tony's verdicts and writes its
# outcomes/insights where the LIVE grading pipeline would ingest them.
# ============================================================================

# --- Two-way reports exchange: staging-CC's dir, NOT the live bot reports ---
TONY_VERDICTS_FILE=$CC_REPORTS/tony_stocks_verdicts.json
TONY_RECORD_FILE=$CC_REPORTS/tony_stocks_record.json
TONY_OUTCOMES_FILE=$CC_REPORTS/tony_stocks_outcomes.json
TONY_INSIGHTS_FILE=$CC_REPORTS/agent_insights.json
# TONY_TEACHING_FILE intentionally unset — bot-owned file, defaults to this
# checkout's reports/ (already isolated by the worktree).

# --- Live trading: impossible in staging (also hardcoded off in code) -------
LIVE_TRADING_ENABLED=false

# --- Alpaca paper account -----------------------------------------------------
# !!! WARNING !!!  Right now staging INHERITS the production paper keys above,
# which means staging WILL PLACE PAPER ORDERS ON THE SAME ACCOUNT the
# production bot trades — duplicate/conflicting orders, polluted equity curve.
# Fine for a quick read-only smoke test; NOT fine for a soak.
#
# RECOMMENDED: create another free paper account (alpaca.markets -> account
# switcher -> "Create New Account" -> Paper -> Generate API Keys), paste the
# keys below, and uncomment. Note: the bot and CC must ALREADY be on different
# paper accounts — this staging account is a THIRD one.
#ALPACA_API_KEY=PK_REPLACE_WITH_STAGING_PAPER_KEY
#ALPACA_SECRET_KEY=REPLACE_WITH_STAGING_PAPER_SECRET
EOF
echo "Wrote $STAGING_ENV (production keys inherited, staging block appended)."
fi

echo "=== [5/6] Systemd units (written to /tmp — NOT installed) ==="
RUN_USER="$(id -un)"
cat > "$UNIT_TMP_API" <<EOF
# tradingbot-api-staging.service — STAGING twin of tradingbot-api.
# API on 127.0.0.1:$STAGING_API_PORT (production: 8001), working dir $STAGING_DIR.
# Safe to stop/start at will — shares nothing writable with production.
[Unit]
Description=Trading Bot STAGING API (FastAPI :$STAGING_API_PORT)
After=network-online.target
Wants=network-online.target
ConditionPathExists=$STAGING_DIR/.venv/bin/python

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$STAGING_DIR
EnvironmentFile=$STAGING_DIR/.env
Environment=PYTHONPATH=$STAGING_DIR/src
ExecStart=$STAGING_DIR/.venv/bin/uvicorn trading_bot.api.main:app --host 127.0.0.1 --port $STAGING_API_PORT
Restart=on-failure
RestartSec=10
StandardOutput=append:$STAGING_DIR/logs/staging-api.log
StandardError=append:$STAGING_DIR/logs/staging-api.err.log

[Install]
WantedBy=multi-user.target
EOF

cat > "$UNIT_TMP_WATCH" <<EOF
# tradingbot-watch-staging.service — STAGING twin of tradingbot-watch.
# Scans live market data, paper-trades the STAGING Alpaca keys, and exchanges
# files only with staging-CC ($CC_STAGING_DIR). On-demand: start it for a soak,
# stop it after (doubles yfinance API calls while running).
[Unit]
Description=Trading Bot STAGING watch loop (scan/track/paper-trade vs staging-CC)
After=network-online.target
Wants=network-online.target
ConditionPathExists=$STAGING_DIR/.venv/bin/python

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$STAGING_DIR
EnvironmentFile=$STAGING_DIR/.env
Environment=PYTHONPATH=$STAGING_DIR/src
ExecStart=$STAGING_DIR/.venv/bin/python -m trading_bot.cli watch --config $STAGING_CONFIG
Restart=on-failure
RestartSec=30
StandardOutput=append:$STAGING_DIR/logs/staging-watch.log
StandardError=append:$STAGING_DIR/logs/staging-watch.err.log

[Install]
WantedBy=multi-user.target
EOF
echo "Units written to $UNIT_TMP_API and $UNIT_TMP_WATCH."

echo "=== [6/6] Sanity: production untouched ==="
git -C "$PROD_DIR" diff --quiet && echo "Production working tree clean — untouched." || \
    echo "NOTE: production working tree has local changes (pre-existing — this script wrote nothing there)."

ALPACA_NOTE="!!! staging is using the PRODUCTION bot's paper keys — it WILL paper-trade the same account.
    Strongly recommended: create a separate free Alpaca paper account and fill the
    ALPACA_API_KEY / ALPACA_SECRET_KEY placeholders at the bottom of $STAGING_ENV."
grep -q '^ALPACA_API_KEY=PK_REPLACE' "$STAGING_ENV" 2>/dev/null && ALPACA_NOTE="staging Alpaca keys still placeholders — fill them in $STAGING_ENV"
grep -q '^#ALPACA_API_KEY=' "$STAGING_ENV" || ALPACA_NOTE="staging has its own ALPACA_API_KEY override — good."

cat <<EOF

============================================================
 SCANNER STAGING READY — $STAGING_DIR
 (branch: $(git -C "$STAGING_DIR" rev-parse --abbrev-ref HEAD) @ $(git -C "$STAGING_DIR" rev-parse --short HEAD))
============================================================
Install + start the services (the ONLY sudo steps):

    sudo cp $UNIT_TMP_API /etc/systemd/system/tradingbot-api-staging.service
    sudo cp $UNIT_TMP_WATCH /etc/systemd/system/tradingbot-watch-staging.service
    sudo systemctl daemon-reload
    sudo systemctl enable --now tradingbot-api-staging.service
    sudo systemctl start tradingbot-watch-staging.service     # start only for a soak

Then:
    API:      http://127.0.0.1:$STAGING_API_PORT   (production stays on :8001)
    Logs:     tail -f $STAGING_DIR/logs/staging-watch.log
              journalctl -u tradingbot-watch-staging -f
    Stop:     sudo systemctl stop tradingbot-watch-staging

⚠️  BEFORE the soak:
  1. ALPACA: $ALPACA_NOTE
  2. MIRROR-BRIDGE: make sure CC-staging's bridge-mirror cron is OFF while this
     twin runs (crontab -l | grep cc-staging-bridge-mirror), or production scan
     output will mix with this twin's output in staging-CC's bridge.
  3. The on-demand rule: stop tradingbot-watch-staging when the soak is done.

No production service was touched by this script.
============================================================
EOF
