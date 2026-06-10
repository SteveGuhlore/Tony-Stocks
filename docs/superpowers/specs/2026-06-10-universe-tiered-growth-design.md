# Universe 2k–3k: Tiered Growth via Dynamic Gatekeeping — Design Spec (Wave 2+)

_Date: 2026-06-10 · Status: PROPOSED (floors need operator sign-off) · Follows: 2026-06-10-universe-expansion-design.md_

## 1. The reframe that makes 2k–3k safe

Wave-1's live dry-run proved the static floors saturate at ~1,150 names. The operator wants
2k–3k **without dead weight**. The key architectural fact (verified in code): this system
already has THREE DYNAMIC quality layers behind the universe file —

1. **Research funnel (daily)** — ranks the whole universe (RS + analyst signal), hard-drops
   below its dollar floor, and caps the scan pool at `shortlist_size`. A dormant name simply
   never makes the shortlist; it costs a cached-metrics lookup, NOT scan/API budget.
2. **Volume sub-score (per scan)** — score_engine.py:296-309: +35 pts for ≥500k shares,
   +35 for ≥$5M dollar volume, +RVOL component, weighted 0.18. A thin name loses ~12.6
   final points → must be exceptional elsewhere to clear the snapshot gate (min_score 60).
3. **Role adjustment** — additions under $25M/day land `speculative_candidate` (−2 pts).

**Therefore: dead weight is a scan-budget problem, not a file-size problem.** The plan moves
gatekeeping from the bluntest instrument (static admission floors) to these dynamic layers,
which re-evaluate every name every day. The universe file becomes "everything mechanically
tradeable"; the funnel decides who's alive *today*.

## 2. What "tradeable" means for THIS bot (first principles)

Entries are capped at `max_notional_per_position: $1000`. Fill size is never the issue — a
$1k order is invisible even on a $1M/day name. The real floor is **microstructure quality**:
spread cost vs the strategy's edge, and bar cleanliness for breakout/momentum signals.

| Daily dollar volume | Typical spread | 2–4% swing-target edge eaten | Verdict |
|---|---|---|---|
| ≥$5M | ~5–15 bp | <5% | current tier — pristine |
| $2–5M | ~10–30 bp | ~5–15% | tradeable; scorer already penalizes −12.6 |
| $1–2M | ~30–80 bp | ~20–40% | edge erosion gets real — EXCLUDE |
| <$1M | 50–150 bp | strategy noise | never |

Concrete arithmetic examples of what each change admits:
- **$45 industrial, 180k sh/day = $8.1M** — rejected today by the 300k share floor despite
  being more liquid (in dollars) than half the universe. Wave 2 admits it; it keeps the full
  $5M-dollar score points, loses only the share-floor 35 → −6.3 net. Exactly right.
- **$20 consumer name, 140k sh/day = $2.8M** — Wave-2 tier-B: funnel admits (≥$2M), scorer
  docks the full −12.6, role −2 → surfaces only on genuinely strong setups. Right.
- **$14 microcap, 70k sh/day = $1.0M** — stays excluded in every wave (spread eats the edge).
- **$3.50 name, 800k sh/day = $2.8M** — dollar-liquid but sub-$5: halts/reverse-split churn.
  Wave-3 decision (price floor $5→$4), NOT wave 2.

## 3. The waves (each measurable, each reversible)

**Wave 1 — tonight, already merged:** execute as-is → ~1,150. Baseline funnel-eval recorded
(52 picks, 63% win, stages insufficient_data).

**Wave 2 — the floor realignment (this spec's core):**

| Param | Where | Now | New | Why / implication |
|---|---|---|---|---|
| `min_avg_volume` | scan settings (default_config:16) | 300k | **150k** | share count double-counts dollar volume; frees mid-priced quality names. Pre-screener follows automatically. |
| `min_avg_volume` | universe YAML `filters:` | 300k | **150k** | consistency |
| `min_avg_volume` | expansion ScreenThresholds | 300k | **150k** | + new CLI flag `--min-avg-volume` |
| `min_dollar_volume` | expansion ScreenThresholds | $5M | **$2M** | ALIGN with the scanner's own scan floor (already $2M!) — expansion was stricter than the live scanner. + CLI flag `--min-dollar-volume` |
| `min_dollar_volume` | research_funnel | $5M | **$2M** | the funnel's RANKING + `shortlist_size: 1000` becomes the daily governor instead of a static floor |
| `max_price` | scan + expansion | $500 | **$1000** | ~20 quality names; $1k notional cap → 1-share positions, mechanically fine (under-risked, harmless) |
| `min_price` | everywhere | $5 | **$5 (keep)** | sub-$5 churn is wave-3, evidence-gated |
| scoring volume thresholds | scoring_config | 500k / $5M | **UNCHANGED — deliberately** | this is the dynamic quality backstop; loosening the front door while keeping the scorer strict is precisely what prevents dead weight becoming dead trades |
| scoring weights | scoring_config | — | **UNTOUCHED** | weight changes go through the governed divergence-calibration two-key path, never hand edits |

Estimated result: ≥$2M/day US common stocks ≈ 2,200–2,800 → **universe lands ~2k–2.6k**.
We don't argue the estimate — the new CLI flags turn it into a measurement: one dry-run
prints the exact survivor count per candidate floor before anything is committed.

**Wave 3 — optional, evidence-gated (1+ week of funnel-eval after wave 2):**
price floor $5→$4 (or $3, matching the YAML's existing `min_price: 3`); add RVOL to the
funnel's ranking weights (surfaces names that are alive TODAY — high value at 2k+ universe).

## 4. Throughput follow-up (the real enabler — separate tested change)

Coverage math: shortlist 1000 at 175 scanned/cycle ≈ 6 cycles ≈ 30 min full coverage (vs
~17 min today). The fix is the already-logged follow-up: **chunk `_fetch_bars_batch` at
`max_symbols_per_batch`**, then raise `max_symbols_per_scan` + rotation caps in tandem
(350 → ~15 min at 2 extra requests/cycle; rate headroom ~149/min is ample). This is its own
PR with tests — NOT bundled into tonight's config change. Until it lands, the cost of wave 2
is honest: ~2× slower full-universe sweep, mitigated by carryover + open-position priority.

## 5. Closing the loop on dead weight (symmetric prune)

Backlog (small, after wave 2 beds in): `prune-universe` CLI — names whose cached
dollar-volume sits below floor for N consecutive scans → report → optional move to the
quarantine list (provenance `notes:` from the expansion make additions auditable). Growth
AND decay both become measured, reversible operations.

## 6. What we deliberately do NOT do
- No scoring-weight edits outside the calibration path (guardrail).
- No snapshot `min_score` 60 loosening — it would raise prediction COUNT by lowering
  prediction QUALITY; revisit only with score-calibration evidence.
- No floor below $1.5–2M/day dollar volume — spread arithmetic above.
- No bundling of the batch-chunking change into a config-only deploy.

## 7. Test/rollout checklist (wave 2)
1. ScreenThresholds defaults + CLI flags + tests (boundary cases at 150k/$2M).
2. default_config + universe-YAML floor edits; funnel floor + test.
3. Dry-run on VM with flags at BOTH floors ($2M/150k and $5M/300k) → print both counts.
4. `--execute` after close → restart watch → verify rotation/shortlist counts in startup log.
5. funnel-eval after ~1 week; wave-2 cohort visibly tagged (`discovery_screened` + notes) →
   prune/quarantine the cohort if KEPT-vs-DROPPED degrades.
