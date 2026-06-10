# Sector-Exposure Cap — Design Spec

_Date: 2026-06-10 · Status: PROPOSED (interface-locked, awaiting cap values + go-ahead) · Branch: `claude/sweet-faraday-y4586j`_

## 1. Problem

The bot's only risk gates are **per-position**: `risk_per_trade_pct` (1%), `max_open_positions` (75),
`max_notional_per_position` ($1000), `max_daily_orders` (200). There is **no portfolio-level
concentration control**. "1% risk × N positions" is not N% of diversified risk when the positions
are correlated.

**Live evidence (2026-06-10 open, account `PA3P0RN75VL1`, 56 open):** the book is heavily
financials/banks — `C, WFC, USB, HBAN, TFC, CFG, FHN, RF, BEN, IVZ` (+ energy-materials cluster
`FCX, HAL, BKR, SLB`). A single rate/sector headline gaps that whole cohort together: the per-trade
1% caps say "diversified," the correlation says otherwise.

**Origin:** distilled from a Reddit r/OpenaiCodex thread — the substantive comment (federico_vitale)
called out that signal→bracket sizing is incomplete without "an overall risk balancing / exposure
limit." This spec implements that as a sector-concentration gate.

## 2. Goal / Non-goals

**Goal:** cap how many concurrent open positions the bot may hold in any one sector (Phase 1:
position-count cap). Fail-closed, pure, fully tested, and **off by default** so it cannot disrupt a
live session until the operator sets a value.

**Non-goals (this spec):**
- Notional/gross-exposure %-based caps → outlined as Phase 2 (needs per-position live notional).
- Mirroring the cap on the Command Center / Tony account (separate repo; out of scope, like the
  reprotect work).
- Touching scoring, trigger rules, or *existing* open positions — the gate only blocks **new** entries.

## 3. Design overview

