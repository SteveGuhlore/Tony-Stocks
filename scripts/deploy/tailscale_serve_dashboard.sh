#!/usr/bin/env bash
# Expose the Kinetic Tape bot dashboard + its API on the tailnet via Tailscale Serve,
# SAME-ORIGIN on :8443 (so the browser uses a relative /api base — no localhost trap, no CORS).
# Coexists with the CC dashboard on :443. Tailnet-only (NEVER Funnel). Idempotent.
# See docs/DASHBOARD_TAILSCALE.md. Run on the VM, attended, after market close.
set -euo pipefail

PORT="${DASHBOARD_HTTPS_PORT:-8443}"
WEB_PORT="${DASHBOARD_WEB_PORT:-3000}"
API_PORT="${DASHBOARD_API_PORT:-8001}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "ERROR: tailscale not found on PATH." >&2
  exit 1
fi

echo "Mapping tailnet https://<this-host>:${PORT}/  -> 127.0.0.1:${WEB_PORT} (dashboard)"
echo "       tailnet https://<this-host>:${PORT}/api -> 127.0.0.1:${API_PORT} (API)"

# API first so /api is matched before the catch-all /.
# tailscale serve STRIPS the --set-path prefix before proxying, so the /api target
# MUST include /api (else :8443/api/cockpit -> :8001/cockpit -> 404).
sudo tailscale serve --bg --https="${PORT}" --set-path=/api "http://127.0.0.1:${API_PORT}/api"
sudo tailscale serve --bg --https="${PORT}" --set-path=/     "http://127.0.0.1:${WEB_PORT}"

echo
echo "Current serve config:"
tailscale serve status || true

# Print the MagicDNS URL to open on your phone.
HOST="$(tailscale status --json 2>/dev/null | grep -oE '"DNSName"\s*:\s*"[^"]+"' | head -1 | sed -E 's/.*"DNSName"\s*:\s*"([^"]+)\.?"/\1/')"
if [ -n "${HOST:-}" ]; then
  echo
  echo ">> Open on your phone:  https://${HOST}:${PORT}/"
else
  echo
  echo ">> Open on your phone:  https://<your-vm-magicdns-name>:${PORT}/   (see 'tailscale status')"
fi

echo
echo "Reminder: build the frontend on the VM with NEXT_PUBLIC_API_URL=/api (relative) so remote fetches"
echo "resolve same-origin. To tear down: sudo tailscale serve --https=${PORT} off"
