# Quality-Gated Universe Expansion (1k → ~2k) — Design Spec

_Date: 2026-06-10 · Status: APPROVED-PENDING-RUN · Branch: `feat/universe-expansion-2026-06-10`_

## 1. Problem & goal

Universe is 1,031 symbols (~5k listed). All three prior expansions (`expand_universe*.py`,
2026-06-03/04) were **hardcoded curated lists with no screening**. Goal: grow to ~2k **tradeable**
names by *criteria*, not count — the next tier of liquid mid-caps that clear the existing
price/volume/dollar-volume floors — plus retune the scaling knobs so coverage and enrichment
don't regress. Operator decision: quality-gated growth to ~1.5–2k (not 3k by count).

## 2. Why now / synergy
- The new sector-exposure cap (`max_positions_per_sector: 8`) will start blocking new financials;
  a wider, sector-classified pool gives the bot non-bank names to fill freed slots.
- Roadmap item 6 (auto-universe growth) stalled on "FMP screener is paid". **Unlock: Alpaca's
  `/v2/assets` endpoint is free** (trading API, works with existing paper keys) and lists every
  active tradable US equity. Liquidity screening uses the already-wired batch-bars pattern.

## 3. Pipeline (new module `src/trading_bot/data/universe_expansion.py` + CLI `expand-universe`)

```
1 DISCOVER  Alpaca GET /v2/assets?status=active&asset_class=us_equity   (free, paper keys)
            keep: tradable=true, exchange ∈ {NYSE, NASDAQ, ARCA, AMEX/NYSEMKT, BATS}
            drop: OTC, symbols with ./-/ suffix classes, warrants/units/rights/preferred (name heuristic)
2 DEDUPE    drop symbols already in universe YAML + quarantine list
3 SCREEN    Alpaca batch daily bars (175/batch, ~30 calendar days lookback):
            >=20 bars on IEX           (data-availability gate — pre-empts quarantine churn)
            5 <= last close <= 500     (existing scanner bounds)
            avg_volume_20    >= 300k   (existing pre-screener floor)
            dollar_volume_20 >= $5M    (existing funnel floor — the stricter liquidity gate)
4 SECTOR    Finnhub /stock/profile2 (free tier) for SURVIVORS only, throttled (~55/min);
            finnhubIndustry → canonical sector map (the YAML's 11 lowercase sectors);
            unknown → "" (loader-safe; flagged in report — sector feeds the NEW sector cap)
5 RANK+CAP  sort by dollar_volume_20 desc, take top --max-add (default 1000)
6 WRITE     YAML blocks in the proven expansion-2/3 format: QUOTED symbols (ON/NO boolean
            tickers), tags [discovery_2026_06, <sector>], role by liquidity
            (dollar_volume >= $25M → primary_candidate, else speculative_candidate),
            demo_profile base_building / high_volatility_whipsaw.
            Insert BEFORE the trailing `filters:` block. Idempotent (skips existing).
```

Dry-run by default; `--execute` writes. Report prints per-gate rejection counts, sector
distribution of additions, and unknown-sector list. The module is pure-core + injected fetchers
(fully testable offline; **no keys in this sandbox — the real run happens on the VM**).

## 4. Scaling knobs retuned in tandem (same branch)

| Knob | Now | New | Why |
|---|---|---|---|
| universe YAML `filters.max_universe_size` | 1100 | 2200 | loader truncates beyond it (universe.py:114) |
| `watch_universe_rotation.max_symbols_per_cycle` | 350 | 500 | ~1.2k shortlist / 500 ≈ full coverage in ~2–3 cycles (vs ~4 at 350). 500 = 3 Alpaca batches/cycle — well inside the 175/min limiter |
| `watch_universe_rotation.rotating_bucket_size` | 350 | 500 | keep bucket == per-cycle cap |
| `research_funnel.shortlist_size` | 600 | 1000 | else the funnel caps the benefit of a 2k universe |
| `pre_screener.min_symbols_after_filter` | 50 | 100 | fallback floor scales with universe |
| `research_funnel.enrich_per_run` | 50 | 50 (keep) | Finnhub free ~60/min; 2k warm ≈ 40 cycles ≈ 3.3h once, then daily cache. Accepted lag |

Per-cycle cost honest math: scan 500 = 3 batch requests (vs 2); intraday stays capped; rate-limit
headroom ~149/min — no risk. Cycle time grows ~40% (~85–120s), still inside the 5-min interval.

## 5. Measurement gate (before AND after — operator runs on VM)
```
PYTHONPATH=src .venv/bin/python -m trading_bot.cli funnel-eval --save-report
```
Baseline now; re-run after ~1 week at 2k. If KEPT-vs-DROPPED deltas degrade (funnel stops
separating winners), the expansion isn't paying — trim via quarantine/role demotion, don't grow.

## 6. Safety / rollout
- All work on `feat/universe-expansion-2026-06-10`; **zero effect on the live loop** until the
  VM pulls + the operator runs `expand-universe --execute` + restarts watch (after close).
- The script never deletes/edits existing symbols; additive only; validated post-write
  (yaml parse + duplicate check + non-string symbol check, per expansion-2/3 lessons).
- New symbols carrying sector="" are uncapped by the sector gate (by design) — report makes the
  gap visible; sector backfill is reusable later.
- Rollback = `git checkout` the YAML + restart (no DB/schema involvement).

## 7. Tests (offline, mocked — project convention)
- pure: asset filtering (OTC/class/heuristics), screen gates incl. boundary values + missing
  bars, industry→sector mapping, role assignment, YAML block building + quoting, insertion
  before `filters:`, idempotency.
- orchestrator with fake fetchers end-to-end; round-trip: written YAML re-parses via
  `load_universe_config`, boolean-ticker symbols stay strings, max_universe_size respected.
