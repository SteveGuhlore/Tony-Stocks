# Handoff — GCP VM deploy + bot⇄CC cutover (2026-06-07)

**Read first:** `docs/DEPLOY_RULES.md` (test-before-deploy + tandem ritual). State note also in
the agent memory. This doc = where things stand and what's next.

## What exists now
- **One GCP VM `trading-stack`** (zone `us-central1-a`, project **`stocks-bot-agent`**, gcloud acct
  `alynx066@gmail.com`, billing = the **$300 trial, expires 2026-08-27**). Debian 12, 30 GB disk.
- Both repos on it: `/opt/trading-bot` (branch `main`), `/opt/command-center` (branch **`master`**).
- **systemd services:** `tradingbot-api` (uvicorn :8001), `tradingbot-offhours` (read-only research
  loop), `cc-runner` (runs `scripts/launch.py --interval 180` = CC dashboard :8765 + agent cron loop).
  *(Old `cc-dashboard` unit was removed — launch.py serves :8765.)*
- **LLM:** both on **Vertex AI** (gemini-2.5-flash) via `/opt/secrets/vertex-key.json`
  (SA `vertex-runner@stocks-bot-agent`, role `aiplatform.user`) → bills the $300. Verified with a
  real call + the e2e harness Phase-7.
- **Bridge tandem VERIFIED both ways.** Fixed: `command_center_dir` → `/opt/command-center`; symlink
  `/opt/TradingBotAgentProject -> /opt/trading-bot` (so the CC's `../TradingBotAgentProject` sibling
  refs resolve); CC `.env` overrides for TONY_OUTCOMES/VERDICTS/RECORD/TEACHING → `/opt/trading-bot/reports`.
- **State migrated local→VM:** `data/trading_bot.db` (33 MB), all `reports/*.json`,
  CC `workspace/ledger` + `workspace/tasks` (1,184 done tasks).
- **Local machine = dev only.** Live op stopped there (python procs killed; `TonyPreOpenReset` +
  `TradingBot-NightlyLearning` tasks Disabled). VM is the sole operator.
- VM-local edits pinned (skip-worktree): bot `config/default_config.yaml`, CC `scripts/vault_sync.sh`
  (neutralized — it hardcoded `/home/ubuntu/ai-ops`, the CC's original VPS layout).

## Open items (next session)
1. **Deploy CC's C–F UX fixes** (`/explain` discoverability, FAQ-hijack, dead-ends, silent-NL) —
   implemented in the CC repo; push `master` → `update_vm.sh` → tandem-verify + `/explain ANET` on
   Telegram. **Quarantine the 5 pre-existing CC reds** (xfail/skip) so the gate is honestly green.
2. **Bot trading loop on the VM** — `paper_trading.enabled: true` is set, but there's **no
   `tradingbot-watch` service** yet, so the bot isn't placing entries on the VM. Add one
   (`watch` loop) when the bot's side should trade live-paper.
3. **Tailscale** — for phone access to the dashboards (install on VM + `tailscale up`/`serve`).
4. **Next.js dashboard rebuild** (planned) — needs **Node 20** on the VM (Debian ships 18).
5. (Optional, deferred) live multi-agent chat (bot + CC agents + operator + dev).

## How to operate
- Redeploy: push (bot=main, CC=master) → on VM `bash /opt/trading-bot/scripts/deploy/update_vm.sh`.
- Verify: `PYTHONPATH=src .venv/bin/python scripts/full_e2e_sync_test.py --quick` (sandbox, no live
  impact) + `systemctl is-active tradingbot-api tradingbot-offhours cc-runner`.
- Audit clone completeness: `bash scripts/deploy/audit_untracked.sh /opt/trading-bot /opt/command-center`.
- Cloud-admin (gcloud) runs from the **Windows** terminal (the VM's default SA has limited scopes).
  VM ops run in the **browser SSH** (Console → Compute Engine → SSH) — works from any device.
- **Paste gotcha:** long lines wrap-break in Windows cmd/PowerShell AND the browser SSH; keep each
  command < ~80 chars or use short separate lines / tar for directories.

## Safety invariants
Different Alpaca paper accounts (bot vs CC). Off-hours engine read-only. Live trading gated. One
operator home (VM). Vertex key bypasses VM scopes — don't rely on the VM default SA for cloud calls.
