# Deployment Walkthrough — Beginner Edition

Plain-English, copy-paste steps to put the trading bot + Command Center on one Google Cloud
VM with Vertex AI. Reference (terser) version: `docs/DEPLOYMENT.md`.

**How to read this:** anything in `<ANGLE_BRACKETS>` you replace with your own value.
Commands you can run inside this Claude session are prefixed with `! ` (the `!` makes Claude
run it and see the output so it can help if something breaks). You can also paste them into a
normal terminal without the `!`.

**The 4 values you'll reuse everywhere — fill these in once:**

| Name | Example | Yours |
|---|---|---|
| `PROJECT` (GCP project id) | `tony-stocks-123456` | __________ |
| `ZONE` | `us-central1-a` | `us-central1-a` |
| `VM` (vm name) | `trading-stack` | `trading-stack` |
| GitHub username | `SteveGuhlore` | `SteveGuhlore` |

Repo URLs (already known):
- Bot: `https://github.com/SteveGuhlore/Tony-Stocks.git`
- CC:  `https://github.com/SteveGuhlore/ai-operations-command-center.git`

---

## Part 0 — Install the Google Cloud CLI (one time)

1. Go to https://cloud.google.com/sdk/docs/install and download the **Windows** installer.
2. Run it, accept defaults. At the end, leave "Run gcloud init" checked.
3. Open a new PowerShell window and confirm:
   ```
   gcloud --version
   ```
   You should see version numbers. If "command not found", close and reopen the terminal.

## Part 1 — Log in & pick your project

```
! gcloud auth login
```
A browser opens — sign in with the Google account that has the $300 trial.

```
! gcloud projects list
```
Find your project's **PROJECT_ID** (the id, not the name). If you don't have one yet:
```
! gcloud projects create <PROJECT> --name="Tony Stocks"
```
Then make sure your $300 **billing account** is linked (Cloud Console → Billing → link the
trial account to this project). Confirm:
```
! gcloud billing projects describe <PROJECT>
```
You want `billingEnabled: true`.

## Part 2 — Make sure BOTH GitHub repos are current

- Bot: already pushed ✅ (this is the repo Claude just pushed).
- CC: in your `AI Operations Command Center` folder, run:
  ```
  git status
  ```
  If it says "ahead of 'origin/main'", run `git push`. The VM clones from GitHub, so GitHub must
  be up to date.

> **Are your repos private?** If yes, the VM can't clone them without a token. Easiest fix:
> create a GitHub **Personal Access Token** (github.com → Settings → Developer settings →
> Fine-grained tokens → read-only on these two repos). You'll paste it when cloning in Part 5.
> Keep it somewhere safe for that step.

## Part 3 — Create the VM

From the **Tony-Stocks repo folder** (`C:\Users\alexa\Downloads\TradingBotAgentProject`):
```
! cd C:\Users\alexa\Downloads\TradingBotAgentProject ; bash scripts/deploy/provision_vm.sh
```
…but `bash` env vars are easier set inline; if the above complains, use:
```
! PROJECT=<PROJECT> ZONE=us-central1-a MACHINE=e2-medium bash scripts/deploy/provision_vm.sh
```
What it does: turns on the Compute + Vertex APIs and creates an Ubuntu VM named `trading-stack`
with SSH-only access. Takes ~1 minute. You should see "VM created" and a NEXT list.

## Part 4 — Create the Vertex key (lets the VM talk to Gemini)

```
! gcloud iam service-accounts create vertex-runner --display-name="Vertex runner" --project=<PROJECT>
! gcloud projects add-iam-policy-binding <PROJECT> --member="serviceAccount:vertex-runner@<PROJECT>.iam.gserviceaccount.com" --role="roles/aiplatform.user"
! gcloud iam service-accounts keys create vertex-key.json --iam-account="vertex-runner@<PROJECT>.iam.gserviceaccount.com"
```
This creates a file `vertex-key.json` in your current folder. **Treat it like a password.**

## Part 5 — Copy files to the VM and set it up

Copy the setup script and the key up:
```
! gcloud compute scp scripts/deploy/setup_vm.sh vertex-key.json trading-stack:~ --zone=us-central1-a
```
SSH into the VM (this opens a shell ON the VM):
```
! gcloud compute ssh trading-stack --zone=us-central1-a
```
Now, **on the VM**, run setup (replace URLs if different). If the repos are **public**:
```
BOT_REPO=https://github.com/SteveGuhlore/Tony-Stocks.git CC_REPO=https://github.com/SteveGuhlore/ai-operations-command-center.git BRANCH=main RUN_USER=$USER bash ~/setup_vm.sh
```
If the repos are **private**, put your token in the URLs (replace `<TOKEN>`):
```
BOT_REPO=https://<TOKEN>@github.com/SteveGuhlore/Tony-Stocks.git CC_REPO=https://<TOKEN>@github.com/SteveGuhlore/ai-operations-command-center.git BRANCH=main RUN_USER=$USER bash ~/setup_vm.sh
```
This installs Python/Node, clones both repos to `/opt`, builds the environments, builds the
dashboard, and installs the background services. It does NOT start anything yet. ~3-5 minutes.

