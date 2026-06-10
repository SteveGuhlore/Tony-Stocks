#!/usr/bin/env bash
# setup_vm.sh — provision software on the VM that co-hosts the trading bot + Command Center.
#
# RUN THIS ON THE VM (after `gcloud compute ssh`). It installs runtimes, clones both
# repos, builds venvs, and installs the systemd units. It does NOT start anything and
# does NOT place secrets — you do that next (see docs/DEPLOYMENT.md) so keys are never
# baked into an image or logged.
#
# Override repo URLs / branch via env:
#   BOT_REPO=<git-url> CC_REPO=<git-url> BRANCH=main RUN_USER=$USER bash setup_vm.sh
set -euo pipefail

BOT_REPO="${BOT_REPO:?set BOT_REPO=<trading-bot git url>}"
CC_REPO="${CC_REPO:?set CC_REPO=<command-center git url>}"
BRANCH="${BRANCH:-main}"
BOT_BRANCH="${BOT_BRANCH:-$BRANCH}"
CC_BRANCH="${CC_BRANCH:-master}"   # CC repo's default branch is master, not main
RUN_USER="${RUN_USER:-$USER}"
BOT_DIR="/opt/trading-bot"
CC_DIR="/opt/command-center"
SECRETS_DIR="/opt/secrets"

echo ">> Installing system packages (python, git, node)..."
sudo apt-get update -y
sudo apt-get install -y python3-venv python3-pip git nodejs npm

echo ">> Creating /opt dirs (owned by $RUN_USER)..."
sudo mkdir -p "$BOT_DIR" "$CC_DIR"
sudo install -d -m 700 -o "$RUN_USER" -g "$RUN_USER" "$SECRETS_DIR"
sudo chown -R "$RUN_USER:$RUN_USER" "$BOT_DIR" "$CC_DIR"

clone_or_pull() {  # $1=url $2=dir $3=branch
  if [ -d "$2/.git" ]; then
    git -C "$2" fetch --all && git -C "$2" checkout "$3" && git -C "$2" pull
  else
    git clone --branch "$3" "$1" "$2"
  fi
}

echo ">> Cloning repos (bot:$BOT_BRANCH  cc:$CC_BRANCH)..."
clone_or_pull "$BOT_REPO" "$BOT_DIR" "$BOT_BRANCH"
clone_or_pull "$CC_REPO" "$CC_DIR" "$CC_BRANCH"

echo ">> Building trading-bot venv..."
python3 -m venv "$BOT_DIR/.venv"
"$BOT_DIR/.venv/bin/pip" install --upgrade pip
if [ -f "$BOT_DIR/requirements.txt" ]; then "$BOT_DIR/.venv/bin/pip" install -r "$BOT_DIR/requirements.txt"; fi
# Vertex AI SDK for the narrator's Gemini path:
"$BOT_DIR/.venv/bin/pip" install "google-genai>=1.0.0"

echo ">> Building command-center venv..."
python3 -m venv "$CC_DIR/.venv"
"$CC_DIR/.venv/bin/pip" install --upgrade pip
if [ -f "$CC_DIR/requirements.txt" ]; then "$CC_DIR/.venv/bin/pip" install -r "$CC_DIR/requirements.txt"; fi

echo ">> Building the bot's Next.js dashboard (optional; for tradingbot-web)..."
if [ -d "$BOT_DIR/dashboard-web" ]; then
  ( cd "$BOT_DIR/dashboard-web" && npm install && npm run build ) || \
    echo "   (dashboard build skipped/failed — API still works; you can build later)"
fi

echo ">> Installing systemd units (substituting run user '$RUN_USER')..."
for unit in "$BOT_DIR"/scripts/deploy/systemd/*.service "$BOT_DIR"/scripts/deploy/systemd/*.timer; do
  [ -e "$unit" ] || continue
  name="$(basename "$unit")"
  sed "s/__RUN_USER__/$RUN_USER/g" "$unit" | sudo tee "/etc/systemd/system/$name" >/dev/null
done
sudo systemctl daemon-reload

cat <<EOF

>> Setup complete. BEFORE starting services:
  1. Place secrets (chmod 600), do NOT commit:
       $BOT_DIR/.env            (from scripts/deploy/env/trading-bot.env.example)
       $CC_DIR/.env             (from scripts/deploy/env/command-center.env.example)
       $SECRETS_DIR/vertex-key.json   (service-account key, roles/aiplatform.user)
  2. Confirm the systemd units' User=/paths match this host (RUN_USER=$RUN_USER).
  3. Enable services:
       sudo systemctl enable --now tradingbot-api tradingbot-offhours cc-dashboard cc-runner
       # tradingbot-web only if you built the Next.js dashboard above
       # Timers (nightly learn + post-close EOD resolution/divergence/bridge):
       sudo systemctl enable --now tradingbot-learn.timer tradingbot-eod.timer
  4. Verify + tunnel to dashboards: see docs/DEPLOYMENT.md

  SAFETY: bot and CC must use DIFFERENT Alpaca paper accounts (never shared keys).
EOF
