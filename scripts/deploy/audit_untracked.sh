#!/usr/bin/env bash
# audit_untracked.sh — list gitignored-but-present files in each repo, i.e. exactly the
# files a fresh `git clone` will NOT bring (secrets + runtime state). Run before/after a
# VM deploy to confirm the must-have state is present. Regenerable noise is filtered out.
#
# Usage:
#   bash scripts/deploy/audit_untracked.sh [repo ...]
#   (defaults to the current repo; on the VM: pass /opt/trading-bot /opt/command-center)
set -euo pipefail

repos=("$@")
[ ${#repos[@]} -eq 0 ] && repos=(".")

for repo in "${repos[@]}"; do
  echo "===== gitignored / won't-clone in: $repo ====="
  git -C "$repo" ls-files --others --ignored --exclude-standard 2>/dev/null \
    | grep -Ev '(^|/)(\.venv|venv|node_modules|__pycache__|\.next|\.pytest_cache|dist|build|\.claude|\.superpowers)/' \
    | grep -Ev '(^|/)(data/cache|workspace/assets|workspace/logs)/' \
    | grep -Ev '\.(pyc|log|tsbuildinfo)$' \
    || echo "  (none / repo not found)"
  echo
done
echo "Must-have to copy if missing on the VM:"
echo "  bot: .env, data/trading_bot.db, reports/*.json"
echo "  cc : .env, workspace/ledger/*, workspace/tasks/*, vault/"
