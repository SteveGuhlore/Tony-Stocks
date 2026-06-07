# GCP VM Co-Host + Vertex AI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans (inline) or subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. Spec: `docs/superpowers/specs/2026-06-06-gcp-vm-vertex-deploy-design.md`.

**Goal:** Run the trading bot + AI Operations Command Center on one GCP e2-medium VM with both routed through Vertex AI Gemini, via a small tested code change + a complete deploy kit + runbook.

**Architecture:** One Ubuntu VM, both repos, shared local bridge folder (no network sync). Bot's existing `google-genai` adapter gains a Vertex-mode path. Everything else is scripts/systemd/docs the operator runs (no cloud auth in the build env).

**Tech Stack:** Python 3 (`google-genai`), pytest, bash, systemd, gcloud, Vertex AI.

**Run tests:** `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` or `$env:PYTHONPATH="src"; python -m pytest tests/test_llm_clients_vertex.py -v`.

**Verified facts:**
- Bot adapter: `src/trading_bot/analytics/llm_clients.py` — `make_llm_client` + `_GeminiClient(api_key)`; `resolve_provider` returns `gemini` when a Gemini key is set; `model_for` → `gemini-2.5-flash`.
- CC start commands: dashboard = `python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765`; runner = `python -m runner.main`. CC dashboard is FastAPI+static HTML (no Node).
- Bot services: `off-hours-watch` loop, FastAPI `trading_bot.api.main:app` on :8001, optional Next.js `dashboard-web` (`npm run build && npm start`).

---

## Task 1: Bot Vertex-mode LLM client (pure, TDD)

**Files:** Modify `src/trading_bot/analytics/llm_clients.py`; Test `tests/test_llm_clients_vertex.py`.

The `google-genai` SDK selects Vertex with `genai.Client(vertexai=True, project=..., location=...)`
using Application Default Credentials / `GOOGLE_APPLICATION_CREDENTIALS`. We gate it on
`GOOGLE_GENAI_USE_VERTEXAI` so the API-key path stays the default/fallback.

- [ ] **Step 1 — failing tests.** `tests/test_llm_clients_vertex.py`: inject a fake `google.genai`
  module via `sys.modules` (a `genai` with a `Client` recording its kwargs). Assert:
  - `_vertex_enabled` parses `"true"/"1"/"yes"/"on"` truthy, everything else false.
  - With `GOOGLE_GENAI_USE_VERTEXAI=true` + `GOOGLE_CLOUD_PROJECT=p` + `GOOGLE_CLOUD_LOCATION=us-central1`,
    `make_llm_client("gemini", env=...)` builds a client and the fake `Client` was called with
    `vertexai=True, project="p", location="us-central1"` (no `api_key`).
  - Vertex flag set but **no project** → `make_llm_client` returns `None`.
  - Vertex flag absent + `GEMINI_API_KEY=k` → fake `Client` called with `api_key="k"` (legacy path).
  - Vertex flag absent + no key → `None`.

```python
# tests/test_llm_clients_vertex.py
from __future__ import annotations
import sys, types
import pytest
from trading_bot.analytics import llm_clients


@pytest.fixture
def fake_genai(monkeypatch):
    calls = {}
    class _Client:
        def __init__(self, **kwargs):
            calls.update(kwargs)
        models = None
    genai_mod = types.SimpleNamespace(Client=_Client)
    google_pkg = types.ModuleType("google")
    google_pkg.genai = genai_mod  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google", google_pkg)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    return calls


def test_vertex_enabled_parsing():
    for v in ("true", "TRUE", "1", "yes", "on"):
        assert llm_clients._vertex_enabled({"GOOGLE_GENAI_USE_VERTEXAI": v}) is True
    for v in ("", "false", "0", "no", "off", "maybe"):
        assert llm_clients._vertex_enabled({"GOOGLE_GENAI_USE_VERTEXAI": v}) is False


def test_make_client_vertex_mode(fake_genai):
    env = {"GOOGLE_GENAI_USE_VERTEXAI": "true", "GOOGLE_CLOUD_PROJECT": "p",
           "GOOGLE_CLOUD_LOCATION": "us-central1"}
    client = llm_clients.make_llm_client("gemini", env=env)
    assert client is not None
    assert fake_genai == {"vertexai": True, "project": "p", "location": "us-central1"}


def test_vertex_mode_requires_project(fake_genai):
    env = {"GOOGLE_GENAI_USE_VERTEXAI": "true"}  # no project
    assert llm_clients.make_llm_client("gemini", env=env) is None


def test_api_key_mode_when_vertex_off(fake_genai):
    env = {"GEMINI_API_KEY": "k"}
    client = llm_clients.make_llm_client("gemini", env=env)
    assert client is not None
    assert fake_genai == {"api_key": "k"}


def test_gemini_none_when_no_creds(fake_genai):
    assert llm_clients.make_llm_client("gemini", env={}) is None
```

