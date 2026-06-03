# Command Center Bridge — Data Contract

**Status:** Draft for coordination (2026-06-02)
**Producer:** the bot (this repo) — `src/trading_bot/vault/bridge.py` / `agent_bridge.py`
**Consumer A:** the Command Center agent "Tony Stocks" (`tony_bridge.py`, separate workspace) — reads Tony's picks
**Consumer B:** the dashboard (`dashboard-web`) — reads Tony Stocks' structured output to fill the "second layer" slots

This is the single source of truth for the JSON that crosses the boundary. Both terminals build to it independently. Markdown remains for agents; **JSON is authoritative for the dashboard.**

## Endpoint (to be added to the FastAPI app)

`GET /api/command-center` → `CommandCenterResponse`

Until this exists, the dashboard's `useCommandCenter()` hook returns empty and every second-layer slot renders "⋯ awaiting".

## Shape

```jsonc
{
  "picks": {
    "NVDA": {
      "symbol": "NVDA",
      "score": 91,                       // 0–100, Tony Stocks' own score
      "verdict": "reaffirm",             // enum: reaffirm | adjust | override | close
      "reasoning": "Financials clean; no earnings in window; raised conviction.",
      "returned_at": "2026-06-02T14:20:00Z"  // ISO 8601 UTC
    }
    // keyed by ticker symbol (uppercase)
  },
  "record": {
    "win_rate": 0.64,                    // 0–1
    "avg_pl_per_trade": 1.9,             // R multiple or % (match Tony's units)
    "target_hits": 38,
    "stop_hits": 21,
    "equity_curve": [100, 101.2]         // simulated paper equity, same basis as Tony's
  },
  "agreement": {                          // tallies for "does the 2nd pass help?"
    "agreed_right": 52,
    "agreed_wrong": 14,
    "cc_overrode_saved": 9,
    "cc_overrode_missed": 4
  }
}
```

## Dedup key

A pick is identified by **`symbol` + `scan_run_id`** (or `symbol` + ISO `date` if run id is unavailable). The producer must not emit two records for the same key; the Command Center must dedup on it before forming a verdict so neither side double-counts.

## Verdict enum (must match `dashboard-web/lib/signal.ts`)

`reaffirm` (✓, green) · `adjust` (◐, amber) · `override` (⊘, red) · `close` (✕, red) · *(absent → "⋯ awaiting", muted)*

## Notes
- All scores are integers 0–100 to match Tony's display.
- `equity_curve` must share Tony's basis (same starting capital / units) so the two lines are comparable on the Track Record chart.
- The dashboard treats any missing field as "awaiting" and never errors on partial data.
