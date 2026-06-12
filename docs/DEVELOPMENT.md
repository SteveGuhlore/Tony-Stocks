# Development Workflow — staging soak before main

Production is a set of 24/7 systemd services (`tradingbot-watch`, `tradingbot-api` :8001,
`tradingbot-web` :3000, plus eod/learn/offhours/reprotect timers) at `/opt/trading-bot`,
paper-trading a live Alpaca account in tandem with the Command Center. Broken code on
`main` = a broken live scanner and corrupted Tony grading. So:

**Rule: no code lands on `main` without a soak in the scanner staging twin.**

This mirrors the Command Center's staging kit (`/opt/command-center-staging`, port 8766)
— same recipe, scanner side.

## The tandem and what staging isolates

The bot and the CC couple only through files:

- **Bot → CC:** bridge briefs into `{vault.command_center_dir}/bridge/tony-stocks/`,
  plus `tony_stocks_outcomes.json` and `agent_insights.json` in the reports exchange.
- **CC → Bot:** `tony_stocks_verdicts.json` and `tony_stocks_record.json`, read back
  for paper-gating and the dashboard.

The staging twin (`/opt/trading-bot-staging`) repoints ALL of these at **staging-CC**
(`/opt/command-center-staging`): the generated staging config sets
`vault.command_center_dir`, and the staging `.env` overrides `TONY_VERDICTS_FILE`,
`TONY_RECORD_FILE`, `TONY_OUTCOMES_FILE`, `TONY_INSIGHTS_FILE` to staging-CC's
`workspace/trading-reports/`. `tony_teaching_log.json` is bot-owned and stays in the
staging checkout's own `reports/`. Everything else (SQLite DB, caches, logs, vault,
outputs) is checkout-relative and isolated by the worktree automatically.

## One-time setup (on the VM)

```bash
bash /opt/trading-bot/scripts/setup_staging.sh <dev-branch>
# then the printed sudo commands to install tradingbot-{api,watch}-staging
```

Before the first real soak: create a **separate free Alpaca paper account** (a third one
— bot and CC already use different ones) and fill the placeholders at the bottom of
`/opt/trading-bot-staging/.env`. Until then staging paper-trades the production bot's
account — duplicate orders, polluted equity curve.

## Per-soak loop

```bash
cd /opt/trading-bot-staging
git fetch origin && git checkout <your-dev-branch>
sudo systemctl restart tradingbot-api-staging
sudo systemctl start tradingbot-watch-staging
# watch:  tail -f logs/staging-watch.log
#         curl -s http://127.0.0.1:8002/api/health

# after market close:
bash scripts/promote_staging.sh   # pytest + tandem sandbox test + :8002 liveness,
                                  # then PRINTS (never runs) the ff-only deploy commands
sudo systemctl stop tradingbot-watch-staging   # twin is on-demand — don't run it 24/7
```

If `requirements.txt` changed on the branch, re-run `setup_staging.sh <branch>`
(idempotent) before restarting.

## ⚠️ Mirror-bridge either/or

CC-staging's optional `--mirror-bridge` cron copies **production** bridge/report files
into staging-CC. While the scanner twin is live, the twin itself generates staging-CC's
bridge files — so the mirror cron must be OFF (`crontab -l | grep
cc-staging-bridge-mirror`), or production and staging scan output mix and the soak
grades garbage. One source at a time: mirror cron for CC-only soaks, scanner twin for
tandem soaks.

## When to spin up the twin

CC staging alone cannot catch a break in the **file formats** the two sides exchange —
its verdict write-back is severed from the live bot on purpose. So:

- any scanner change → soak in the twin;
- **any change (either repo) to the verdict/outcome/record schema or the bridge/tier
  report format → spin up the twin and test the full round trip against staging-CC
  before promoting.** This is the blind spot the twin exists to cover.

Otherwise leave `tradingbot-watch-staging` stopped — a permanent second scanner doubles
yfinance API calls and CPU for no benefit.

## Safety properties (both scripts)

- `setup_staging.sh` never writes into `/opt/trading-bot`, never edits the production
  `.env`, never restarts any production service. Idempotent: re-runs never clobber a
  filled-in staging `.env`.
- `promote_staging.sh` never pushes, merges, or restarts anything — production only
  changes when you run the printed commands yourself, after market close.
- Live trading stays impossible: `live_trading_enabled` is hardcoded false in code and
  forced false again in the staging `.env`; `paper_trading.base_url` only accepts the
  paper endpoint.
- The bot has no outbound senders (no Telegram/email/social) — nothing to disable.
