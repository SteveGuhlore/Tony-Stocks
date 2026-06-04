# Execution Parity Contract — Bot vs Command Center (head-to-head)

**Status:** v1 (2026-06-04)
**Purpose:** Make the bot-vs-CC paper-trading experiment *valid*. A head-to-head only
means something if it has **one independent variable**. We hold the entire "physics of
trading" identical across both books and vary **only the brain** (how each decides). If
execution/risk/grading also differed, a performance gap would be unattributable — you
couldn't tell whether Tony's reasoning helped or whether he just had a bigger account,
tighter stops, or a different fill model.

Both terminals build to this contract independently. The **bot's `paper_trading` config
is the canonical reference**; the CC must match these values.

---

## A. MUST BE IDENTICAL — the execution & risk contract

| Parameter | Canonical value (bot) | Why it must match |
|---|---|---|
| Risk per trade | `risk_per_trade_pct: 1.0` (% of equity risked = entry→stop distance) | The core sizing policy; neither side implicitly leveraged. |
| Position-sizing formula | `shares = floor( (risk_pct × equity) ÷ (entry − stop) )` | Same formula both sides. |
| Max open positions | `max_open_positions: 50` | Same concurrent exposure. |
| Max notional / position | **1% of account equity** → bot ($100k) = `1000`; CC ($1M) = `10000` ✅ | Same *%* single-name cap so concentration matches across unequal account sizes. **Aligned 2026-06-04:** bot `1000`, CC `10000` — clean 1%-of-account match. |
| Max daily orders | `max_daily_orders: 200` | Same activity ceiling. |
| Order mechanics | market entry + **GTC** OCO bracket (take-profit limit + stop) | Same fill + protection behavior. |
| Time-in-force | `gtc` | Protection persists overnight on both. |
| Fee / slippage model | Alpaca paper defaults (both) | Same cost assumptions. |
| Candidate set | the **same scanner picks** (same symbols, same scanner score, same baseline entry/stop/target) | Both judge the *same opportunities*. |
| Trigger definition | price crosses `entry` | "Did it enter" defined identically. |
| Outcome grading | same resolver: same target/stop-hit logic, same price data, same holding/expiry rules | Both books graded by one harness. |
| Trading calendar / session window | NYSE hours; watch window 09:35–16:10 ET | Same clock. |

### Comparison basis (so equal $ capital is NOT strictly required)
What matters is the **risk policy (%)**, not the absolute account size. Compare in
**% returns / equity normalized to an index of 100**, exactly as
`docs/CONTRACTS/command-center-bridge.md` requires (`equity_curve` must share Tony's
basis). If you also want intuitive dollar comparison, align starting capital (e.g. both
$1M) — optional, and disruptive to do mid-run (resets open positions), so prefer
normalized comparison.

---

## B. DELIBERATELY DIFFERENT — the independent variable (the brain)

| Dimension | Bot | CC / Tony |
|---|---|---|
| Reasoning method | Deterministic technical scoring (trend / momentum / volume / risk / setup) | LLM qualitative synthesis |
| Tools / inputs | Scanner indicators, single price feed | News, fundamentals, analyst ratings, catalysts, web research (FMP/Finnhub), now the Research Funnel |
| The decision | Takes every triggered scanner pick at scanner levels | `reaffirm` / `adjust` / `pass` / `override` / `close` |
| Level adjustments | Uses scanner stop/target as-is | May move stop/target (its reasoning) |

### The subtle point: level adjustments flow through the SAME risk formula
When Tony **adjusts a stop**, the entry→stop distance changes, so at the *same 1% risk*
his **share count differs** from the bot's. **This is correct, not a parity violation** —
the *policy* (1% risk) is identical; the *stop level* is his decision. Keep the formula
fixed; let each agent's chosen stop flow through it.

### What we do NOT vary yet (keep the experiment clean)
**Conviction-based sizing is deferred.** Tony emits a `confidence` (low/med/high). Sizing
bigger on high conviction is tempting, but then you're testing *two* hypotheses at once
(selection quality **and** sizing skill).
- **Phase 1 (now):** identical fixed-risk sizing → isolates *"does the reasoning pick better?"*
- **Phase 2 (later, separate experiment):** conviction sizing, once a selection edge is established.

---

## C. Action items to reach parity
1. **Verify the CC's risk policy + caps match Section A** (`risk_per_trade_pct`,
   `max_open_positions`, `max_notional_per_position`, `max_daily_orders`, GTC bracket,
   sizing formula). The CC config lives in the Command Center workspace — **must be checked
   there** (not visible from this repo).
2. **Adopt normalized-equity comparison** (index to 100) on the dashboard's head-to-head
   chart so unequal starting capital doesn't distort the read.
3. **Single source of truth:** any change to a Section-A parameter on one side must be
   mirrored on the other. Treat Section A as frozen unless both books change together.

## D. What is already shared today
- Candidate set + baseline levels: both consume the **same bridge** (`command-center-bridge.md`).
- Outcomes: the bot emits `tony_stocks_outcomes.json`; the CC grades against it (one resolver).
- Pure separation: the bot ignores Tony's verdicts on its own book — the divergence *is*
  the measurement (`close_on_command_center_exit: false`).
