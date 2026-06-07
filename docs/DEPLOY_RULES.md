# Deployment Rules — Bot ⇄ Command Center (tandem)

**Hard rule (mirrors the CC's rule): never deploy untested code to the VM, and never treat
`main`/`master` as deployable unless the test gate is green.** Both repos. No exceptions for
"small" changes — silent bridge/path breaks are exactly how tandem dies quietly.

## The test-before-deploy gate
Before pushing a change intended for the VM:
1. **Unit suite green** in the repo you changed:
   - Bot: `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` (or `pytest`).
   - CC: its own suite. If a pre-existing red is unrelated to your change, **quarantine it**
     (`@pytest.mark.xfail(reason=...)` / `skip`) in the same PR so green stays meaningful — do
     **not** normalize a red board.
2. **Tandem sandbox test** (cross-repo contract, no live impact, runs anytime):
   `PYTHONPATH=src python scripts/full_e2e_sync_test.py --quick` → `RESULT N/N passed`.
3. Only then push.

## Tandem-safe deploy ritual
1. Dev in the **correct session**: bot changes in the bot repo/session; CC changes in the CC
   repo/session. (Two sessions editing the same area = drift. One owner per repo.)
2. Push: bot → `main`, CC → `master`.
3. On the VM: `bash /opt/trading-bot/scripts/deploy/update_vm.sh` (pulls **both** repos, rebuilds,
   restarts). Keep the VM working trees clean — untracked files break `git pull --ff-only`.
4. **Verify before trusting**: on the VM run the tandem sandbox test + `systemctl is-active …` +
   a real `/explain` / API hit. Only then resume live.

## Completeness check (gitignored files don't clone)
A `git clone` never brings `.gitignore`d files — that's where secrets + state live. Audit anytime:
```
bash scripts/deploy/audit_untracked.sh /opt/trading-bot /opt/command-center
```
Must-have (copy manually, per repo): `.env`, `data/trading_bot.db`, `reports/*.json`; CC:
`.env`, `workspace/ledger/*`, `workspace/tasks/*`, `vault/`. Skip: caches, `node_modules`,
`workspace/assets`, logs (regenerable).

## VM-local files pinned (so pulls don't clobber them)
`git update-index --skip-worktree` is set on: bot `config/default_config.yaml`,
CC `scripts/vault_sync.sh`. To intentionally update one: `--no-skip-worktree` → pull → re-pin.

## Seeing the dashboards
Localhost-bound on the VM (`127.0.0.1`): bot API `:8001`, CC dashboard `:8765`, bot web `:3000`.
Reach them via **Tailscale** (phone-friendly, private) or an SSH tunnel
(`gcloud compute ssh trading-stack -- -L 8765:localhost:8765 -L 8001:localhost:8001`).
Never open these ports publicly.

## Safety invariants (unchanged)
Bot and CC use **different Alpaca paper accounts**. Bot off-hours engine is read-only. Live
trading stays gated. One operator home at a time (VM = production; local = dev only).
