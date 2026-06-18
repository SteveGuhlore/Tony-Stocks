#!/usr/bin/env bash
# set_data_feed.sh — switch the bot's Alpaca market-data feed and restart the consumers.
#
#   bash scripts/deploy/set_data_feed.sh sip    # full consolidated tape (needs Alpaca "Algo Trader Plus")
#   bash scripts/deploy/set_data_feed.sh iex    # free IEX feed (default / instant revert)
#   bash scripts/deploy/set_data_feed.sh show   # print the current setting
#
# WHY: the bot reads ALPACA_DATA_FEED at provider startup (src/trading_bot/data/market_data.py).
# IEX is free but thin (~2-3% of volume), so many symbols return stale/no recent bars and the
# scanner correctly skips them -> very few entries. SIP is the full real-time tape and fixes that.
#
# This script ONLY flips the env var + restarts services. SIP *data* requires the paid Alpaca
# market-data subscription on the account that owns ALPACA_API_KEY — subscribe first, then run
# `set_data_feed.sh sip`. If SIP isn't active you'll see HTTP 403 / "subscription" errors in the
# watch log; revert instantly with `set_data_feed.sh iex`.
set -uo pipefail

ENVF="${BOT_ENV:-/opt/trading-bot/.env}"
arg="${1:-show}"

[ -f "$ENVF" ] || { echo "no env file at $ENVF (override with BOT_ENV=...)"; exit 1; }

cur() { grep -E '^ALPACA_DATA_FEED=' "$ENVF" 2>/dev/null | tail -1 | cut -d= -f2- ; }

if [ "$arg" = "show" ]; then
  v="$(cur)"; echo "ALPACA_DATA_FEED=${v:-<unset, defaults to iex>}"; exit 0
fi
case "$arg" in
  iex|sip) ;;
  *) echo "usage: set_data_feed.sh [iex|sip|show]"; exit 1 ;;
esac

if grep -qE '^ALPACA_DATA_FEED=' "$ENVF"; then
  sed -i -E "s/^ALPACA_DATA_FEED=.*/ALPACA_DATA_FEED=$arg/" "$ENVF"
else
  printf '\nALPACA_DATA_FEED=%s\n' "$arg" >> "$ENVF"
fi
echo "set ALPACA_DATA_FEED=$arg in $ENVF"

echo "restarting data consumers..."
for s in tradingbot-watch tradingbot-api tradingbot-offhours; do
  if systemctl list-unit-files "$s.service" >/dev/null 2>&1; then
    sudo systemctl restart "$s" && echo "  restarted $s" || echo "  WARN: failed to restart $s"
  fi
done

echo
echo "Give it one scan cycle (~1-2 min), then verify:"
echo "  journalctl -u tradingbot-watch --since '3 min ago' --no-pager | grep -iE 'feed|stale|no bars|HTTP 4|subscription' | tail -20"
echo "If you see HTTP 403 / 'subscription' -> SIP not active on the account; revert: $0 iex"
