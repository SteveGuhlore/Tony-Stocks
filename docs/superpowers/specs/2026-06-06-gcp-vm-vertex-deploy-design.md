# GCP VM Co-Host (bot + Command Center) with Vertex AI — Design

**Date:** 2026-06-06
**Status:** Design — awaiting user review
**Trial constraint:** $300 GCP free-trial credit, **expires 2026-08-27** (the binding limit, not the dollars).

## Goal

Run the trading bot **and** the AI Operations Command Center (CC) unattended 24/7 on a single
Google Cloud VM, and route both projects' LLM calls through **Vertex AI Gemini** under one GCP
project (unified billing/IAM/monitoring). Preserve every existing safety invariant: read-only /
default-OFF engines, no shared Alpaca keys, bot↔CC pure separation, no public exposure.

## Non-negotiable boundary (execution model)

This repo's tooling **cannot run `gcloud`** — there is no Google Cloud auth in the build
environment. Therefore:

- **I produce** every artifact: provisioning/setup scripts, systemd units, `.env` templates,
  the bot's Vertex code change (with tests), budget-alert commands, and a runbook.
- **The operator runs** the cloud steps (`gcloud …`, the VM `setup_vm.sh`, enabling APIs),
  pasting output back (`! gcloud …`) so I can help debug.

"Build" = artifacts + bot code, **not** silent cloud provisioning.

## Architecture: one VM, shared local bridge folder

A single **Ubuntu 22.04 LTS `e2-medium`** (2 vCPU / 4 GB) VM hosts both projects:

```
/opt/trading-bot/                          ← this repo (git clone)
/opt/command-center/                       ← AI Operations Command Center (git clone)
/opt/command-center/bridge/tony-stocks/    ← shared bridge folder (UNCHANGED mechanism)
```

**Why one VM (not two):** the bot↔CC link is a **shared local filesystem** — the bot writes
`bridge/tony-stocks/...` and reads `reports/tony_stocks_verdicts.json`; the CC reads the bot's
`tony_stocks_outcomes.json` via `TONY_OUTCOMES_FILE`. On one VM this keeps working verbatim by
pointing `command_center_dir` at the CC's path on the VM — **no Cloud Storage / rsync / API
rewrite.** Two VMs would force replacing the file bridge with a network sync. `e2-medium` (not
`e2-small`) gives headroom for two FastAPI apps + the CC agent runners + Node dashboard builds.

Both projects are Python 3.x / FastAPI / uvicorn, so a single Ubuntu host with Python + Node
serves both.

## Components & services (systemd, auto-restart)

| Service | Command | Notes |
|---|---|---|
| `tradingbot-offhours` | `cli off-hours-watch --config config/default_config.yaml` | read-only research loop |
| `tradingbot-api` | `uvicorn trading_bot.api.main:app --host 127.0.0.1 --port 8001` | dashboard backend (localhost only) |
| `cc-*` | mirror the CC's existing start commands (runner/agents/dashboard) | derived from CC repo |

- The bot's nightly-learning and off-hours phases are already self-scheduling **loops**, so
  systemd-only is sufficient; **no Cloud Scheduler in v1** (can add later).
- Dashboards bind to `127.0.0.1` and are reached via **SSH tunnel** — never a public IP/port.
- Paper trading stays `enabled: false`; the off-hours engine stays `enabled: false` until the
  operator opts in. Live-trading guardrails unchanged.

## Vertex AI Gemini wiring

**Bot (code change — small, tested):** `src/trading_bot/analytics/llm_clients.py` currently builds
`genai.Client(api_key=...)`. Add a Vertex path: when `GOOGLE_GENAI_USE_VERTEXAI` is truthy,
build `genai.Client(vertexai=True, project=<GOOGLE_CLOUD_PROJECT>, location=<GOOGLE_CLOUD_LOCATION>)`
which uses Application Default Credentials / the service-account key. Keep the API-key path intact
as a fallback. `resolve_provider`/`model_for` unchanged (still returns `gemini`, model
`gemini-2.5-flash`). The narrator stays decision-free and fail-quiet — a Vertex auth failure
degrades to the deterministic template, never breaks a run. New unit tests cover: Vertex-mode
client construction is selected when the env flag is set; API-key mode still selected otherwise;
both degrade to `None`/template on missing creds.