- [ ] **Step 2 — run, expect fail** (`_vertex_enabled` undefined / vertex path missing).
- [ ] **Step 3 — implement.** Add the flag helper + Vertex branch, and make `_GeminiClient`
  accept either creds path:

```python
_VERTEX_FLAG = "GOOGLE_GENAI_USE_VERTEXAI"
_TRUTHY = {"1", "true", "yes", "on"}


def _vertex_enabled(env: Mapping[str, str]) -> bool:
    return str(env.get(_VERTEX_FLAG, "")).strip().lower() in _TRUTHY
```

In `make_llm_client`, replace the `provider == "gemini"` block with:

```python
        if provider == "gemini":
            if _vertex_enabled(env):
                project = env.get("GOOGLE_CLOUD_PROJECT")
                location = env.get("GOOGLE_CLOUD_LOCATION") or "us-central1"
                if not project:
                    return None
                return _GeminiClient(vertex=True, project=project, location=location)
            api_key = next((env.get(k) for k in _GEMINI_KEYS if env.get(k)), None)
            if not api_key:
                return None
            return _GeminiClient(api_key=api_key)
```

Change `_GeminiClient.__init__` to:

```python
    def __init__(self, *, api_key: str | None = None, vertex: bool = False,
                 project: str | None = None, location: str | None = None) -> None:
        from google import genai  # noqa: PLC0415  (pip install google-genai)
        self._genai = genai
        if vertex:
            self._client = genai.Client(vertexai=True, project=project, location=location)
        else:
            self._client = genai.Client(api_key=api_key)
        self.messages = self._Messages(self._client, genai)
```

- [ ] **Step 4 — run, expect pass** (`pytest tests/test_llm_clients_vertex.py -v`).
- [ ] **Step 5 — full suite** stays green (`scripts\run_tests.ps1`).
- [ ] **Step 6 — commit** `feat(llm): Vertex AI mode for Gemini client (GOOGLE_GENAI_USE_VERTEXAI)`.

## Task 2: VM provisioning script (gcloud)

**Files:** Create `scripts/deploy/provision_vm.sh`.

- [ ] **Step 1** Write a parameterized, idempotent-ish gcloud script. Env-overridable:
  `PROJECT`, `ZONE=us-central1-a`, `MACHINE=e2-medium`, `VM=trading-stack`. It: sets the project;
  enables `compute.googleapis.com` + `aiplatform.googleapis.com`; creates an Ubuntu 22.04 VM with a
  30GB disk; ensures the default firewall allows **only** SSH (no http/https rules added); prints
  next steps. No public app ports. Include a commented budget-create example. `set -euo pipefail`,
  `#!/usr/bin/env bash`, header comment explaining it's operator-run.
- [ ] **Step 2 — commit** `chore(deploy): VM provisioning script`.

## Task 3: VM setup script

**Files:** Create `scripts/deploy/setup_vm.sh`.

