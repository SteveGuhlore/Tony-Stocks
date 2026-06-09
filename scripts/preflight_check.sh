#!/usr/bin/env bash
# preflight_check.sh — one-command health check for the trading-bot + Command Center tandem.
#
# READ-ONLY. Run on the VM any time (especially pre-open) to prove the whole system is live:
#   bash scripts/preflight_check.sh
#
# Checks: systemd services, bot API/dashboard, scanner cycling, nightly-learning feedback
# health, bot->CC handoff freshness, and naked-position protection on BOTH paper accounts.
# Exit code 0 == all critical checks pass; 1 == at least one FAIL (WARN does not fail).
set -uo pipefail

BOT_DIR="${BOT_DIR:-/opt/trading-bot}"
CC_DIR="${CC_DIR:-/opt/command-center}"
fail=0
pass(){ printf "  \033[32mPASS\033[0m %s\n" "$1"; }
warn(){ printf "  \033[33mWARN\033[0m %s\n" "$1"; }
bad(){  printf "  \033[31mFAIL\033[0m %s\n" "$1"; fail=1; }

echo "== 1. services =="
for s in tradingbot-watch tradingbot-api tradingbot-offhours tradingbot-web cc-runner; do
  st=$(systemctl is-active "$s" 2>/dev/null)
  if [ "$st" = active ]; then pass "$s active"; else bad "$s = ${st:-unknown}"; fi
done

echo "== 2. bot API + dashboard =="
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 http://127.0.0.1:8001/api/health 2>/dev/null)
if [ "$code" = 200 ]; then pass "bot API /api/health 200"; else bad "bot API /api/health = ${code:-no-response}"; fi

echo "== 3. scanner cycling (last 15 min) =="
if journalctl -u tradingbot-watch --since "15 min ago" --no-pager 2>/dev/null \
   | grep -qE "Watch cycle summary|Pre-screener|Scheduled Watch Mode|Rotation bucket"; then
  pass "watch loop logging activity"
else
  warn "no watch activity in 15 min (may just be between cycles)"
fi

echo "== 4. nightly-learning feedback health =="
hf="$BOT_DIR/reports/learning_health.json"
if [ -f "$hf" ]; then
  read -r ok asof < <(python3 -c "import json;d=json.load(open('$hf'));print(d.get('ok'),d.get('as_of'))" 2>/dev/null)
  if [ "$ok" = "True" ]; then pass "learning feedback ok (as_of=$asof)"; else bad "learning feedback DEGRADED (as_of=$asof) — re-run 'cli learn'"; fi
else
  warn "no learning_health.json yet (written by the nightly run)"
fi

echo "== 5. handoff freshness (bot -> CC bridge) =="
if ls "$CC_DIR"/bridge/tony-stocks/*.md >/dev/null 2>&1; then
  latest=$(ls -t "$CC_DIR"/bridge/tony-stocks/*.md | head -1)
  age_h=$(( ( $(date +%s) - $(stat -c %Y "$latest") ) / 3600 ))
  if [ "$age_h" -lt 24 ]; then pass "CC bridge fresh: $(basename "$latest") (${age_h}h old)";
  else warn "CC bridge stale: $(basename "$latest") (${age_h}h old)"; fi
else
  bad "no CC bridge files found under $CC_DIR/bridge/tony-stocks/"
fi

echo "== 6. naked positions — both paper accounts =="
python3 - <<'PY'
import json, glob, urllib.request, sys
def env(f):
    d={}
    for ln in open(f, errors="ignore"):
        ln=ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k,_,v=ln.partition("="); d[k.strip()]=v.strip().strip('"').strip("'")
    return d
def api(k,s,p):
    r=urllib.request.Request("https://paper-api.alpaca.markets"+p,
        headers={"APCA-API-KEY-ID":k,"APCA-API-SECRET-KEY":s})
    with urllib.request.urlopen(r, timeout=30) as x: return json.load(x)
rc=0; seen=set()
G="\033[32m"; Y="\033[33m"; R="\033[31m"; N="\033[0m"
for f in sorted(glob.glob("/opt/*/.env")):
    d=env(f); k=d.get("ALPACA_API_KEY") or d.get("APCA_API_KEY_ID"); s=d.get("ALPACA_SECRET_KEY") or d.get("APCA_API_SECRET_KEY")
    if not (k and s): continue
    try:
        acct=api(k,s,"/v2/account")
    except Exception as e:
        print(f"  {R}FAIL{N} {f}: account API error {e}"); rc=1; continue
    if acct["account_number"] in seen: continue
    seen.add(acct["account_number"])
    has_stop=set()
    for o in api(k,s,"/v2/orders?status=open&limit=500&nested=true"):
        for x in [o]+(o.get("legs") or []):
            if x.get("side")=="sell" and (x.get("stop_price") or "stop" in str(x.get("type","")).lower()):
                has_stop.add(x["symbol"])
    pos=api(k,s,"/v2/positions"); naked=[p["symbol"] for p in pos if p["symbol"] not in has_stop]
    tag=acct["account_number"]
    if not naked:
        print(f"  {G}PASS{N} {tag}: 0/{len(pos)} naked")
    elif len(naked) <= 5:   # a few just-entered names awaiting their protect cycle is normal
        print(f"  {Y}WARN{N} {tag}: {len(naked)}/{len(pos)} naked (likely fresh entries) {naked}")
    else:
        print(f"  {R}FAIL{N} {tag}: {len(naked)}/{len(pos)} naked {naked}"); rc=1
sys.exit(rc)
PY
[ $? -ne 0 ] && fail=1

echo
if [ "$fail" -eq 0 ]; then echo -e "\033[32mPREFLIGHT: ALL GREEN\033[0m"; else echo -e "\033[31mPREFLIGHT: ISSUES FOUND (see FAIL above)\033[0m"; fi
exit "$fail"
