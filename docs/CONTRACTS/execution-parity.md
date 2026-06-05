# Execution Parity Contract — Bot vs Command Center (head-to-head)

**Status:** v1.1 (2026-06-05) — adds the B1 conviction-sizing experiment (Section B.1)
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

### What we vary, and when (keep the experiment clean)
Tony emits a `confidence` (low/med/high). Sizing bigger on high conviction tests a *second*
hypothesis (sizing skill) on top of selection quality, so it is staged separately:
- **Phase 1 (B0, baseline):** identical fixed-risk 1% sizing on both books → isolates
  *"does the reasoning pick better?"* (picking-alpha).
- **Phase 2 (B1, below):** Tony's book scales size by conviction; **the bot stays flat-1%
  as the control** → isolates *"does conviction sizing add return on top of selection?"*
  (sizing-alpha).

---

## B.1 The B1 conviction-sizing experiment (conviction-scaled Tony vs flat-1% bot)

**B1 lives entirely in Tony's book (`alpaca_paper`).** It does *not* change the bot's
execution. For the head-to-head to stay falsifiable, three things MUST hold on the bot side:

1. **Bot stays flat-1% — it is the control group.** The bot must **not** adopt conviction
   sizing to "match" Tony. The bot's sizing is `size_position(entry, stop, equity, config)`
   in `execution/order_router.py` — it has **no** conviction/confidence input by design, and
   must keep none. This is the single thing the tandem most easily gets wrong; it is locked
   by a guard test (`tests/test_b1_control_parity.py`). If the bot ever conviction-scales,
   B1 measures nothing.
2. **Tolerate an additive `sizing_attribution` key in `record.json`.** When B1 is live, the
   CC may add an optional `sizing_attribution` block to `tony_stocks_record.json` (e.g.
   `{"picking_alpha_pct": ..., "sizing_alpha_pct": ...}`). The bot side ingests record.json
   leniently (`api/routes/command_center.py::build_record` reads only known keys via `.get()`;
   `CommandCenterRecord` ignores extras) — an unknown key is **ignored, never a strict-schema
   reject**. Locked by `tests/test_b1_control_parity.py`.
3. **Report picking-alpha vs sizing-alpha separately.** Because the bot is the flat-1%
   control and Tony is conviction-scaled, the head-to-head report must decompose Tony's edge
   into **picking-alpha** (selection quality, comparable to the bot at equal sizing) and
   **sizing-alpha** (the extra return attributable to conviction sizing). Comparing raw
   returns alone conflates the two and is not a valid read of either hypothesis.

**Gate rule:** do not flip B1 on until this section is mirrored on **both** sides (bot +
Command Center) and the CC confirms it emits `sizing_attribution` and a picking/sizing-alpha
split. Section A (the execution/risk contract) is otherwise unchanged: the bot's 1% risk
policy and caps remain frozen.

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
