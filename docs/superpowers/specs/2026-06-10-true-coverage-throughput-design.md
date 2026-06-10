# True Universe Coverage + Scan Throughput — Spec & Plan (APPROVAL GATE)

_Date: 2026-06-10 · Status: AWAITING APPROVAL · Operator ask: "true coverage across the universe;
too many in batches/in sector run together; more stocks + more predictions; do this ASAP."_

## 0. The two distinct problems (often conflated)

| Problem | Symptom operator sees | Root cause (verified in code) |
|---|---|---|
| **A. Throughput** | full universe takes many cycles to sweep | `max_symbols_per_scan: 175` caps each scan; `_fetch_bars_batch` sends ALL symbols in ONE un-chunked request (market_data.py:440-442), so the cap can't safely rise |
| **B. Coverage clustering** | "too many in a batch/sector run together" | rotation discovery takes a **contiguous slice** of the funnel-ranked shortlist (universe_rotation.py:116-119): `available[start : start+bucket]`. Contiguous rank = one score band = one hot sector scanned together; the tail waits |

Both must be fixed for genuine "true coverage." A is necessary (scan more/cycle); B is what makes
each cycle a *representative cross-section* instead of a sector clump. Neither touches scoring
weights or trade logic.

---

## PART A — Throughput: chunked batch fetch + aligned caps

### A1. Chunk `_fetch_bars_batch` (the unlock)
Today it does `params["symbols"] = ",".join(ALL symbols)` in one request — which is exactly why
175 is the ceiling (URL length + Alpaca per-request symbol limits). Change: iterate in chunks of
`max_symbols_per_batch` (175), accumulate `bars_by_symbol` across chunks (the pattern already
written in `universe_expansion.fetch_daily_closes_volumes`). Pure mechanical change; per-symbol
output identical. `api_requests_used`/`batch_requests_used` counters already track the extra calls.

**Implication / worked example:** scan 350 symbols → 2 chunked requests (was: truncate to 175,
1 request). Rate limiter headroom is ~149/min; a cycle today uses ~3 requests, so 350-sym cycles
use ~5 — no rate pressure. Cycle time grows from ~85s to ~110s, well inside the 5-min interval.

### A2. Raise the aligned caps (only AFTER A1 lands + tests green)
| Param | Now | New | Implication |
|---|---|---|---|
| `market_data.alpaca.max_symbols_per_scan` | 175 | **350** | true per-cycle scan = 350 |
| `watch_universe_rotation.max_symbols_per_cycle` | 350 | **350** (already) | now actually honored end-to-end |
| `rotating_bucket_size` | 350 | **350** | matches |
| `intraday.max_symbols_per_cycle` | 175 | **175 (keep)** | intraday is research-only (`use_for_scoring: false`); 175 is a real budget — leaving it bounds the per-cycle intraday burst |
| `settings.max_symbols` (top-level) | 175 | **350** | manual full-scan parity |

Coverage math at shortlist 1000: 1000/350 ≈ **3 cycles ≈ 15 min** full sweep (vs ~6 cycles/30 min
at 175). For 2k+ shortlist later, A3 (below) is the next dial.

### A3. (deferred, documented) higher caps for 2k+
500/cycle is feasible (3 chunked requests) once A1/A2 prove stable for a week. Each step is a
one-line config bump gated on watching `rate_limit_warnings` stay 0 and cycle time < interval.

---

## PART B — True coverage: strided rotation (kills sector/score clustering)

### B1. The mechanism (deterministic decimation, no RNG)
Replace the contiguous discovery window with an **evenly-strided comb** across the entire ranked
`available` list. For a bucket of B from N available:
```
step = N / B                       # e.g. 1000/350 = 2.857
indices = round((offset + i*step)) % N   for i in 0..B-1
offset advances by 1 each cycle    # epoch length = ceil(step) cycles -> full coverage
```
Each cycle's picks are spaced ~`step` apart in rank → consecutive scanned names are in DIFFERENT
score bands → mixed sectors by construction. No clustering. Fully deterministic (testable, no
seed/RNG), still covers every name once per epoch — same total coverage, evenly distributed.

**Worked example (N=1000 shortlist, B=350):** today cycle-1 scans ranks 1-350 (top band: the hot
sector), cycle-2 ranks 351-700, etc. — a hot-sector clump first, the tail last. With strided:
cycle-1 scans ranks {1, 4, 7, 10, ... 997} — a thin comb spanning the WHOLE list, every sector and
score band represented; cycle-2 {2, 5, 8, ...}; cycle-3 {3, 6, 9, ...}; epoch (3 cycles) = full
universe, each cycle a faithful cross-section. "More predictions across the variety" — every cycle.

### B2. Why not shuffle / sector-round-robin
- **Shuffle-deck**: also decorrelates, but needs a seed for determinism and reshuffle bookkeeping;
  strided gives the same even cross-section with simpler, RNG-free, trivially-tested code.
- **Sector-stratified round-robin**: strongest sector guarantee but needs sector data injected into
  the rotator (new coupling) and can starve large sectors. Deferred to a wave-3 enhancement IF
  strided's proportional representation proves insufficient (it won't for "representative coverage").

### B3. Scope guardrails
Only the discovery step (precedence 4) changes. Core/open-position/carryover steps (1-3) are
untouched — open positions and high-priority carryover still always scanned. `bucket_id` semantics
preserved for the dashboard.

---

## Interaction with the universe expansion
- A+B make a 2k–2.6k universe genuinely coverable: 1000-shortlist swept evenly in 3 cycles, every
  cycle sampling all sectors. Without B, a bigger universe makes clustering WORSE (longer contiguous
  runs). Without A, it makes sweeps slower. They're the prerequisites for growth paying off.
- Zero changes to scoring weights, thresholds, snapshot `min_score`, or trade gating.

## Test plan (TDD, offline)
- **A1**: `_fetch_bars_batch` chunking — multi-chunk accumulation, a symbol split across chunks,
  the 175-boundary, empty/oversized lists; mock `requests`. Assert identical per-symbol output vs
  the single-request path.
- **A2**: config load asserts new caps; a watch-cycle test (FakeProvider) scans the full presented
  set (no silent truncation).
- **B1**: `WatchUniverseRotator` strided coverage — over `ceil(step)` cycles every available symbol
  is scanned exactly once (full-coverage invariant); each cycle's picks are spread (assert max gap
  between consecutive ranks ~step, i.e. NOT contiguous); core/open/carryover precedence unchanged;
  N<B and N==0 edge cases.

## Rollout (after close, its own deploy — NOT bundled with the floor change)
1. A1 + B1 + tests green on branch; full suite.
2. VM dry validation: `watch --max-cycles 3` in a worktree → confirm 3 cycles cover the shortlist
   evenly + cycle time < 5 min + `rate_limit_warnings: 0`.
3. Merge → VM pull → restart `tradingbot-watch` after close → watch 3 live cycles; verify the
   cycle-summary `symbols_scanned` ≈ 350 and discovery picks span sectors.
4. Roll A3 (500/cycle) only after a clean week.

## Decisions needed from operator
1. **Approve A1 chunking + raise scan cap 175→350?** (the throughput core)
2. **Approve B1 strided rotation?** (the anti-clustering core)
3. Bundle A+B in one branch/PR (faster) or two (smaller blast radius each)?
