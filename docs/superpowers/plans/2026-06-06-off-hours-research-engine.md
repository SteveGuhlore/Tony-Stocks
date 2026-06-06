# Off-Hours Research Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Spec: `docs/superpowers/specs/2026-06-06-off-hours-research-engine-design.md`.

**Goal:** A read-only off-hours engine (weekdays 16:30→09:00 ET + weekends) that prepares a ranked, catalyst-aware, recalibrated Morning Watchlist + plan for the next open, with **zero execution path** (no auto-entry off-hours).

**Architecture:** Pure cores in `analytics/`, a data seam in `data/`, orchestration in `cli.py`, fail-quiet sinks (reports file / vault note / CC bridge / FastAPI route + Next.js tab). ~80% reuse of existing machinery (`run_scan`, `research_providers`, `run_learn`, `divergence_calibration`, `funnel_eval`, `learning_narrator`, vault/bridge/api patterns).

**Tech Stack:** Python 3 (stdlib `dataclasses`, `enum`, `zoneinfo`, `datetime`), pytest, FastAPI/Pydantic v2, Next.js (App Router) + TanStack Query, PowerShell scheduled task.

**Run tests:** `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` (or `$env:PYTHONPATH="src"; python -m pytest tests/<file> -v`).

**Note for executors:** This plan locks the *interfaces* (the cross-task contract) exactly. For implementation bodies, follow the cited existing-pattern file in each task — match its structure, fail-quiet style, and conventions. Do NOT invent alternate signatures; the names/fields below are the integration contract every task depends on.

---

## Interface Contract (every task MUST conform — do not rename)

```python
# analytics/off_hours_window.py
class Phase(str, Enum):
    POST_CLOSE = "post_close"; OVERNIGHT = "overnight"; PRE_OPEN = "pre_open"
    WEEKEND = "weekend"; MARKET_HOURS = "market_hours"
def is_off_hours(now_et: datetime) -> bool          # False only weekday 09:30–16:00
def current_phase(now_et: datetime) -> Phase
def next_market_open(now_et: datetime) -> datetime

# data/premarket_provider.py
@dataclass(frozen=True)
class PreMarketQuote: symbol: str; last: float; prev_close: float; gap_pct: float; as_of: str
class PreMarketProvider(Protocol):
    def get_premarket_quote(self, symbol: str) -> PreMarketQuote | None: ...
class NullPreMarketProvider:  # used now; returns None always

# analytics/catalyst_enrichment.py
@dataclass(frozen=True)
class CatalystTags:
    symbol: str; upcoming_earnings_date: str | None = None; earnings_blackout: bool = False
    analyst_rec_trend: str = "flat"; news_sentiment: float | None = None
    revenue_growth: float | None = None
    def to_dict(self) -> dict: ...
def build_catalyst_tags(symbol, *, earnings_date=None, today: date, blackout_days=5,
    recommendation_now=None, recommendation_prev=None, news_sentiment=None,
    revenue_growth=None) -> CatalystTags

# analytics/morning_prep.py
@dataclass(frozen=True)
class PrepCandidate:
    symbol: str; score: float; setup: str; entry: float | None; stop: float | None
    target: float | None; rr: float | None; conviction: str; catalysts: dict; warnings: list[str]
@dataclass(frozen=True)
class MorningPrep:
    generated_at: str; et_date: str; phase: str; shortlist: list[PrepCandidate]
    what_changed_overnight: str; plan_for_open: str
    def to_dict(self) -> dict: ...
def build_morning_prep(*, scored_rows: list[dict], catalyst_tags: dict[str, CatalystTags],
    open_positions: list[dict] | None = None, learning_facts: dict | None = None,
    calibration_proposals: list[dict] | None = None, premarket: dict | None = None,
    now_et: datetime, phase: str, shortlist_size: int = 20) -> MorningPrep

# vault/morning_prep_writer.py
def render_morning_prep_markdown(prep: MorningPrep, *, narrative: str | None = None) -> str
def write_morning_prep_note(prep, *, vault_dir, narrative=None) -> Path
def write_morning_prep_bridge(prep, *, command_center_dir, narrative=None) -> Path | None
def write_morning_prep_report(prep, *, reports_dir) -> Path   # writes <date>.json + <date>.md
```

`conviction`: score≥0.80→"high", ≥0.60→"medium", else "low"; an `earnings_blackout` tag downgrades one band. `rr` = (target-entry)/(entry-stop) when all present else None. Date strings are ET `YYYY-MM-DD`; `generated_at`/`as_of` are ISO-8601 with offset. NOTE: scored_rows use the scan_results column names — score field is `total_score` (0–100; normalize /100 for the 0–1 conviction bands), setup is `setup_category`, levels are `planned_entry_price`/`stop_price`/`target_price`. Confirm against `storage/repositories.py` when implementing.