Add one gate to the existing pure `should_trade()` in `order_router.py`, fed by:
- a new **config** field `max_positions_per_sector` (int; `0` = disabled), and
- a new **PortfolioState** field `open_sector_counts: Mapping[str, int]` (sector → # open positions),
  plus a new **`sector: str`** argument carrying the candidate's sector.

Sector *resolution* (symbol → sector) happens in the **impure** `_portfolio_state()` /
`open_triggered_picks()` layer (which already touches repo/broker), so `order_router` stays a pure,
side-effect-free decision function — consistent with its current contract.

### 3.1 Per-cycle correctness (already guaranteed by the existing loop)
`_portfolio_state()` is rebuilt **per pick** inside `open_triggered_picks()` and reads live open
positions via `repo.open_paper_position_symbols()`. After each approved pick calls
`repo.open_paper_position(...)`, the next pick's state — and therefore `open_sector_counts` — reflects
it. So the cap holds **within** a single cycle (the 6th bank won't open if the cap is 5), not merely
across cycles. No loop changes needed beyond building the counter.

## 4. Sector resolution (the load-bearing design decision)

`get_sector()` (`vault/sector_map.py`) is Title-Cased and **has gaps** — verified: `HBAN`, `HST`,
`MARA` → `"Unknown"`. Relying on it alone would leave real bank exposure (HBAN) uncapped, defeating
the control. Therefore resolution is **layered, highest-coverage first**:

```
resolve_sector(symbol):
  1. latest non-empty scan_results.sector for the symbol   # scanner's own classification, covers the live 1026 universe
  2. else get_sector(symbol)                                # vault/sector_map.py fallback
  3. else ""                                                # unknown
  normalize: .strip().lower()
```

- Same resolver is used for **both** the open positions and the incoming candidate, so bucketing is
  internally consistent regardless of source casing.
- **Uncapped buckets** (never blocked, never counted toward a cap): `{"", "unknown", "benchmark",
  "market"}`. Rationale: a risk gate must not reject a trade merely because we *can't classify* it —
  fail-open on unknown sector (availability over a weak, possibly-wrong cap). Unknowns are logged so
  the gap is visible and `sector_map`/universe config can be improved. (Design trade-off recorded:
  this is the one deliberate fail-open in an otherwise fail-closed gate.)

New repo method: `sectors_for_symbols(symbols: set[str]) -> dict[str, str]` — one query returning the
latest non-empty `scan_results.sector` per symbol; falls back to `get_sector` in Python for misses.

## 5. Interface contract (locked)

### 5.1 `PaperTradingConfig` (`execution/paper_config.py`)
```python
max_positions_per_sector: int = 0   # 0 = disabled (no sector cap). >0 = max concurrent open per sector.
```
Loaded via the existing `_coerce_int` pattern in `load_paper_trading_config`; added to the `common`
dict; **no fail-closed validation needed** (0/negative simply disables — clamp `<0` to `0`).
`default_config.yaml` `paper_trading:` gets `max_positions_per_sector: 0  # off until tuned`.

### 5.2 `PortfolioState` (`order_router.py`)
```python
open_sector_counts: Mapping[str, int] = field(default_factory=dict)  # normalized sector -> open count
```
Frozen dataclass keeps a `Mapping` via `default_factory=dict` (never mutated; frozen only forbids
attribute reassignment). Default empty → existing constructors and all current tests are unaffected.

### 5.3 `should_trade(...)` (`order_router.py`)
New keyword arg `sector: str = ""`. New gate, placed **immediately after** the `max_open_positions`
check (it is a capacity/concentration gate, same family), **before** `max_daily_orders` and sizing:
```python
sec = (sector or "").strip().lower()
cap = config.max_positions_per_sector
if cap > 0 and sec and sec not in _UNCAPPED_SECTORS:
    if state.open_sector_counts.get(sec, 0) >= cap:
        return OrderDecision(False, 0, f"sector cap reached for {sec} ({cap})")
```
`_UNCAPPED_SECTORS = frozenset({"", "unknown", "benchmark", "market"})`. Fails closed on every other
path (unchanged). Backward-compatible: default `sector=""` + default `cap=0` → exact current behavior.

### 5.4 Impure wiring (`execution/paper_engine.py`)
- `_portfolio_state(...)`: build `open_sector_counts` = `Counter(resolve_sector(s) for s in open_symbols)`
  (normalized; drop uncapped buckets), via the new `repo.sectors_for_symbols(...)`.
- `open_triggered_picks(...)`: resolve the candidate's sector once per pick and pass `sector=` into
  `should_trade(...)`. Rejections already flow into the `rejected` list → visible in the cycle summary.

## 6. Alternatives considered
- **Gate inside the DB/repo layer** — rejected: pollutes the pure router contract; harder to test.
- **`get_sector` only** — rejected: coverage gaps (HBAN/HST/MARA) silently neuter the cap.
- **Notional %-of-equity sector cap first** — deferred to Phase 2: needs live per-position notional
  (mark-to-market), more moving parts; count-cap delivers 90% of the protection with far less risk.
- **Hard-fail on unknown sector** — rejected: would block legitimately-tradeable names we can't
  classify; unacceptable availability hit for a concentration heuristic.

## 7. Rollout / safety
- Ships **disabled** (`max_positions_per_sector: 0`). Zero behavior change until the operator sets a
  value (recommend `8` to start, given ~56 positions across ~10 sectors). Tunable without code change.
- Read-only on existing positions; only gates *new* entries; fail-closed except the documented
  unknown-sector fail-open. No scoring/trigger/strategy changes. Deploy is config+code, no schema
  migration (uses existing `scan_results.sector`).

## 8. TDD task plan
1. `paper_config.py` + test: new field loads, clamps `<0`→0, default 0.
2. `order_router.py` + `test_order_router.py`: add `open_sector_counts`/`sector`; gate tests —
   (a) rejects at limit, (b) allows under limit, (c) disabled when cap=0, (d) unknown/benchmark/""
   sector uncapped, (e) different sector unaffected, (f) backward-compat (no args → current behavior).
3. `repositories.py` + test: `sectors_for_symbols` returns latest non-empty scan_results.sector;
   falls back to `get_sector`; missing → "".
4. `paper_engine.py` + test: `_portfolio_state` builds the counter; `open_triggered_picks` passes
   sector and the gate blocks the Nth same-sector pick **within one cycle** (live-like broker double).
5. Full suite green; `full_e2e_sync_test.py --quick` per DEPLOY_RULES.

## 9. Phase 2 (future, not now)
`max_sector_exposure_pct` — cap a sector's gross notional as % of equity, marked to live price.
Reuses the resolver + counter scaffolding; adds notional summation from the ledger/equity-curve marks.
