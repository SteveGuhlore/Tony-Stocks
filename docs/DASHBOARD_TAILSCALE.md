# Bot Dashboard over Tailscale (phone access)

_Companion to the Kinetic Tape dashboard. Goal: view + act on the dashboard from your phone over
the tailnet, with **no "works on localhost, blank on phone" surprises**._

## The pattern (matches how the CC dashboard is already exposed)

Both VM services bind to **127.0.0.1** (see `scripts/deploy/systemd/tradingbot-web.service` :3000 and
`tradingbot-api.service` :8001) — they are NOT open on the network. Remote access is via **Tailscale
Serve**, which reverse-proxies tailnet HTTPS → those localhost ports. The CC dashboard already works this
way (you can see it), so the bot dashboard mirrors it.

### The one decision that prevents the classic breakages

Serve the **dashboard and its API on the SAME HTTPS origin**:

- `https://<vm>.<tailnet>.ts.net:8443/`     → bot dashboard (127.0.0.1:3000)
- `https://<vm>.<tailnet>.ts.net:8443/api`  → bot API       (127.0.0.1:8001)

Because they share an origin, the browser fetches the API at a **relative `/api`** path. This
simultaneously kills:

1. **The localhost trap** — a phone loading the page can't reach `http://localhost:8001`; relative
   `/api` resolves to the tailnet host instead. (This is the exact gotcha that has bitten this project
   before — see the port-mismatch note in prior handoffs.)
2. **CORS** — same origin ⇒ no cross-origin request ⇒ no CORS preflight to misconfigure.

The bot dashboard uses its own HTTPS port (`:8443`) so it does **not** collide with the CC dashboard on
`:443`. (Tailscale Serve allows 443 / 8443 / 10000.)

> We use **Serve (tailnet-only)**, NOT **Funnel**. The dashboard must never be exposed to the public
> internet — it has money-adjacent control actions. Tailnet is the security boundary (plus the action
> PIN + env-fence on POSTs, per the Codex review).

## Build-time requirement (critical — `NEXT_PUBLIC_API_URL` is baked at build)

`NEXT_PUBLIC_*` vars are inlined at `next build` time, so the VM build MUST be built with the relative base:

| Environment | `NEXT_PUBLIC_API_URL` |
|---|---|
| Local dev (`npm run dev`) | `http://localhost:8001/api` |
| VM build (served over Tailscale) | `/api`  ← relative, same-origin |

`scripts/deploy/update_vm.sh` should export `NEXT_PUBLIC_API_URL=/api` before `npm run build` on the VM.
If the dashboard's API client hardcodes `http://localhost:8001`, that's a remote-access bug — it must read
`process.env.NEXT_PUBLIC_API_URL` and default to `/api`. **(Integration checkpoint — verify before deploy.)**

## Commands (run on the VM, attended, after close)

```bash
# Expose the bot dashboard + API same-origin on :8443 (tailnet HTTPS).
# --bg persists across reboots (stored in tailscaled state).
sudo tailscale serve --bg --https=8443 --set-path=/api  http://127.0.0.1:8001
sudo tailscale serve --bg --https=8443 --set-path=/      http://127.0.0.1:3000

# Verify (read-only):
tailscale serve status        # should list :8443 → / and /api
tailscale status              # confirm MagicDNS name

# Tear down if needed:
# sudo tailscale serve --https=8443 off
```

Convenience wrapper: `scripts/deploy/tailscale_serve_dashboard.sh` (idempotent; prints the resulting URL).

## On your phone

1. Tailscale app installed + logged into the same tailnet (already done — you can see the CC dashboard).
2. MagicDNS on.
3. Open **`https://<vm-magicdns-name>:8443/`** (the script prints the exact URL). The dashboard loads and
   its API calls resolve to the same host automatically.

## Verify before trusting (no silent fixes during market hours)

- [ ] `tailscale serve status` shows `:8443 / → 127.0.0.1:3000` and `:8443 /api → 127.0.0.1:8001`.
- [ ] On the phone: dashboard loads AND the tape populates (proves the relative `/api` fetch works remotely).
- [ ] A read view that uses live prices shows a graceful state (not a blank/crash) when the market is closed.
- [ ] A money-action POST from the phone returns **403** unless `ENV_ROLE=prod` + matching broker fingerprint
      (the env-fence) AND the action PIN is supplied — confirm the fence is live on the VM.