---

## Task 1: Off-hours window guard (pure)  [parallelizable — no deps]

**Files:** Create `src/trading_bot/analytics/off_hours_window.py`; Test `tests/test_off_hours_window.py`. Pattern: `cli.py:_is_within_regular_market_hours` (line ~2981) for ET tz handling.

- [ ] **Step 1 — failing tests.** Cover: weekday 10:00 ET → `is_off_hours False`, `current_phase==MARKET_HOURS`; weekday 16:45 → off_hours True, phase POST_CLOSE; 03:00 → OVERNIGHT; 08:30 → PRE_OPEN; Saturday 12:00 → WEEKEND, off_hours True; Sunday 12:00 → WEEKEND; `next_market_open` from Fri 18:00 → Mon 09:30, from Tue 08:00 → Tue 09:30. Use `datetime(..., tzinfo=ZoneInfo("America/New_York"))`.
- [ ] **Step 2 — run, expect fail** (`pytest tests/test_off_hours_window.py -v`).
- [ ] **Step 3 — implement.** `Phase` enum; `is_off_hours` (False only Mon–Fri 09:30–16:00); `current_phase` windows: MARKET_HOURS Mon–Fri 09:30–16:00; PRE_OPEN weekday 06:00–09:30; POST_CLOSE weekday 16:00–24:00; OVERNIGHT 00:00–06:00 (Mon–Fri); WEEKEND all Sat/Sun. `next_market_open`: next weekday 09:30 strictly after `now_et`.
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(off-hours): window guard core`.

## Task 2: Pre-market provider seam (stub now)  [parallelizable — no deps]

**Files:** Create `src/trading_bot/data/premarket_provider.py`; Test `tests/test_premarket_provider.py`. Pattern: `data/research_providers.py` (Protocol + adapter style).

- [ ] **Step 1 — failing tests.** `NullPreMarketProvider().get_premarket_quote("NVDA") is None`; `PreMarketQuote` is frozen and stores fields; a tiny fake implementing the Protocol returns a quote with computed `gap_pct`.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** `PreMarketQuote` dataclass, `PreMarketProvider` Protocol, `NullPreMarketProvider`. Add module docstring documenting future `AlpacaSipPreMarketProvider`/`PolygonPreMarketProvider` (commented placeholder classes, `raise NotImplementedError`).
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(off-hours): pre-market provider seam (Null)`.

## Task 3: Catalyst enrichment (pure)  [parallelizable — no deps]

**Files:** Create `src/trading_bot/analytics/catalyst_enrichment.py`; Test `tests/test_catalyst_enrichment.py`. Pattern: `analytics/tony_divergence.py` (pure classification core).

- [ ] **Step 1 — failing tests.** earnings_date 3 days out + blackout_days=5 → `earnings_blackout True`; 10 days out → False; None → False; rec_now net>prev → `analyst_rec_trend=="up"`, lower → "down", equal → "flat"; missing recs → "flat"; `to_dict()` keys match contract.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** `CatalystTags` + `build_catalyst_tags`. Finnhub recommendation dict net = `strongBuy*2+buy - sell - strongSell*2`; trend = sign(net_now - net_prev). Missing data → safe defaults.
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(off-hours): catalyst enrichment core`.

## Task 4: Morning-prep assembler (pure)  [depends on Tasks 1–3 interfaces only]

**Files:** Create `src/trading_bot/analytics/morning_prep.py`; Test `tests/test_morning_prep.py`. Pattern: `analytics/nightly_learning.py` (pure fact builder, sample-gated, `to_dict`).

- [ ] **Step 1 — failing tests.** Given 3 synthetic `scored_rows` (dicts with `symbol,total_score,setup_category,planned_entry_price,stop_price,target_price`) + a `catalyst_tags` map → `build_morning_prep` returns top-N sorted desc by score; conviction bands correct; blackout downgrades conviction; `rr` computed; `to_dict()` round-trips to the spec §4.1 shape (keys: generated_at, et_date, phase, shortlist[], what_changed_overnight, plan_for_open). Empty input → empty shortlist, no error.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** `PrepCandidate`, `MorningPrep`, `build_morning_prep`. Map scored_rows→candidates, attach catalyst dict, compute conviction/rr, sort, truncate to `shortlist_size`. `what_changed_overnight` = deterministic summary of `learning_facts` (e.g. "N new lessons; calibration: <state>") or "No overnight changes." `plan_for_open` = "<count> names armed; <high-conviction count> high-conviction; <blackout count> in earnings blackout."
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(off-hours): morning-prep assembler core`.

