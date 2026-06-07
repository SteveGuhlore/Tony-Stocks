# Deployment — Trading Bot + Command Center on one GCP VM (Vertex AI)

Run the trading bot **and** the AI Operations Command Center (CC) unattended on a single
Google Cloud VM, with both routed through **Vertex AI Gemini**. The bot↔CC bridge stays a
**shared local folder** on the VM — no network sync.

> **You run the cloud steps.** This repo's tooling has no cloud auth. Every command below is
> yours to run (locally or on the VM). Artifacts referenced live in `scripts/deploy/`.

> **Trial clock:** the $300 free trial **expires 2026-08-27**, then converts to paid *on your
> consent*. The VM (~$24/mo on e2-medium) is the main ongoing cost. Set the budget alert (Step 7).

---

## Architecture at a glance

```
GCP VM (Ubuntu 22.04, e2-medium)
├── /opt/trading-bot/          this repo
│   ├── tradingbot-offhours    off-hours-watch loop (read-only research)
│   ├── tradingbot-api         FastAPI :8001 (localhost)
│   └── tradingbot-web         Next.js :3000 (localhost, optional)
├── /opt/command-center/       AI Operations Command Center
│   ├── cc-dashboard           FastAPI :8765 (localhost)
│   ├── cc-runner              agent task runner loop
│   └── bridge/tony-stocks/    <-- shared bridge folder (bot writes, CC reads)
└── /opt/secrets/vertex-key.json   service-account key (chmod 600)
```

All dashboards bind to `127.0.0.1` — reached only via **SSH tunnel**. The only open inbound
port is SSH (22).

---

## Step 0 — Prerequisites (local machine)

- Install the gcloud CLI, then:
  ```bash
  gcloud auth login
  gcloud projects list           # note your PROJECT_ID (or create one)
  ```
- Make sure your $300 free-trial billing account is linked to that project.

## Step 1 — Provision the VM

From the repo root on your machine:
```bash
PROJECT=<your-project-id> ZONE=us-central1-a MACHINE=e2-medium \
  bash scripts/deploy/provision_vm.sh
```
This enables Compute + Vertex (`aiplatform`) APIs and creates the VM with SSH-only ingress.

## Step 2 — Create the Vertex service account + key (local machine)

```bash
PROJECT=<your-project-id>
gcloud iam service-accounts create vertex-runner \
  --display-name="Vertex runner (trading stack)" --project="$PROJECT"

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:vertex-runner@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

gcloud iam service-accounts keys create vertex-key.json \
  --iam-account="vertex-runner@${PROJECT}.iam.gserviceaccount.com"
# This writes vertex-key.json locally. Treat it like a password.
```

## Step 3 — Copy the setup script + key to the VM

```bash
VM=trading-stack ZONE=us-central1-a
gcloud compute scp scripts/deploy/setup_vm.sh   "$VM":~          --zone="$ZONE"
gcloud compute scp vertex-key.json              "$VM":~         --zone="$ZONE"
```

## Step 4 — Run setup on the VM

```bash
gcloud compute ssh trading-stack --zone=us-central1-a
# --- now on the VM ---
BOT_REPO=<trading-bot git url> \
CC_REPO=<command-center git url> \
BRANCH=main \
RUN_USER=$USER \
  bash ~/setup_vm.sh
```
Installs Python/Node/git, clones both repos to `/opt`, builds venvs (adds `google-genai` to the
bot venv), builds the Next.js dashboard, and installs the systemd units (with your user
substituted). It starts nothing yet.

## Step 5 — Place secrets on the VM

```bash
# still on the VM
sudo install -m 600 -o "$USER" -g "$USER" ~/vertex-key.json /opt/secrets/vertex-key.json
rm ~/vertex-key.json

cp /opt/trading-bot/scripts/deploy/env/trading-bot.env.example      /opt/trading-bot/.env
cp /opt/trading-bot/scripts/deploy/env/command-center.env.example   /opt/command-center/.env
chmod 600 /opt/trading-bot/.env /opt/command-center/.env
# Edit each .env: fill GOOGLE_CLOUD_PROJECT, Alpaca keys (TWO DIFFERENT paper accounts!),
# FMP/FINNHUB keys. Vertex flag + key path are pre-filled.
nano /opt/trading-bot/.env
nano /opt/command-center/.env
```

> **SAFETY:** the bot and the CC must use **different Alpaca paper accounts** — never the same
> keys. Both engines ship default-OFF; turn the off-hours engine on only when ready
> (`off_hours.enabled: true` in `/opt/trading-bot/config/default_config.yaml`).

## Step 6 — Enable + start services

```bash
sudo systemctl enable --now tradingbot-api tradingbot-offhours cc-dashboard cc-runner
# optional Next.js dashboard (only if the build in Step 4 succeeded):
sudo systemctl enable --now tradingbot-web

systemctl status tradingbot-api tradingbot-offhours cc-dashboard cc-runner --no-pager
```