- [ ] **Step 1** Script that runs ON the VM (header says so). It: `apt-get update`; installs
  `python3-venv python3-pip git nodejs npm` (Node for the bot's Next.js dashboard); creates
  `/opt/secrets` (`chmod 700`); clones both repos into `/opt/trading-bot` and `/opt/command-center`
  (env `BOT_REPO`, `CC_REPO` URLs — placeholders documented); creates a venv + `pip install -r`
  for each (`google-genai` added to the bot venv); copies the systemd units into
  `/etc/systemd/system/`; `daemon-reload`; prints the enable/start commands and the reminder to
  drop `.env` files + the Vertex key first. `set -euo pipefail`.
- [ ] **Step 2 — commit** `chore(deploy): VM setup script`.

## Task 4: systemd unit files

**Files:** Create `scripts/deploy/systemd/{tradingbot-offhours,tradingbot-api,tradingbot-web,cc-dashboard,cc-runner}.service`.

- [ ] **Step 1** Five units. Each: `Restart=always`, `RestartSec=10`, `EnvironmentFile=` the
  project `.env`, `WorkingDirectory=`, a non-root `User=`, `After=network-online.target`,
  `[Install] WantedBy=multi-user.target`. Exact ExecStart per the verified commands:
  - `tradingbot-offhours`: `/opt/trading-bot/.venv/bin/python -m trading_bot.cli off-hours-watch --config config/default_config.yaml` (Environment `PYTHONPATH=src`)
  - `tradingbot-api`: `/opt/trading-bot/.venv/bin/uvicorn trading_bot.api.main:app --host 127.0.0.1 --port 8001` (Environment `PYTHONPATH=src`)
  - `tradingbot-web`: `/usr/bin/npm --prefix /opt/trading-bot/dashboard-web start` (after a build; documented)
  - `cc-dashboard`: `/opt/command-center/.venv/bin/python -m uvicorn dashboard.server:app --host 127.0.0.1 --port 8765`
  - `cc-runner`: `/opt/command-center/.venv/bin/python -m runner.main`
- [ ] **Step 2 — commit** `chore(deploy): systemd units for bot + CC`.

## Task 5: env templates

**Files:** Create `scripts/deploy/env/trading-bot.env.example`, `scripts/deploy/env/command-center.env.example`.

- [ ] **Step 1** `trading-bot.env.example`: `PYTHONPATH=src`; Alpaca paper keys (bot's OWN account —
  comment: never share with CC); `FMP_API_KEY`, `FINNHUB_API_KEY`; the Vertex block
  (`GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT=`, `GOOGLE_CLOUD_LOCATION=us-central1`,
  `GOOGLE_APPLICATION_CREDENTIALS=/opt/secrets/vertex-key.json`); a comment that
  `learning.provider`/narrator pick Gemini automatically. `command-center.env.example`: the CC's
  own Alpaca (DIFFERENT account) + the same Vertex block. Both warn `chmod 600`, never commit.
- [ ] **Step 2 — commit** `chore(deploy): env templates with Vertex vars`.

## Task 6: Deployment runbook

**Files:** Create `docs/DEPLOYMENT.md`.

- [ ] **Step 1** End-to-end operator runbook: prerequisites (gcloud CLI, billing/trial linked);
  the exact ordered commands (`gcloud auth login`; run `provision_vm.sh`; `gcloud compute scp` the
  setup script/keys or `ssh` + clone; run `setup_vm.sh`; create the service account + key + IAM
  `roles/aiplatform.user`; place `.env` + `vertex-key.json`; `systemctl enable --now` each service);
  the **SSH tunnel** commands to reach dashboards (`gcloud compute ssh ... -- -L 8001:localhost:8001 -L 8765:localhost:8765 -L 3000:localhost:3000`);
  the **budget alert** ($50, 50/90/100%) cmd; a **verification** checklist (systemctl status, one
  `off-hours-prep` run shows a Gemini-authored narrative, CC reads the bridge); the **Aug 27 2026
  expiry** warning; and a **"what we need from the CC"** section (its repo URL, that it must point at
  Vertex via `GOOGLE_APPLICATION_CREDENTIALS` + provider config, and the different-Alpaca-account rule).
- [ ] **Step 2 — commit** `docs(deploy): end-to-end GCP deployment runbook`.

## Task 7: KNOWN_BACKLOG note

**Files:** Modify `KNOWN_BACKLOG.md`.

- [ ] **Step 1** One line: deferred deploy hardening (Secret Manager, Cloud Scheduler, container/Cloud Run, CI/CD, HA) — out of v1 scope.
- [ ] **Step 2 — commit** `docs: backlog note for deploy hardening`.

---

## Self-Review

- **Spec coverage:** topology→Tasks 4/6; Vertex bot→Task 1; Vertex CC→Task 6 doc; services→Task 4; secrets/safety→Tasks 5/6; budget→Task 6; deliverables list→Tasks 1–6; build order honored. Covered.
- **Placeholders:** repo URLs/project id are operator-supplied env vars (documented), not plan gaps.
- **Type consistency:** `_vertex_enabled`, `_VERTEX_FLAG`, `GOOGLE_GENAI_USE_VERTEXAI`, the
  `_GeminiClient(vertex=, project=, location=)` signature, and env var names are identical across
  Task 1 code/tests and Tasks 5/6.
