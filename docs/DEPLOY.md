# Deploy runbook (VM)

Production runs on the VM: **bot** at `/opt/trading-bot` (deploys from `main`), **command-center**
at `/opt/command-center` (deploys from `master`). The canonical script `scripts/deploy/update_vm.sh`
deploys **both** (git pull → refresh deps → rebuild dashboard → restart services).

> **Policy vs mechanics.** This doc is the *how*. The *when/whether* gate lives in
> `docs/DEPLOY_RULES.md`: tests green (unit + `scripts/full_e2e_sync_test.py --quick`), staging
> soak, and promote only outside market hours. Don't deploy red.

---

## Two ways to deploy

### A. On-demand GitHub Action — preferred (no SSH)
A self-hosted runner **on the VM** runs the deploy and reports back through GitHub, so a deploy can
be triggered and verified entirely from GitHub (including by Claude via the GitHub MCP). No SSH
keys ever leave the box.

1. GitHub → repo → **Actions → “Deploy to VM” → Run workflow** → `mode: deploy`.
2. The runner runs `update_vm.sh` (serialized with `flock` so two triggers can't race) then a
   **verify** step: `tradingbot-api` + `cc-runner` must be `active` (job fails otherwise), and it
   prints the live `/api/command-center` agreement + the readiness sweep.
3. Open the run’s logs to confirm it’s green and eyeball the agreement numbers.

`mode: verify-only` runs just the checks (no code change).

### B. Manual on the VM (fallback)
```bash
bash /opt/trading-bot/scripts/deploy/update_vm.sh   # full-stack: bot + command-center
bash /opt/command-center/scripts/readiness_check.sh
```

---

## One-time setup: the self-hosted runner

Your GitHub is a **personal account** (no org), so register the runner **in this repo** (one
runner is enough — `update_vm.sh` is full-stack; add a second in the CC repo only if you also want
to trigger from there). On the VM, as the user that owns `/opt/*` (e.g. `alynx066`):

```bash
# 1) Grab the exact download + a registration token from:
#    GitHub → Settings → Actions → Runners → "New self-hosted runner" (Linux x64)
mkdir -p ~/actions-runner && cd ~/actions-runner
curl -o r.tar.gz -L https://github.com/actions/runner/releases/latest/download/actions-runner-linux-x64.tar.gz
tar xzf r.tar.gz
./config.sh --url https://github.com/SteveGuhlore/Tony-Stocks --token <RUNNER_TOKEN> \
            --labels self-hosted --name tony-vm --unattended

# 2) Run it as a service so it survives reboots:
sudo ./svc.sh install $(whoami)
sudo ./svc.sh start
sudo ./svc.sh status          # should show "active (running)"
```

Then grant the runner user **passwordless sudo** for exactly the restarts `update_vm.sh` performs —
`sudo visudo -f /etc/sudoers.d/cc-deploy`:
```
alynx066 ALL=(root) NOPASSWD: /bin/systemctl restart tradingbot-api, /bin/systemctl restart tradingbot-web, /bin/systemctl restart cc-runner, /bin/systemctl restart tradingbot-offhours, /bin/systemctl restart tradingbot-watch
```
The runner only ever polls GitHub outbound (no inbound ports) and only runs `.github/workflows/deploy.yml`.

---

## Verify (after any deploy)
```bash
systemctl is-active tradingbot-api cc-runner tradingbot-web
curl -s http://127.0.0.1:8001/api/command-center | python3 -m json.tool | grep -A6 '"agreement"'
bash /opt/command-center/scripts/readiness_check.sh
```

## Rollback
Prefer **revert** (preserves history, safe to redeploy):
```bash
cd /opt/trading-bot   # or /opt/command-center
git revert <bad-sha> && git push origin main   # (master for CC)
bash /opt/trading-bot/scripts/deploy/update_vm.sh
```
Last resort only, with care (destructive — the CC safety hook blocks it without explicit intent):
`git reset --hard <previous-good-sha>` then restart the services.