## Task 5: Vault writer + bridge + reports sink  [depends on Task 4]

**Files:** Create `src/trading_bot/vault/morning_prep_writer.py`; Test `tests/test_morning_prep_writer.py`. Pattern: `vault/learning_writer.py` (markdown render + write; mkdir parents; UTF-8).

- [ ] **Step 1 — failing tests.** `render_morning_prep_markdown` contains a "PLANNED" disclaimer + each shortlist symbol + an Obsidian `[[SYM]]` link; `write_morning_prep_note(tmp_path)` writes `morning_prep/<date>.md`; `write_morning_prep_report(tmp_path)` writes `<date>.json` (valid JSON matching `to_dict`) + `<date>.md`; `write_morning_prep_bridge` writes under `bridge/tony-stocks/morning-prep/<date>.md` and returns None if `command_center_dir` is None.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** the four functions. Markdown: header with et_date+phase, the PLANNED-not-entered disclaimer (reinforces invariant #1), a table of shortlist (symbol/score/setup/entry/stop/target/rr/conviction/catalysts), what_changed_overnight, plan_for_open, optional `narrative` block. JSON via `json.dumps(prep.to_dict(), indent=2)`.
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(off-hours): vault note + CC bridge + reports sink`.

## Task 6: Bridge contract doc  [parallelizable — docs only]

**Files:** Create `docs/CONTRACTS/morning-prep-bridge.md`. Pattern: `docs/CONTRACTS/self-learning-bridge.md`.

- [ ] **Step 1** Write the one-way contract: path `{cc}/bridge/tony-stocks/morning-prep/<ET-date>.md`, writer=bot, reader=CC Tony agent, cadence (post_close/overnight/pre_open/weekend), the markdown sections, and the pure-separation guarantee (bot never reads a live verdict here).
- [ ] **Step 2 — commit** `docs(off-hours): morning-prep bridge contract`.

## Task 7: Config + settings  [serialized — shared files]

**Files:** Modify `config/default_config.yaml` (add `off_hours:` block); Modify `src/trading_bot/settings.py` (`ScannerSettings.off_hours: dict | None = None`); Test `tests/test_off_hours_config.py`.

- [ ] **Step 1 — failing test** loads config and asserts `settings.off_hours["enabled"] is False` and defaults present (`cadence_minutes`, `earnings_blackout_days`, `shortlist_size`, `full_universe_scan`, `premarket_provider: "null"`, `enrich_budget`).
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** the YAML block (default-off) + the settings field.
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(off-hours): config + settings (default off)`.

## Task 8: CLI orchestration + safety guard  [serialized — modifies cli.py]

**Files:** Modify `src/trading_bot/cli.py` (`run_off_hours_prep`, `run_off_hours_watch`, subparsers `off-hours-prep` / `off-hours-watch`); Test `tests/test_off_hours_cli.py`, `tests/test_off_hours_no_execution.py`. Patterns: `run_learn` (line ~3764, fail-quiet per sink, exit 0), `run_watch` (loop + market guard, line ~1190), `_emit_due_bridges` (disk idempotency, line ~4022).

- [ ] **Step 1 — failing tests.** (a) `run_off_hours_prep` on a sandbox config produces `reports/morning_prep/<date>.json` and returns a summary dict; a failing sink (monkeypatched to raise) does NOT raise. (b) **Safety guard** `test_off_hours_no_execution.py`: import `trading_bot.cli`; assert the `run_off_hours_prep`/`run_off_hours_watch` source does **not** reference `run_paper_cycle`/`paper_engine`/`submit_bracket`/broker (assert via `inspect.getsource` not containing those tokens); and that `current_phase` during market hours short-circuits the prep loop.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement.** `run_off_hours_prep(args)`: determine phase (arg override or `current_phase`); `emit-outcomes` (reuse helper); deep scan via `run_scan` with `override_symbols=<full universe>` paced; enrich catalysts via `research_providers` (budgeted); if phase==overnight also call `run_learn`, `tony-divergence`, `divergence-calibration` surface, `funnel-eval --save-report` (each try/except); `build_morning_prep`; optional `learning_narrator` narrative; write all four sinks (each try/except). Return summary. **Never import/call the paper engine or broker.** `run_off_hours_watch(args)`: loop — sleep cadence; if `current_phase` is MARKET_HOURS → sleep & continue; else run the due phase once per ET day (disk-idempotent set keyed by `<date>:<phase>`); honor `data/STOP_WATCH_MODE`. Register subparsers.
- [ ] **Step 4 — run, expect pass** (`pytest tests/test_off_hours_cli.py tests/test_off_hours_no_execution.py -v`).
- [ ] **Step 5 — commit** `feat(off-hours): off-hours-prep + off-hours-watch CLI + no-execution guard`.

## Task 9: End-to-end sandbox test  [depends on Task 8]

**Files:** Test `tests/test_off_hours_e2e.py`. Pattern: `tests/test_learning_e2e.py` (temp sandbox, sha256 fingerprint isolation).

- [ ] **Step 1 — failing test.** In a temp sandbox config (redirected db/vault/reports/command_center_dir), run `run_off_hours_prep` for `post_close`; assert all four sinks exist (reports json+md, vault note, bridge file) and the JSON parses to the contract; re-run → idempotent (no crash); fingerprint the real `vault/` + `reports/` dirs before/after the test setup to assert **zero real-workspace mutation**.
- [ ] **Step 2–4 — run/iterate to green.**
- [ ] **Step 5 — commit** `test(off-hours): e2e sandbox + isolation`.

## Task 10: API route + schema  [serialized — modifies api/main.py, schemas.py]

**Files:** Create `src/trading_bot/api/routes/morning_prep.py`; Modify `api/schemas.py` (+`MorningPrepResponse`), `api/main.py` (register router); Test `tests/test_api_morning_prep.py`. Pattern: `api/routes/command_center.py` + `tests/test_api_command_center.py`.

- [ ] **Step 1 — failing test.** `GET /api/morning-prep` returns 200 with the latest `reports/morning_prep/<date>.json` mapped to `MorningPrepResponse`; missing file → 200 with empty shortlist (never 500). Use the existing TestClient fixture pattern; set `app.state.reports_dir` to a tmp dir.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** schema + route (read-only; honors `REPORTS_DIR`) + register.
- [ ] **Step 4 — run, expect pass.**
- [ ] **Step 5 — commit** `feat(off-hours): GET /api/morning-prep`.

## Task 11: Next.js Morning Prep tab  [depends on Task 10 contract]

**Files:** Create `dashboard-web/app/morning/page.tsx`, `dashboard-web/components/morning/MorningPrep.tsx`, `dashboard-web/lib/hooks/useMorningPrep.ts`; Modify `dashboard-web/lib/api.ts`, `dashboard-web/lib/types.ts`, the StatusBar/nav. Pattern: `app/paper/page.tsx` + `components/paper/PaperBook.tsx` + `lib/hooks/usePaper.ts`.

- [ ] **Step 1** Add `MorningPrepResponse`/`PrepCandidate` types, `api.morningPrep()`, `useMorningPrep` (fail-quiet), the `/morning` page + component (KPI strip, ranked shortlist table with entry/stop/target/rr/conviction/catalysts, "what changed overnight", plan-for-open). Every row shows a **PLANNED** badge (no entry happens off-hours). Add nav link.
- [ ] **Step 2** `cd dashboard-web; npx tsc --noEmit` → clean.
- [ ] **Step 3 — commit** `feat(off-hours): Morning Prep dashboard tab`.

## Task 12: Scheduling + docs  [serialized — last]

**Files:** Create `scripts/register_off_hours_task.ps1`; Modify `AGENT_STATE.md`, `ROADMAP.md`. Pattern: `scripts/register_learning_task.ps1`.

- [ ] **Step 1** `register_off_hours_task.ps1` registers `TradingBot-OffHoursWatch` running `off-hours-watch` via `.venv\Scripts\python.exe` (read-only; safe unattended). Document activation + the no-auto-entry guarantee in AGENT_STATE; tick ROADMAP.
- [ ] **Step 2 — commit** `chore(off-hours): scheduled-task registration + docs`.

---

## Self-Review

- **Spec coverage:** §3.1 cores → Tasks 1–4; §3.3 orchestration → Task 8; §3.4 phases → Task 8; §4 sinks → Tasks 5/6/10/11; §5 config → Task 7; §6 tests → Tasks 1–5,8,9,10,11 (incl. safety guard Task 8, e2e Task 9). Invariant #1 → Task 8 guard test + Task 5/11 PLANNED labels. All covered.
- **Type consistency:** All tasks reference the single Interface Contract block above. `MorningPrep.to_dict()` shape == spec §4.1.
- **Placeholders:** none — each task names exact files, the pattern file to follow, exact test cases, and commit messages.
