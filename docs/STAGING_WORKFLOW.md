# Staging Workflow — the only road to production

Production (`/opt/trading-bot`, services `tradingbot-api` :8001 / `tradingbot-watch` /
`tradingbot-web` :3000 + timers, branch `main`) runs 24/7 and is **never** edited, restarted
with uncommitted code, or deployed to directly. Every change travels:

**dev branch → staging soak → promote gate → fast-forward main → prod restart (after close)**

The Command Center (`/opt/command-center` → twin `/opt/command-center-staging`, service
`cc-runner-staging` :8766, flag `CC_LLM_OFFLINE`) follows this identical workflow with its own
copies of the scripts.

---

## The staging twin — what it is

A git **worktree** of this repo at `/opt/trading-bot-staging` (shares the object store; the dev
branch is checked out there while prod next door stays on `main`). Own venv, own `.env`, own
config, own state (DB/cache/logs/reports), API on **:8002**, services `tradingbot-api-staging` +
`tradingbot-watch-staging`. Functionally identical to prod except hermetically sealed:

| Seal | Mechanism |
|---|---|
| $0 LLM spend | `TONY_LLM_OFFLINE=1` + ANTHROPIC/GEMINI/GOOGLE keys blank (template narration) |
| $0 data-vendor spend | FINNHUB/FMP/TWELVE_DATA/POLYGON blank + enrichment budget zeroed (funnel is advisory-only); Alpaca IEX + paper are FREE and stay live |
| No shared trading book | its OWN throwaway Alpaca paper account ($100k, matching prod) — never prod's keys |
| No prod-grading pollution | exchange repointed at staging-CC: bridge → `/opt/command-center-staging/bridge/tony-stocks`, TONY_* files → its `workspace/trading-reports` |
| On-demand only | started by hand for a soak, stopped after promotion, never boot-enabled |

## Bootstrap (ONCE per machine)

```bash
sudo mkdir -p /opt/trading-bot-staging && sudo chown $USER:$USER /opt/trading-bot-staging
git -C /opt/trading-bot fetch origin <branch>
git -C /opt/trading-bot worktree add /opt/trading-bot-staging <branch>
bash /opt/trading-bot-staging/scripts/setup_staging.sh <branch>   # run STAGING'S copy
# then: throwaway paper keys into the .env, verify (below), install units, START (never enable)
```

## The dev loop (every piece of work)

1. **Develop** — a Claude session works on a fresh dev branch and pushes. Sessions never run
   VM commands against the prod checkout; staging commands below are run by the operator.
2. **Ship to staging:**
   ```bash
   cd /opt/trading-bot-staging
   git fetch origin && git checkout <branch> && git pull --ff-only
   sudo systemctl restart tradingbot-api-staging
   sudo systemctl start tradingbot-watch-staging     # or restart, if running
   ```
3. **Iterate** — watch `logs/staging-watch.log` + `curl -s 127.0.0.1:8002/api/health`. Bug? The
   session pushes a fix; `git pull --ff-only` + restart. Repeat freely.
4. **Soak** — one evening of live market data minimum.
5. **Promote** — `bash /opt/trading-bot-staging/scripts/promote_staging.sh`. Gates: full pytest +
   tandem sandbox test (`full_e2e_sync_test.py --quick --no-live-llm`) + `:8002` liveness, against
   the exact soaked commit. On green it PRINTS the ff-only merge + prod restart commands — run
   them by hand, after 4 PM ET.
6. **Stop staging** — `sudo systemctl stop tradingbot-watch-staging`. Twins stay off between soaks.

## Pre-start safety gate (every time, both twins)

```bash
grep -n  '^TONY_LLM_OFFLINE='                        /opt/trading-bot-staging/.env  # =1
grep -nE '^(ANTHROPIC_API_KEY|GEMINI_API_KEY|GOOGLE_API_KEY|FINNHUB_API_KEY|FMP_API_KEY|TWELVE_DATA_API_KEY|POLYGON_API_KEY)=' \
                                                     /opt/trading-bot-staging/.env  # all blank
grep -nE '^ALPACA_(API_KEY|SECRET_KEY)='             /opt/trading-bot-staging/.env  # staging keys ONLY
```
If the Alpaca lines show a prod key, or `TONY_LLM_OFFLINE` is missing: **do not start.** A twin
started on prod keys trades the same paper book prod is actively trading.

## Post-soak contract (what "passed" means)

- no LLM/enrichment calls happened (flag was 1, keys blank — this repo has no spend ledger;
  staging-CC's `workspace/ledger/daily-spend.json` must read `total_usd: 0.0` exactly)
- scans ran, bridge briefs landed in staging-CC, outcomes emitted, paper orders placed/reconciled
  on the throwaway account, EOD report produced (functional coverage, not an idle box)
- staging services stayed `active` through day rollovers (no crash loops)

## Rules of thumb

- One branch in staging at a time; a new branch waits for the current soak to finish.
- Multi-repo changes (verdict/outcome/record schema, bridge/tier report format): run BOTH twins,
  soak together, promote both. CC-staging's `--mirror-bridge` cron must be OFF while this twin
  runs (one bridge producer at a time — see docs/DEVELOPMENT.md).
- Full-fidelity soak (real LLM keys, only when the change IS the LLM/enrichment path): set
  `TONY_LLM_OFFLINE=0` + real keys for that ONE soak, then revert. Rare, deliberate, never default.
- Emergency direct prod fix (should be never): immediately re-point staging at main afterward so
  histories re-converge, or the next ff-only promote will refuse.
- Operator-only sudo: install/start/stop of staging units; sessions provide commands, never run them.