## Step 7 — Budget alert (protect the trial)

```bash
# Get your billing account id:
gcloud billing accounts list
BILLING=<XXXXXX-XXXXXX-XXXXXX>
gcloud billing budgets create \
  --billing-account="$BILLING" \
  --display-name="trading-stack \$50" \
  --budget-amount=50USD \
  --threshold-rule=percent=0.5 \
  --threshold-rule=percent=0.9 \
  --threshold-rule=percent=1.0
```
Alerts email the billing admins at 50/90/100%.

## Step 8 — Reach the dashboards (SSH tunnel)

From your machine:
```bash
gcloud compute ssh trading-stack --zone=us-central1-a -- \
  -L 8001:localhost:8001 -L 8765:localhost:8765 -L 3000:localhost:3000
```
Then open locally: bot API `http://localhost:8001`, bot dashboard `http://localhost:3000`,
CC dashboard `http://localhost:8765`. Closing the SSH session closes the tunnel.

### Remote access without a tunnel (Tailscale)

To reach the dashboard from a phone/laptop on the tailnet, expose **only** the Next.js
web server (port 3000) — not the API:
```bash
tailscale serve --bg 3000        # serves https://<host>.<tailnet>.ts.net → localhost:3000
```
The dashboard calls the API **same-origin** (relative `/api/*`); the Next.js server
reverse-proxies those requests to the local FastAPI on `127.0.0.1:8001` via the
`rewrites()` in `dashboard-web/next.config.ts`. So the API is reachable through the one
exposed origin and never needs its own port on the tailnet. **Do not** set
`NEXT_PUBLIC_API_URL` to a `localhost` URL — in a remote browser `localhost` is the
*viewer's* device, which is the classic "Cannot reach the API" failure. Leave it unset
(same-origin) unless you intentionally serve the API on a separate public origin, and
override the proxy target with `API_PROXY_TARGET` only if the API isn't on `:8001`.

---

## Verification checklist

- `systemctl status` shows all enabled services `active (running)`.
- Bot logs: `journalctl -u tradingbot-offhours -n 50 --no-pager`.
- **Vertex narration works** — run one prep manually on the VM:
  ```bash
  cd /opt/trading-bot && PYTHONPATH=src .venv/bin/python -m trading_bot.cli \
    off-hours-prep --config config/default_config.yaml --phase post_close
  ```
  Then check `reports/morning_prep/<date>.md` — the narrative section should read as
  Gemini-authored prose (not the deterministic template). A Vertex auth/region problem
  degrades to the template silently; check `journalctl` if so.
- CC reads the bridge: confirm `/opt/command-center/bridge/tony-stocks/` receives the bot's
  files and the CC's grading consumes `TONY_OUTCOMES_FILE`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Narrative is templated, not Gemini | Vertex not enabled / no project / wrong region / bad key | Check `.env` (`GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`), key path + perms, `journalctl -u tradingbot-offhours` |
| `403 Permission denied` on Vertex | service account missing role | re-run the `roles/aiplatform.user` binding (Step 2) |
| Dashboard blank / connection refused | tunnel not up, or API on wrong port | confirm SSH `-L` flags + `tradingbot-api` running on :8001 |
| "Cannot reach the API at ." (remote/phone) | frontend pointed at `localhost` or empty origin; API not proxied | leave `NEXT_PUBLIC_API_URL` unset (same-origin); the `rewrites()` in `next.config.ts` proxy `/api/*` → `127.0.0.1:8001`; rebuild (`npm run build`) + restart `tradingbot-web`; confirm `systemctl is-active tradingbot-api` |
| Service won't start | `User=`/path mismatch | `journalctl -u <svc>`; ensure units' `User=` matches the VM user |

---

## What we need from the Command Center (separate repo)

The CC lives in its own repository — these are the CC-side actions (most are config, not code):

1. **Repo URL + branch** for `CC_REPO` in Step 4.
2. **Point Tony at Vertex:** set `GOOGLE_APPLICATION_CREDENTIALS=/opt/secrets/vertex-key.json`,
   `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` (the
   `command-center.env.example` covers these). If the CC's LLM client doesn't yet support a
   Vertex path, it needs the same one-line switch the bot got
   (`genai.Client(vertexai=True, project=…, location=…)`) — point me at the CC repo and I'll add it.
3. **Different Alpaca paper account** than the bot (hard rule — never shared keys).
4. **`TONY_OUTCOMES_FILE`** set to the bot's outcomes file on the VM (already in the template).
5. Confirm the CC's start commands match the `cc-dashboard` / `cc-runner` units
   (`uvicorn dashboard.server:app :8765` and `python -m runner.main`); adjust the units if the CC
   has changed.

## Deferred (out of v1 scope)

Secret Manager, Cloud Scheduler, container/Cloud Run packaging, CI/CD, public ingress + TLS,
multi-VM HA. See `KNOWN_BACKLOG.md`.