## Part 6 — Put secrets on the VM (still on the VM)

Move the key into place:
```
sudo install -m 600 -o $USER -g $USER ~/vertex-key.json /opt/secrets/vertex-key.json
rm ~/vertex-key.json
```
Create the two `.env` files from the templates:
```
cp /opt/trading-bot/scripts/deploy/env/trading-bot.env.example /opt/trading-bot/.env
cp /opt/trading-bot/scripts/deploy/env/command-center.env.example /opt/command-center/.env
chmod 600 /opt/trading-bot/.env /opt/command-center/.env
```
Edit the bot env (use `nano`, Ctrl-O to save, Ctrl-X to exit):
```
nano /opt/trading-bot/.env
```
Fill in:
- `GOOGLE_CLOUD_PROJECT=<PROJECT>`
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` = the **bot's** paper account
- `FMP_API_KEY`, `FINNHUB_API_KEY`
(the Vertex flag + key path are already set)

Edit the CC env:
```
nano /opt/command-center/.env
```
Fill in:
- `GOOGLE_CLOUD_PROJECT=<PROJECT>`
- `ALPACA_API_KEY` / `ALPACA_SECRET_KEY` = the **CC/Tony** paper account — **MUST be a
  different account than the bot's** (never the same keys)
- `TONY_OUTCOMES_FILE` is pre-filled to the bot's outcomes file path.

## Part 7 — Start everything (on the VM)

```
sudo systemctl enable --now tradingbot-api tradingbot-offhours cc-dashboard cc-runner
```
(Optional bot Next.js dashboard, only if its build succeeded in Part 5:)
```
sudo systemctl enable --now tradingbot-web
```
Check they're all running (look for `active (running)` in green):
```
systemctl status tradingbot-api tradingbot-offhours cc-dashboard cc-runner --no-pager
```

## Part 8 — Turn the engine ON (optional, when ready)

The off-hours engine ships **OFF** for safety. When you want it live:
```
nano /opt/trading-bot/config/default_config.yaml
# find the off_hours: block, set  enabled: true
sudo systemctl restart tradingbot-offhours
```

## Part 9 — Budget alert (protect the $300)

On your **local machine**:
```
! gcloud billing accounts list
```
Copy the ACCOUNT_ID, then:
```
! gcloud billing budgets create --billing-account=<ACCOUNT_ID> --display-name="trading-stack $50" --budget-amount=50USD --threshold-rule=percent=0.5 --threshold-rule=percent=0.9 --threshold-rule=percent=1.0
```
Now you get emailed at 50/90/100% of $50. **Remember: the trial expires 2026-08-27.**

## Part 10 — Open the dashboards (from your machine)

```
! gcloud compute ssh trading-stack --zone=us-central1-a -- -L 8001:localhost:8001 -L 8765:localhost:8765 -L 3000:localhost:3000
```
Leave that window open, then in your browser:
- Bot API: http://localhost:8001
- Bot dashboard: http://localhost:3000
- Command Center: http://localhost:8765

Close the SSH window to close the tunnel.

---

## Did it work? (verify)

On the VM, run one research pass manually:
```
cd /opt/trading-bot && PYTHONPATH=src .venv/bin/python -m trading_bot.cli off-hours-prep --config config/default_config.yaml --phase post_close
```
Then look at the newest file in `reports/morning_prep/` — the "narrative" section should read
like real written prose (that proves Vertex/Gemini is working). If it's terse/templated, Gemini
isn't wired — check `journalctl -u tradingbot-offhours -n 50 --no-pager`.

## Common problems

| You see | Do this |
|---|---|
| `gcloud: command not found` | Reopen terminal after installing the CLI (Part 0) |
| Clone asks for password on the VM | Repos are private → use the `<TOKEN>` URL form (Part 5) |
| Narrative is templated, not Gemini prose | Check `/opt/trading-bot/.env` Vertex vars + key perms; `journalctl -u tradingbot-offhours` |
| `403 Permission denied` (Vertex) | Re-run the `roles/aiplatform.user` binding (Part 4) |
| Dashboard won't load | Make sure the SSH `-L` tunnel window (Part 10) is still open |
| A service is `failed` | `journalctl -u <service-name> -n 50 --no-pager` to see why |

## Costs (so you're not surprised)

- VM (e2-medium): ~$24/month. Vertex Gemini Flash: pennies per run.
- All of it draws from the $300 trial until **2026-08-27**, then converts to paid only if you
  agree. The $50 budget alert (Part 9) is your safety net.
- To pause spending without deleting anything: `! gcloud compute instances stop trading-stack --zone=us-central1-a` (restart later with `start`). A stopped VM costs almost nothing (just disk).