**CC (config/doc, minimal code):** the CC already ships `.vertex-key.json` + `google-auth`. Document
pointing Tony at Vertex (its provider/model config + `GOOGLE_APPLICATION_CREDENTIALS`). Any CC code
change happens in the CC repo and is kept minimal; this spec owns only the bot side + the runbook.

**Shared GCP setup (operator runs):** one project; enable `aiplatform.googleapis.com`; a service
account with `roles/aiplatform.user`; key mounted on the VM; env: `GOOGLE_GENAI_USE_VERTEXAI=true`,
`GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION=us-central1`, `GOOGLE_APPLICATION_CREDENTIALS=/opt/secrets/vertex-key.json`.

## Secrets & safety

- `.env` per project on the VM, `chmod 600`, **never committed** (mirrors current local setup).
- Service-account key at `/opt/secrets/vertex-key.json`, `chmod 600`, owned by the run user.
- **Two different Alpaca paper accounts** stay enforced — bot and CC never share Alpaca keys
  (existing invariant; the runbook calls it out explicitly).
- No inbound ports except SSH (22). Dashboards via SSH tunnel only.

## Budget protection

A GCP **Budget = $50** with alerts at 50% / 90% / 100% (email). Reinforce in the runbook that the
trial **auto-converts to paid on 2026-08-27** unless cancelled, and that the VM is the main ongoing
cost (~$24/mo).

## Deliverables (artifacts I produce in this repo)

```
src/trading_bot/analytics/llm_clients.py     ← + Vertex-mode client path (TDD)
tests/test_llm_clients_vertex.py             ← new unit tests for the Vertex path
scripts/deploy/provision_vm.sh               ← gcloud: create VM, firewall (SSH only), budget hint
scripts/deploy/setup_vm.sh                   ← apt, python3+venv, node, clone both repos, venvs, .env stubs
scripts/deploy/systemd/tradingbot-offhours.service
scripts/deploy/systemd/tradingbot-api.service
scripts/deploy/systemd/cc-*.service          ← mirrored from the CC's start commands
scripts/deploy/env/trading-bot.env.example   ← incl. Vertex env vars
scripts/deploy/env/command-center.env.example
docs/DEPLOYMENT.md                            ← end-to-end runbook + gcloud command sequence + budget + SSH-tunnel + verification
```

## Build order

1. **Bot Vertex path** — TDD code change + tests, green suite (here, now).
2. **Deploy kit** — provision/setup scripts, systemd units, env templates.
3. **Runbook** — `docs/DEPLOYMENT.md` with the exact operator commands.
4. **Operator executes** gcloud/VM steps; I debug from pasted output.
5. **CC co-host** — its systemd units + Vertex config doc (read CC repo to mirror start commands).

## Testing / verification

- Bot: new `tests/test_llm_clients_vertex.py` green + full suite stays green.
- Scripts: shellcheck-clean / syntactically sound; **not executed** here (they touch the cloud).
- Live verification (operator, post-deploy): `systemctl status` for each service; one
  `off-hours-prep` run produces a morning-prep brief whose narrative is Gemini-authored (proves
  Vertex path); CC reads the bridge; budget alert visible in console.

## Risks & mitigations

- **Trial expiry (Aug 27):** budget alert + runbook note; operator decides on paid conversion.
- **Vertex auth/region drift:** fail-quiet narrator means the bot never breaks; runbook documents
  region + ADC troubleshooting.
- **CC opacity:** CC code lives in a separate repo; this spec owns the bot + runbook and treats CC
  changes as minimal/documented, mirrored from its actual start commands.
- **Cost of the build itself:** session already at ~$105; the heavy lifting (off-hours engine) is
  done — this phase is one small code change + scripts/docs, comparatively light.

## Out of scope (v1)

Cloud Scheduler, Secret Manager, managed DB, container/Cloud Run packaging, CI/CD, public ingress,
HA/multi-VM. All deferrable; noted in `KNOWN_BACKLOG.md` if desired.
