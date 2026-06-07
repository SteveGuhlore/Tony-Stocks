# Agent State / Handoff Log

_Last updated: 2026-06-06_

Use this file so Codex, Claude, Cursor, or any other agent can continue from the same context when the user switches because of usage limits.

---

## 2026-06-07 handoff — Kinetic Tape dashboard: DESIGN LOCKED + Codex-APPROVED, build STARTED

**Branch:** `feat/kinetic-dashboard` (off `main`; legacy frontend tagged `dashboard-web-legacy`).
**Operator mandate:** full autonomy — "don't ask, build in one pass until done, best dashboard ever." Cost-no-object.

### Design is locked & build-ready (do NOT re-litigate)
- Spec: `docs/superpowers/specs/2026-06-07-kinetic-tape-dashboard-design.md`
- Plan (Rev 5, **Codex APPROVED after 5 rounds**): `PLAN.md` · transcript `PLAN-REVIEW-LOG.md`
- **Visual contract = 11 approved HTML mockups** in `.superpowers/brainstorm/9752-1780851075/content/`
  (esp. `08-kinetic-system.html`, `09-enriched-row.html`, `11-symbol-drawer-v2.html`). Their CSS/tokens/SVG
  lift DIRECTLY into code — they ARE the spec. Memory: `project_kinetic_dashboard.md`.
- Theme "Kinetic Tape": Space Grotesk + Space Mono; `#0a0c0b` bg, lime `#c4f042` accent, **cyan `#37e0ff`=BOT**,
  **amber `#ff9e2c`=Tony/2nd-pass**, pos `#46d39a` neg `#ff5d73` warn `#ffce4a`. IA = One Cockpit (morph
  Prep/Live/Review + rail + dual-source slide-over + ⌘K + mobile reflow). Stack: Next16/React19/TS/Tailwind4/
  motion(react)/lightweight-charts/Pixi.js; drop Recharts.

### DONE this session (verified)
- **`src/trading_bot/api/env_fence.py`** — fail-closed money-action fence (Codex #1/#2): money POSTs allowed
  ONLY when `ENV_ROLE=prod` AND live broker account id == `TRADINGBOT_PROD_ACCOUNT_ID`. Pure decision fn +
  best-effort runtime resolver. **8 unit tests** in `tests/test_env_fence.py`.
- **`src/trading_bot/api/schemas.py`** — `CandidateSnapshotRow` extended (additive, Codex #3): current_price,
  research_unrealized_pl_pct, reassessment_label, time_active_minutes, original_entry/stop/target.
- **`src/trading_bot/api/routes/cockpit.py`** — `GET /api/cockpit` aggregate (Codex #6): pure `build_cockpit_rows`
  (snapshots ⋈ subscores ⋈ CC picks ⋈ live price → one symbol view-model) + route; wired in `main.py`. Status
  derivation (near/triggered/watching), distance-to-entry, price_status (live/delayed/unavailable), verdict
  passthrough, NaN coercion. **10 tests** in `tests/test_api_cockpit.py`. (sparkline=[] until `intraday_bars`.)
- **Verified:** env-fence + cockpit + api-smoke + command-center → **all green (29 + 34 runs)**.

### NEXT immediate brick
Chart endpoint + `intraday_bars` SQLite table (Codex #5) → then paper marks (Codex #4) → control endpoints +
cross-process lock/preconditions + fence wiring → personalization tables. THEN frontend (Phase B).

### NEXT (PLAN.md order — Phase A backend, then B frontend, then C gates)
A) remaining backend (additive; verify method names against `storage/repositories.py`):
  - populate the new CandidateSnapshotRow fields in `picks._snap` from repo rows (cols exist in `candidate_snapshots`).
  - **`GET /api/cockpit`** aggregate view-model (Codex #6): one row per symbol = scan score+5 sub-scores+setup+
    levels + tracking live fields + day-change (prices) + Tony verdict+score (command_center) + status + sparkline
    series + RVOL + per-symbol agreement. Read-optimized; every field awaiting-safe.
  - **chart endpoint + new `intraday_bars` SQLite table** (Codex #5, 10-trading-day retention, fed by price-poll/
    watch cycle; daily from stored snapshots; explicit unavailable/stale; NO hot-path yfinance).
  - enrich `/api/paper/positions` with marked-to-live unrealized P/L + protection(OCO) status (Codex #4).
  - **control POST endpoints** (stop-watch, pause/resume-paper, flatten-all/one, re-protect, trigger-scan,
    export-bridge, ack-alert) guarded by `env_fence.assert_money_action_allowed` + PIN + Origin allowlist + nonce
    + idempotency + `action_audit` row + **cross-process lock (shared SQLite advisory lock/lockfile honored by
    API+watch+paper)** + per-action preconditions (trigger-scan 409 if scan running; flatten/re-protect require
    position version match). Personalization tables: pins/notes/presets/journal/call_ratings/price_alerts.
B) frontend: wipe `dashboard-web/` frontend (legacy already tagged), tokens→globals.css+tailwind+lib/tokens.ts,
   signature components (score glyph, plan-rail, sparkline, verdict pill, Pixi universe field) component-first +
   visual-diff vs mockups, data layer (verdict=string normalized once; stale/503 fallbacks; SSE backoff+rehydrate,
   polling=truth), cockpit shell, **virtualized** tape + per-row price store, dual-source drawer, rail views,
   prep/review, wire actions AFTER read-only parity proven.
C) gates: prod-shaped degraded-data E2E (empty CC files/stale watch/503 prices/env drift) + visual-diff
   (gan-design/browser-qa/Playwright) + `tsc`/`next build`/vitest/Playwright green. Deploy: Node 20 LTS on VM,
   `update_vm.sh`, alongside CC, Tailscale + action token + Telegram env.

### Invariants
No scanner/scoring/strategy decision-logic changes (only additive API + minimal watch/paper concurrency hooks).
No new-entry placement from UI. Local dev (ENV_ROLE unset/dev) physically can't trade the VM account.
Scoped `git add` only — NEVER stage `vault/`, `data/`, `logs/` (live data churn in tree).

---

## 2026-06-06 handoff — Off-Hours Research Engine COMPLETE (Tasks 1–12)

**Commit:** `chore(off-hours): scheduled-task registration + docs` on branch `feat/off-hours-research`
**Suite:** All tests from Tasks 1–11 remain green (no code changes in Task 12 — docs/script only).

### What was built (full engine, Tasks 1–12)

The **Off-Hours Research Engine** is a read-only inverse watch loop that runs during weekday
off-hours (16:30→09:00 ET) and weekends. It assembles a ranked, catalyst-aware **Morning Watchlist
+ plan** for the next open. All 12 tasks are committed and green on `feat/off-hours-research`.

**Key components:**
- Window guard (`analytics/off_hours_window.py`) + PreMarket seam (`NullPreMarketProvider`)
- Catalyst enrichment (FMP/Finnhub, budgeted, fail-quiet)
- Morning-prep assembler (`analytics/morning_prep.py`, `build_morning_prep`)
- Four fail-quiet sinks: `reports/morning_prep/<date>.json`, `vault/morning_prep/<date>.md`,
  CC bridge `morning-prep/<date>.md`, `GET /api/morning-prep`
- Next.js `/morning` tab in `dashboard-web/`
- CLI commands: `off-hours-prep` (one-shot) and `off-hours-watch` (inverse loop)
- Scheduled task launcher: `scripts/run_off_hours_watch.cmd` + `scripts/register_off_hours_task.ps1`

### How to activate

1. **Enable in config** — set `off_hours.enabled: true` in `config/default_config.yaml`
   (currently default OFF; the engine is a no-op while disabled).
2. **Register the scheduled task** (runs daily at 16:35 ET, unattended):
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\scripts\register_off_hours_task.ps1
   ```
3. **Or run manually** (one-shot, any time off-hours):
   ```powershell
   $env:PYTHONPATH = "src"
   python -m trading_bot.cli off-hours-prep --config config/default_config.yaml
   ```
4. **Stop the watch loop** at any time by creating `data/STOP_OFF_HOURS` (kill file).

### No-auto-entry guarantee (hard invariant)

The engine **places ZERO trades and fires ZERO orders** during off-hours. This is a hard
architectural invariant, not a config toggle:
- The off-hours code paths contain no imports or calls to `run_paper_cycle`, `paper_engine`,
  `submit_bracket`, or `broker`.
- This is enforced by **`tests/test_off_hours_no_execution.py`** (source-inspection + behavioral
  tests), which will fail the suite if any execution token is ever introduced.
- Entries fire ONLY during market hours (09:30–16:00 ET) via the existing `watch` loop.

### What to do next

- **Merge to main** when ready: `git checkout main && git merge feat/off-hours-research`
  (run `python -m pytest -q` on the branch first to confirm green).
- **Push** when the operator asks (branch is local only).
- **Activate** by following the steps above (attended, after close).
- The Next.js `/morning` tab is wired and ready; it populates once `off-hours-prep` has run
  at least once and `GET /api/morning-prep` returns data.

---

## 2026-06-06 handoff — Task 8 DONE: off-hours-prep + off-hours-watch CLI + no-execution guard

**Commit:** `00d31f9` on branch `feat/off-hours-research`
**Suite:** 1181 passed (up from 1014 baseline; +23 new tests from this task). Zero failures.

### What was built (Task 8 of the Off-Hours Research Engine plan)

**`src/trading_bot/cli.py`** additions:
- `_now_et()` — clock helper extracted for monkeypatching in tests (returns current `America/New_York` datetime)
- `_OFF_HOURS_STOP_FILE` / `_OFF_HOURS_STATE_FILE` — module-level patchable paths for stop file + idempotency state
- `_off_hours_prep_already_run(et_date, phase)` / `_mark_off_hours_prep_run(et_date, phase)` — disk-idempotent `<date>:<phase>` key set (JSON, under `data/`, mirrors `_emit_due_bridges` style)
- `run_off_hours_prep(args)` — full prep orchestration: clock → scan DB rows → catalyst enrichment (FMP/Finnhub, budgeted, degrade gracefully) → OVERNIGHT extras (funnel_eval refresh + load learning_facts) → optional narrative → NullPreMarketProvider seam → `build_morning_prep` → 3 fail-quiet sinks (report json+md, vault note, CC bridge). Returns `{phase, et_date, shortlist_size, sinks_written, errors}`.
- `run_off_hours_watch(args)` — inverse watch loop: MARKET_HOURS → sleep+continue (NO prep); off-hours → prep once per `<date>:<phase>` (idempotent); honors `data/STOP_OFF_HOURS` stop file and `--max-cycles` for testing. Exits 0.
- Subparsers: `off-hours-prep` (`--config --phase --reports-dir --vault-dir --command-center-dir`) and `off-hours-watch` (`--config --max-cycles --cadence-minutes`). Dispatched in `main()`.

**Real scored-row field names and remap written:**
- `candidate_snapshots` table columns: `total_score`, `setup_category`, `planned_entry_price`, `stop`, `target`
- Contract keys expected by `build_morning_prep`: `total_score`, `setup_category`, `planned_entry_price`, `stop_price`, `target_price`
- Remap applied in `run_off_hours_prep`: `stop → stop_price`, `target → target_price`; `total_score`, `setup_category`, `planned_entry_price` pass through unchanged

**Optional reuse wired vs skipped:**
- WIRED: `ScannerRepository.list_candidate_snapshots` (DB scan rows), `FmpProvider.earnings_calendar`, `FinnhubProvider.recommendation`, `build_catalyst_tags`, `build_morning_prep`, `write_morning_prep_{report,note,bridge}`, `_refresh_funnel_eval_for_learning` (for OVERNIGHT phase), `NullPreMarketProvider` seam
- SKIPPED (risky/unclear): `run_learn` full invocation (circular scope risk; learning_facts loaded from JSON instead), tony-divergence/calibration calls (out of scope — the plan marks these as optional for OVERNIGHT), narrative wiring (coded with LLM gate but left minimal to avoid key dependency in tests)

**Safety guard (hard invariant):**
- `inspect.getsource(run_off_hours_prep)` and `inspect.getsource(run_off_hours_watch)` contain ZERO occurrences of: `run_paper_cycle`, `paper_engine`, `submit_bracket`, `broker` — tested by `test_off_hours_no_execution.py::TestNoExecutionTokens` (8 tests, all pass)

**Test files:**
- `tests/test_off_hours_cli.py` — 10 tests: happy-path (returns dict, writes JSON, et_date, phase_override, sinks_written list, shortlist_size) + fail-quiet (sink raises → no exception, error recorded, multi-sink all-fail)
- `tests/test_off_hours_no_execution.py` — 13 tests: 8 source-inspection guards + 5 watch-loop behavioral (MARKET_HOURS no-prep, PRE_OPEN calls prep, exit via max_cycles, stop file halts, idempotency prevents double-prep)

### Remaining tasks in the Off-Hours Research Engine plan
Tasks 1–7 (analytics modules, sinks) were already committed on `feat/off-hours-research` prior to this session. Task 8 (this task) is now done. Tasks 9–12 (API endpoint, Next.js `/morning` tab, full E2E, merge) remain.

### How to execute next tasks
- `git checkout feat/off-hours-research` (already on this branch)
- Run `python -m pytest -q` to confirm green (1181 passed)
- Continue with Task 9: `GET /api/morning-prep` FastAPI endpoint
- **Scoped git add only** — never stage `vault/`, `data/`, `logs/` (live data)

---

## 2026-06-06 handoff — main merge + 3 shipped items; OFF-HOURS ENGINE planned, NOT built (next task)

**TL;DR:** `feat/divergence-calibration` was **merged to main** (985 tests verified green first). Then three
independent backlog items shipped and were merged into branch **`feat/off-hours-research`** (off main).
The big new initiative — the **Off-Hours Research Engine** — has a committed **design spec + 12-task
interface-locked implementation plan but ZERO implementation code yet**. That is the next session's job
(GateGuard is now OFF user-wide, so agents can run unthrottled by the fact-forcing gate). Nothing pushed.

### What is DONE and committed on `feat/off-hours-research`
1. **main = `a963419`** (divergence-calibration fast-forward merged; 985 green at merge time).
2. **Tier-3 contract-drift guard** (merge `0768b12`) — `tests/test_contract_drift.py`, **18 tests**.
   Freezes the 5 bot↔CC schemas (outcomes JSON, bridge markdown sections, verdicts JSON, record JSON,
   divergence teaching-log) with explicit `contract: key X ...` drift messages. **Honest gap found:**
   `docs/CONTRACTS/self-learning-bridge.md` documents a `learning/<date>.md` brief with NO producer in
   code — that contract is unimplemented (backlog it; not a blocker).
3. **Equity-curve fairness** (merge `ff78cb0`) — `analytics/equity_curve.py` + `api/routes/paper.py`,
   **16 tests**. `build_paper_equity_curve` now accepts `open_positions` + injected `live_prices` and folds
   open-position unrealized P/L into the LATEST point only (mark-to-live for a fair head-to-head with the
   CC). Fail-quiet: no keys / market closed / `live_prices` None → byte-identical realized-only. Pure core
   (prices injected, no network). Display-only; no orders.
4. **Nightly funnel-eval wiring** (merge `f468440`) — `cli.py` + `scripts/run_nightly_learning.cmd`,
   **37 tests**. Fixed a real path-mismatch bug: the learner reads `reports/funnel_eval.json` but
   `funnel-eval --save-report` wrote `reports/<date>/funnel_eval.json`. `run_learn` now refreshes
   `reports/funnel_eval.json` (fail-quiet) before reading it; the 1:30am task runs `funnel-eval` then `learn`.
   Broken/missing funnel_eval.json → learner returns rc 0 (covered by test).

> **Verification status:** B/C/D each ran their own suites green (18/16/37), AND the FULL integrated suite
> after all three merges is **GREEN: 1014 passed** (up from the 985 pre-merge baseline; 1 harmless websockets
> deprecation warning). Confirmed `scripts\run_tests.ps1` at handoff. Safe to build on top.

### THE NEXT TASK — build the Off-Hours Research Engine
- **Spec:** `docs/superpowers/specs/2026-06-06-off-hours-research-engine-design.md`
- **Plan (execute this):** `docs/superpowers/plans/2026-06-06-off-hours-research-engine.md` — 12 TDD tasks,
  fully interface-locked (the Interface Contract block is the cross-task glue; do NOT rename fields).
- **What it is:** a read-only off-hours engine (weekdays 16:30→09:00 ET + weekends) that prepares a ranked,
  catalyst-aware, recalibrated **Morning Watchlist + plan** for the next open. Inverse-watch loop
  (`off-hours-watch`) + one-shot `off-hours-prep` CLI. Four fail-quiet sinks: `reports/morning_prep/<date>.json`,
  `vault/morning_prep/<date>.md`, CC bridge `morning-prep/<date>.md`, and `GET /api/morning-prep` + a Next.js
  `/morning` tab. Pluggable pre-market provider seam stubbed (NullPreMarketProvider now).
- **HARD INVARIANT #1 — no off-hours auto-entry, EVER.** The engine prepares plans only; it must never
  import/call the paper engine, broker, or order submission. Task 8 has a guard test enforcing this. Entries
  fire ONLY during market hours via the existing live watch loop. (This was the operator's explicit
  requirement: paper trades auto-enter, and off-hours it legit can't / with real money it can't.)
- **Verified column-name note for the executor:** `candidate_snapshots` exposes `total_score` (0–100, divide
  by 100 for the 0–1 conviction bands), `setup_category`, `planned_entry_price`, and `stop`/`target` (NOT the
  `stop_price`/`target_price` suffixes used as placeholders in the plan contract). Map to the real names; keep
  the public dataclass field names from the contract. Confirm against `storage/repositories.py`.
- **How to execute (next session, GateGuard now off):** `git checkout feat/off-hours-research`; run the full
  suite to confirm green; then execute the plan task-by-task with TDD (subagent-driven-development is ideal
  now that the fact-forcing gate is off). Scoped `git add` ONLY — the working tree has ~128 modified
  `vault/*.md` + ~89 untracked LIVE-DATA files that must NEVER be staged (`git add <specific paths>`, never
  `-A`/`.`/`vault/`). When green end-to-end (incl. `cd dashboard-web; npx tsc --noEmit`), merge
  `feat/off-hours-research` → main.

### Housekeeping / loose ends
- **Stale worktrees to prune** (already merged): `git worktree remove` the three under
  `.claude/worktrees/agent-a222f2554d9727518`, `agent-a226cb8b01b516c5c`, `agent-a38ebdcbdab1f79de`
  (branches `worktree-agent-*`). Agent A's research-only run wrote no code (nothing to recover).
- **GateGuard:** now disabled user-wide via `~/.claude/settings.json` `env.ECC_GATEGUARD=off`. NOTE this does
  NOT disable the separate harness-level **cost-warning hook** (that is what made one background agent pause
  mid-task last session) — be aware sub-agents may still pause on cost.
- **Nothing pushed.** main is ahead of origin by the divergence-calibration merge; `feat/off-hours-research`
  is local only. Push only when the operator asks.
- Backlog to add: the unimplemented `self-learning-bridge.md` `learning/<date>.md` producer (found by the
  contract-drift guard).

---

## 2026-06-05 handoff — Divergence Calibration (V44 vein) + B1 control-parity guards

**TL;DR:** Shipped **divergence calibration** — the Tony-vs-bot divergence ledger now feeds a
**human-gated, two-key, bounded retune** of the 5 scanner weights. Plus **B1** control-parity
guards. Branch `feat/divergence-calibration`. **Full suite green (950+); 49 calibration/activation
+ 5 B1 tests.** Three specialist review agents (python/security/silent-failure) audited it; the
real CRITICAL (`apply_nudge` bound math) is fixed + stress-tested (30 degenerate cases).

### What it does (spec: `docs/superpowers/specs/2026-06-05-divergence-calibration-design.md`)
- **Pure core** `analytics/divergence_calibration.py`: per-component outcome **attribution**
  (does a sub-score separate winners from losers?) AND per-cohort **divergence confirmation**
  (did Tony correctly override the cohort that sub-score inflates?). A weight nudge fires only
  when **both agree**; ≤3 weight-pts, clamped [0.05,0.50], renormalized to 1.0, sample-gated.
- **Key 1 (approve):** proposals ride the existing `approval_package.json` `suggestions` list
  (kind=`weight_calibration` + `new_weights`); `record-suggestion-decision` records approval
  unchanged (records ≠ applies).
- **Key 2 (apply):** new CLI **`activate-strategy-version`** — the SOLE path that writes live
  weights into `config/scoring_config.yaml`; refuses without an approved proposal; validates the
  payload (sum≈1.0, 5 keys, bounds) before writing; `--revert`; writes provenance
  `config/strategy_versions/vNN.yaml` + appends `reports/strategy_versions.json`.
- **Join:** `repositories.list_snapshot_subscores` (candidate_snapshots ⋈ scan_results on
  scan_run_id+symbol) recovers sub-scores; `cli._load_pick_records` joins to outcomes on
  `(symbol, pick_date)`. **Smoke on real data: picks=50, dropped=0** (date-alignment validated).
- Wired into `after-market-review` (defensive — never breaks the review). Today it correctly
  prints "No calibration yet — evidence has not converged."

### How to use
1. `after-market-review` surfaces weight proposals when the ledger converges.
2. `record-suggestion-decision --index N --status approved` (Key 1).
3. `activate-strategy-version [--key <suggestion_key>]` (Key 2) → live weights. `--revert` to undo.

### B1 (execution-parity contract) — `docs/CONTRACTS/execution-parity.md` v1.1 §B.1
B1 = conviction-scaled Tony vs flat-1% bot. Bot-side guards locked by `tests/test_b1_control_parity.py`:
(1) `order_router.size_position` has NO conviction term (bot stays flat-1% control);
(2) `record.json` ingestion tolerates an additive `sizing_attribution` key (ignored, never rejected);
(3) contract amended to require picking-alpha vs sizing-alpha reporting before the gate is flipped on.

### Follow-ups (deliberately out of scope)
- Tier-3 contract-drift test guard (freeze bridge/verdict/record schemas).
- Reviewer notes declined as out-of-threat-model for a local single-operator tool (path-root
  assertions would break tmp_path tests; suggestion_key→weights binding) — payload validation
  covers the real corruption risk. Calibrate thresholds/sectors later.

---

## 2026-06-05 handoff — REAL two-layer tandem-loop test (bot <-> live CC code)

**TL;DR:** New harness `scripts/tandem_loop_test.py` proves the whole layer-1 (bot) <->
layer-2 (Command Center) loop end to end against the **REAL CC runner code** (not synthetic
JSON), in one shared throwaway sandbox. **25/25 checks pass** incl. the full **926-test**
pytest suite, live Gemini narration, and a hard guarantee that **neither live system is
touched** (real bot reports/DB/vault AND the real CC workspace are byte-for-byte unchanged
before/after). Read-only on trading; no orders. Uncommitted (1 new file + AGENT_STATE).

### What it actually exercises (the operator's ask: "nothing breaks during live hours")
- **Layer 1 (bot)** seeds snapshots -> `emit-outcomes` -> writes the daily anchor bridge +
  4 intraday handoffs (10:30/13:00/15:30/eod) into the sandbox CC bridge dir.
- **Layer 2 (REAL CC)** — imports and drives the actual Command Center code:
  `runner.bridge.tony_bridge.scan_and_process()` ingests every handoff and spawns one Tony
  deep-dive task per bridge (idempotent on re-run); `runner.tools.tony_verdict.write_tony_verdict`
  writes 2nd-pass verdicts (all 5 enums incl. `close`; bracket-validity guard verified);
  `runner.ledger.tony_scorecard.write_record()` grades the bot's outcomes -> `record.json`;
  `tony_outcomes.get_tony_outcomes()` track record.
- **Back to layer 1** the bot consumes the CC's REAL outputs: `cc_exit_symbols` detects the
  `close`, `tony-divergence` builds the teaching ledger (4 contract keys), and the
  `/api/command-center` mappers (`build_record/build_agreement/build_picks`) accept the CC
  record+verdicts (the head-to-head panel render path). Round-trip continuity asserted.
- **Nightly handoff** `learn` deterministic + a LIVE Gemini pass.

### How isolation is guaranteed (zero corruption)
- Bot: sandbox config redirects `database_path` + vault dirs + `command_center_dir`; demo
  guards flipped so synthetic data is recognized.
- CC: env (`TONY_*_FILE`/`TONY_BRIDGE_DIR`/`TONY_REPORTS_DIR`, read at CC import time) is set
  BEFORE importing `runner.*`, AND the non-env CC globals that point at the real workspace
  (`tony_bridge.TASKS_DIR`/`VAULT_DIR`/`_PROCESSED_LOG`/`BRIDGE_MD_DIR`/`TRADING_REPORTS_DIR`)
  are monkeypatched to the sandbox after import.
- Phase 9 fingerprints (sha256) the real bot sinks + the real CC bridge/tasks/processed-log/
  record/signal-ledger before and after; the run FAILS if any byte changed. (Confirmed clean.)

### The two fixes from the prior unfinished session
1. **`.env`/LLM key passthrough** — the harness now parses both bot + CC `.env` files and
   injects the LLM keys into the subprocess env (and os.environ for in-proc CC). bot
   `GEMINI_API_KEY` wins; also aliased to `GOOGLE_API_KEY` for google-genai.
2. **Interpreter mismatch (root cause of the old fallback)** — the harness drives bot
   subprocesses with `.venv\Scripts\python.exe` (what the nightly scheduled task uses); that
   venv has `google-genai`. A bare `python` does NOT, which is why live narration fell back
   before. Now `llm=on (gemini-2.5-flash)`.

### Run it
`$env:PYTHONPATH="src"; python scripts/tandem_loop_test.py` (full, ~5 min incl. pytest).
`--quick` skips the suite (~30s loop only); `--no-live-llm` skips the paid Gemini pass.

### One honest caveat (minor, tracked)
The seeded **demo** data was too thin to tier any `[[SYM]]` Tier-1 names into the bridge, so
the verdict round-trip used a fixed symbol set (NVDA/AMD/AAPL/MSFT/AVGO/BA) rather than
bot-extracted symbols. The CC ingested the real bot bridges fine (parsed all 4, spawned
tasks); only the *specific* verdicted symbols were the fallback. During live hours the bridge
WILL carry Tier-1 wikilinks, so the bot-origin link is exercised then. If desired, enrich the
sandbox seed (or copy a recent real bridge's body) so Tier-1 extraction yields real symbols.

---

## 2026-06-04 (late session) handoff — Nightly self-learning loop SHIPPED + Paper Trades tab

**TL;DR:** On branch `feat/nightly-self-learning` (off `main`). Two things shipped, both
**read-only on trading** (no orders, no config/threshold/risk edits, no watch restart).
Full suite **922 passed**. NOT merged, NOT pushed, no scheduled task registered yet.

### 1. Nightly self-learning "brain" (the big one)
A nightly loop that grades the bot's own resolved trades, evolves a knowledge base, and
teaches both the dashboard and the Command Center. Design spec
`docs/superpowers/specs/2026-06-04-nightly-self-learning-design.md`, plan
`docs/superpowers/plans/2026-06-04-nightly-self-learning.md`.
- **`analytics/nightly_learning.py`** (pure) — `build_nightly_facts` across 9 dimensions
  (setup edge, sector signal+streaks, score calibration, R-multiple/expectancy, hold-time,
  exit mix, regime/streak, funnel value, Tony divergence), all sample-size gated.
- **`analytics/learning_knowledge.py`** (pure) — `update_knowledge`: a living `KnowledgeBase`
  that promotes/demotes claims on CUMULATIVE evidence + week-over-week trend; idempotent
  per-date history. This is the "evolve" — lessons compound, don't reset.
- **`analytics/learning_narrator.py`** — Claude (`claude-sonnet-4-6`) writes the prose from
  VERIFIED facts only (never raw rows); falls back to deterministic templates on any error
  or missing `ANTHROPIC_API_KEY`, so the run never fails on the LLM.
- **Sinks:** `vault/learning/<date>.md` + `vault/learning/_knowledge.md` (Obsidian memory),
  `reports/agent_insights.json` (dashboard mailbox, via `agent_bridge.record_agent_insights_batch`,
  deduped), and the CC bridge `{cc}/bridge/tony-stocks/learning/<date>.md` (contract:
  `docs/CONTRACTS/self-learning-bridge.md`). `vault/learning_writer.py`.
- **CLI:** `python -m trading_bot.cli learn --config config/default_config.yaml`
  (`--date --min-sample --no-llm --no-bridge --reports-dir --vault-dir --command-center-dir`).
  `run_learn` is fail-quiet per sink → always exits 0. Config block `learning:` in
  `default_config.yaml` (+ `ScannerSettings.learning`).
- **Tests:** `test_nightly_learning` (18), `test_learning_knowledge` (4), `test_learning_narrator`
  (4), `test_learning_writer` (3), `test_agent_bridge_batch` (1), `test_learning_config` (2),
  `test_learning_cli` (2), `test_learning_e2e` (2 — full tandem incl. evolution + CC bytes).

**To activate (attended):**
1. `powershell -ExecutionPolicy Bypass -File .\scripts\register_learning_task.ps1` → registers
   the `TradingBot-NightlyLearning` task at 1:30am (before CC's 2am). Read-only → safe unattended.
2. Ensure `ANTHROPIC_API_KEY` in `.env` for the LLM narrative (else clean template fallback).
3. **CC-side (their workspace, NOT this repo):** point the CC self-learning script at
   `{cc}/bridge/tony-stocks/learning/` — same wiring pattern as `TONY_OUTCOMES_FILE`.
4. Dress rehearsal anytime (throwaway temp sandbox): `.\scripts\mock_learning_e2e.ps1`.

### 2. Paper Trades dashboard tab
New `/paper` tab in `dashboard-web` (StatusBar nav) — full mirror of the CC reference:
KPI strip, head-to-head equity curve, OPEN positions table (live LAST + live $/% P/L via
`useLivePrices`), CLOSED trades table. `components/paper/PaperBook.tsx` + `app/paper/page.tsx`.
tsc clean, verified live (31 open positions render). These paper-tab files are uncommitted on
the working tree — commit separately if desired.

### Tandem with CC (from operator's CC update this session)
- CC's learning is wired via its runner's daily hook + a "Flash can't strip Tony's guardrails"
  safety net. Our bot learner is INDEPENDENT and feeds CC one-way through the bridge file — no
  collision; pure separation holds.
- **OPEN tandem item — head-to-head fairness:** CC now `mark_live()`s its Paper Book + equity
  curve to live prices. The bot's `/api/paper/equity-curve` is still realized-only, so the
  head-to-head is asymmetric (our open winners/losers aren't marked). **Next task:** mark the
  bot's open positions to live in the equity curve's latest point for symmetry. Tracked in
  `KNOWN_BACKLOG.md`.

---

## 2026-06-04 (evening session) handoff — roadmap items 1–4 shipped (funnel scaling, ET-date lock, funnel eval, Tony teaching)

**TL;DR:** Executed `docs/superpowers/specs/2026-06-04-remaining-roadmap-plan.md` items 1–4 on branch
`feat/remaining-roadmap-2026-06-04` (off `main`). Full suite green after each. **NOT merged to main, NOT
pushed, live watch loop NOT restarted** — all changes are code/config/tests/docs only and won't affect the
running PID until an attended restart. **Item 7 (paper-trade dashboard) is the only remaining roadmap item.**

### What shipped (commits on the feature branch)
1. **Item 1 — Funnel enrichment scaling** (`686443a`). `RecommendationCache` (`reports/finnhub_reco_cache.json`,
   daily-keyed `{SYMBOL:{score,fetched_date}}`) + `enrich_per_run` per-cycle budget so the funnel ranks the
   WHOLE universe over a few cycles without bursting Finnhub's free ~60/min tier. `gather_funnel_signals` is
   cache-aware (fresh = free, stale/missing fetched up to budget); `warm_recommendation_cache` runs each watch
   cycle (wired into `run_watch`). Config: `enrich_per_run: 50`, `reco_cache_ttl_days: 1`.
2. **Item 2 — Scan-coverage ET-date** (`686443a`). The coverage builder already buckets after-hours scans by
   ET via `market_date_mask` (V16A); locked with `tests/test_scan_coverage_et_date.py`. Dormant
   `count_paper_orders_today` UTC/ET edge noted in `KNOWN_BACKLOG.md` (only bites in extended hours — gated off).
3. **Item 3 — Funnel evaluation harness** (`4e5972b`). `analytics/funnel_eval.py` (pure) + `funnel-eval` CLI:
   per stage, win-rate/avg-R of KEPT vs DROPPED names over stored outcomes → helps/hurts/neutral/insufficient.
   Live run: 46 picks, all stages `insufficient_data` (picks only exist for funnel survivors — honest).
4. **Item 4 — Tony teaching / divergence** (pending commit this session). `analytics/tony_divergence.py` (pure)
   + `tony-divergence` CLI → `reports/tony_teaching_log.json`. Joins `tony_stocks_verdicts.json` ×
   `tony_stocks_outcomes.json` on (symbol, pick_date), classifies agreed_right/wrong + cc_overrode_saved/missed
   + pending, reasoning verbatim. `/api/command-center` agreement block now **falls back to this ledger** when
   the CC record lacks one (`build_agreement_from_teaching`). Live run: 10 verdicts × 46 outcomes → all pending
   (verdict dates 06-03/04 vs resolved outcomes 05-18→05-22, so none join yet — they grade as outcomes resolve).

### New CLIs
`funnel-eval [--days N --min-sample N --save-report]`, `tony-divergence` (both research-only, read-only except
writing their report/ledger JSON).

### To activate on the live loop (after close, attended)
A watch restart picks up Item 1 (reco cache + per-cycle warming). Same restart caveat as prior handoffs (it
emits due bridges at the top before the market guard). Merge the branch to `main` first (or run from the
branch). Nothing forces a restart — Item 1 only changes behavior on the next `run_watch`.

### Item 7 — paper-trade dashboard surface (SHIPPED this session, frontend committed `46e8d14`)
- **Backend** (`f...`): `analytics/equity_curve.py` (pure `build_paper_equity_curve`, realized series indexed
  to 100) + `GET /api/paper/equity-curve?base_equity=100000`. Tests in `test_equity_curve.py` + api smoke.
- **Frontend** (Next.js 16, tsc clean, verified live in the running :3000 dashboard):
  - Board: amber **PAPER** badge on held symbols + real fill-based P/L (verified: FITB/C/PINS/GLW/SLB).
  - StatusBar: account chip ("Trading Bot 31 open · realized").
  - `/record`: **HeadToHeadEquity** chart — bot (amber) vs Tony (cyan), each indexed to 100, baseline at
    100, legend with each side's % return, "Collecting…" until ≥2 points.
  - SymbolDrawer: bot paper-position section (fill/qty/opened/stop/target/live P/L) vs the planned entry.
  - `lib/hooks/usePaper.ts` (usePaper + usePaperEquityCurve, fail-quiet), api + Paper* types.
- **Equity-curve model (operator decision):** each side publishes its OWN normalized series; either dashboard
  overlays both. Bot publishes `/api/paper/equity-curve`. **To light up the curve with data:** (1) restart the
  API on :8001 so the new endpoint exists (currently 404s → graceful "Collecting…"); (2) need ≥2 closed paper
  trades. **CC side (coordinate):** have the Command Center expose/keep its Tony series (it already builds
  `equity-history.json` / `/api/tony/equity-curve`); the bot dashboard reads Tony's series from
  `command-center record.equity_curve`.

### Still open
- Roadmap item 6 (auto-universe growth — FMP screener is paid): **operator decision**, no code until a path is picked.
- Restart API :8001 (attended) to expose `/api/paper/equity-curve`. Restart watch loop (attended, after close) to
  activate Item 1's reco cache + per-cycle warming. Neither is forced.

---

## 2026-06-03 handoff — Two-agent paper trading is LIVE (read this first)

**TL;DR:** The full bot↔Command-Center two-agent paper-trading loop is **live and trading end-to-end**:
bot scan → corrected bridge → CC ingests → Tony deep-dive → verdicts → Alpaca fills. Two independent
paper books graded against the same outcomes (the "does the 2nd pass help?" experiment). All code is
committed + pushed to `origin/main` (github.com/SteveGuhlore/Tony-Stocks).

### ⚠️ Live processes running right now — do NOT disrupt during market hours
Launched detached (Start-Process, hidden) on this Windows machine; they persist while the device is
awake but **do not auto-restart** if it sleeps or a process dies.
- **Bot watch loop** (`python -m trading_bot.cli watch`) — scanning/trading/bridging. Log: `logs/watch_live2.err`.
- **FastAPI backend** on **:8001** (`uvicorn trading_bot.api.main:app`) — serves the dashboard. Log:
  `logs/api.err`. (Dropped once mid-session; relaunch if down — read-only, no trading impact.)
- **Next.js dashboard** on **:3000** (`npm run dev` in `dashboard-web`). Log: `logs/web.err`.
- Kill switches: `data/STOP_WATCH_MODE` (stops watch), `data/STOP_PAPER_TRADING` (pauses paper trades).
- **OPERATING RULE: market hours (09:30–16:00 ET) = watch only, NO code changes/restarts.** Make code
  changes after the 16:00 ET close so a mistake can't hit a live order.

### Accounts + config (real money posture intact)
- **TWO SEPARATE Alpaca paper accounts, never shared keys:** bot = **`PA3P0RN75VL1`** (.env `ALPACA_API_KEY`
  prefix `PKU74F…`); CC's Tony = the **$1M** account (key `…K5ZP`). `load_dotenv` uses setdefault — keys
  come cleanly from `.env` (no OS-env shadowing).
- `config/default_config.yaml`: `live_trading_enabled: false` (stays false). `paper_trading.enabled: true`,
  `close_on_command_center_exit: false` (**PURE SEPARATION** — bot ignores Tony's verdicts on its own book),
  `account_label: "Trading Bot"`, rotation `max_symbols_per_cycle/rotating_bucket_size: 350` (scans ~full
  universe each cycle).

### File contract between the two terminals
| File / path | Owner | Purpose |
|---|---|---|
| `…/AI Operations Command Center/bridge/tony-stocks/YYYY-MM-DD.md` | bot writes | daily deep-dive anchor |
| `…/bridge/tony-stocks/YYYY-MM-DDTHHMM.md` | bot writes | intraday light updates |
| `reports/tony_stocks_outcomes.json` | bot writes | resolved outcomes (join on `pick_date`+`resolved_date`) — CC grades |
| `reports/tony_stocks_verdicts.json` | **CC writes** | bot reads (records only — pure separation) |
| `reports/tony_stocks_record.json` | **CC writes** | bot dashboard will read (has real graded data now) |

### What this session shipped (all committed on `main`)
Outcomes emitter + resolved-outcomes assembly; test-suite repair (removed dead Streamlit `dashboard`
tests); **paper-trading subsystem (6 phases)** = config (`execution/paper_config.py`), pure order router
(`order_router.py`), broker (`broker.py` FakeBroker + `alpaca_paper.py` AlpacaPaperBroker), storage
(`paper_orders`/`paper_positions` + repo methods), engine + watch wiring (`paper_engine.py`,
`run_paper_cycle`), API + CLIs; CC-verdict reader (`cc_verdicts.py`, pure-separation); intraday bridges +
daily-anchor automation; and the **bridge-export fix** — the export was decoupled from the live scan/book,
now wired to real Universe/Scored counts, live `current_price`, triggered flags, and real carry-over;
`update-snapshots` per-cycle limit 500→120 for cadence.

### CLIs
`watch`, `export-to-vault [--slot 1030|1300|1530|eod]`, `emit-outcomes`, `paper-status`,
`paper-flatten` (kill switch — close all), `paper-check [--test-order SYM]`.

### How to verify (read-only, safe anytime)
- Bot book: `python -m trading_bot.cli paper-status` or `GET http://127.0.0.1:8001/api/paper/positions`.
- Dashboard: `http://localhost:3000`. Watch: latest `watch_runs` heartbeat / `logs/watch_live2.err`.
- Bridges: `…/bridge/tony-stocks/2026-06-03*.md`.

### Update (2026-06-03, later same-day session) — item 1 SHIPPED
- **`GET /api/command-center` endpoint is built, tested, and LIVE.** New route
  `src/trading_bot/api/routes/command_center.py` (pure mappers `build_picks/build_record/build_agreement`
  + the route); schemas added to `api/schemas.py` (`CommandCenter*`); registered in `api/main.py`
  (+ `app.state.reports_dir`, env `REPORTS_DIR`). Reads `reports/tony_stocks_verdicts.json` (override
  `TONY_VERDICTS_FILE`) + `tony_stocks_record.json` (override `TONY_RECORD_FILE`); never writes.
  Three contract bridges: `tony_win_rate` 0–100 → 0–1 fraction; agreement `override_saved/missed` →
  `cc_overrode_saved/missed`; `verdict` passed through **verbatim** so non-enum values (e.g. `"pass"`)
  survive (frontend degrades unknowns to "⋯ awaiting"). Missing/malformed files → empty/None (no errors).
  Tests: `tests/test_api_command_center.py` (11 passing); full suite **788 passed**.
- **API `:8001` was restarted** (old PID 23388 → new PID 30828) so the route loads — uvicorn has no
  `--reload`. Watch loop (PIDs 11672/25684) and frontend `:3000` were **not** touched. Live check:
  `GET /api/command-center` → 200, 7 picks (DAL/DXCM/MARA/CRM/HOOD/D/PATH), win_rate 0.333,
  cc_overrode 2/4. The "TONY STOCKS" panel / "2nd pass help?" matrix / head-to-head equity now populate.
- **Follow-up (optional, not blocking):** Tony's `"pass"` verdict renders as a muted "⋯ awaiting" chip
  (score + reasoning still show). To make the chip honest, add a `"pass"` entry to `dashboard-web/lib/signal.ts`
  `VERDICTS` + the `VerdictKind` union (frontend-only). `equity_curve`/`avg_pl_per_trade`/`target_hits`/
  `stop_hits` stay null until CC writes them into `record.json`.

### Update 2 (2026-06-04 early, after close) — EOD bridge fix + universe expansion SHIPPED
**All changes are code/config only and verified green (full suite 789 passed). NOT YET ACTIVATED on
the live watch loop — see "Activation" below.**

1. **EOD (16:00) bridge handoff was silently never firing — FIXED.** Root cause: the auto 16:00
   checkpoint was labelled `"eod"`, which writes the canonical daily filename `YYYY-MM-DD.md` — the
   SAME file the morning daily-anchor already created — so the disk-idempotency guard
   (`bridge_file.exists()` in `cli._emit_due_bridges`) skipped it every day. Fix: relabel the auto
   checkpoint `"eod"` → `"1600"` in `vault/bridge_schedule.py` so it writes a timestamped
   `YYYY-MM-DDT1600.md` (intraday-style) that never collides and the CC reliably ingests. Manual
   `export-to-vault --slot eod` and the daily anchor keep canonical-daily semantics. Tests updated:
   `tests/test_bridge_schedule.py` (29 pass), incl. a regression locking the 1600 timestamped name.
2. **Universe expanded 349 → 548** (requested: "scan more stocks as data grows"). Added 199 curated
   liquid US names across all sectors via `scripts/expand_universe.py` (idempotent generator; auto-dedups;
   reloads+validates YAML) as `primary_candidate`/`speculative_candidate` with NO `watchlist_core` tag,
   so they feed the rotating **discovery** pool (not forced core). **Critical coupling fixed:**
   `config/universe_swing_research_config.yaml` `filters.max_universe_size` 350 → **600** — without this,
   `data/universe.load_universe()` truncates `result[:max_universe_size]` and the new names are silently
   dropped. `tests/test_universe.py` budget test now reads the cap from config (no more hardcoded 350).
   Per-cycle scan stays bounded by `watch_universe_rotation.max_symbols_per_cycle: 350`, so rate-limit
   load is unchanged — rotation just covers 548 over ~1.6 cycles. Live loader confirmed: 548.

**Activation (NOT done — deliberately left for an attended pre-open restart):** the live watch loop
(PIDs 11672/25684) still has the OLD config in memory (349 universe, "eod" slot). A restart picks up
both changes. I did NOT restart it unattended tonight because: (a) on restart the loop runs
`_emit_due_bridges` at the top BEFORE the market guard, and since all of today's checkpoints have passed,
it would immediately emit today's `2026-06-03T1600.md` — which would trigger the CC agent to (possibly)
place after-hours orders on its $1M book; (b) restarting a money-adjacent loop unattended at night is an
outward-facing action worth doing attended. **To activate (recommended tomorrow before 09:30 ET):**
`data/STOP_WATCH_MODE` to stop the old loop (or kill PIDs 11672/25684), then relaunch:
`$env:PYTHONPATH="src"; python -m trading_bot.cli watch --config config/default_config.yaml`. First
restart will also deliver today's missed 1600 EOD handoff to Tony (expected/benign).

**Not committed.** On `main` with heavy live vault/*.md churn in the tree. Files to commit (scoped):
`src/trading_bot/api/routes/command_center.py`, `api/schemas.py`, `api/main.py`,
`tests/test_api_command_center.py`, `vault/bridge_schedule.py`, `tests/test_bridge_schedule.py`,
`scripts/expand_universe.py`, `config/universe_swing_research_config.yaml`, `tests/test_universe.py`,
`ROADMAP.md`, `AGENT_STATE.md`. Branch off main first.

### Update 4 (2026-06-04 ~17:40 ET, after close) — Funnel LIVE + execution-parity contract
> **NEXT SESSION:** execute `docs/superpowers/specs/2026-06-04-remaining-roadmap-plan.md` — all remaining
> roadmap items in one clean pass (funnel enrichment scaling → ET-date fix → funnel eval harness → Tony
> teaching layer → universe-growth decision → **paper-trade dashboard LAST**). Sizing is now matched 1%
> of each account: **bot $1k / CC $10k**. Bot sizing live as `max_notional_per_position: 1000`.
- **Research Funnel is ENABLED and live on the watch loop** (PID 35116, relaunched after close with
  `PYTHONUNBUFFERED=1` so logs stream). Verified at startup: `universe 543 → 542 shortlist (dropped 1:
  DOCU earnings-blackout)`, rotator now pulls from the funnel shortlist. Config: `enabled:true`,
  `use_news_sentiment:false` (Finnhub news-sentiment is premium/403), `earnings_blackout_days:5`,
  `sentiment_mode:annotate`, rank by analyst recommendation. Fail-safe (errors → pre-screened universe).
- **API keys (live-tested):** Twelve Data ✅, Finnhub recommendation ✅, FMP earnings + revenue-growth ✅
  (FMP fixed to `/stable` API — `/v3` 403s). **Premium/paid gaps:** Finnhub news-sentiment (403),
  FMP company-screener (402 — this is the auto-universe-growth engine; needs a paid FMP plan).
- **⚠️ Finnhub 429 rate-limit:** the funnel's per-symbol recommendation calls burst past the free
  ~60/min tier. Mitigation applied: `enrich_limit` 150→**50** (the RUNNING loop still has 150 in memory;
  next restart picks up 50). Proper fix (follow-up): add pacing/rate-limiting to the Finnhub calls so
  larger enrich_limits don't 429. Funnel degrades gracefully meanwhile (rate-limited → no score, advisory).
- **Execution-parity contract:** `docs/CONTRACTS/execution-parity.md` — what bot+CC must share
  (risk%, sizing formula, caps, GTC bracket, candidate set, one grading harness; compare via equity
  normalized to 100) vs differentiate (reasoning/tools/decision/level-adjustments). **Action item: verify
  the CC's risk%/caps match Section A — lives in the Command Center workspace, not this repo.**
- Commits on `main`: `0fd465d` (FMP /stable + verify script), `ab038be` (funnel enable + parity contract),
  plus the enrich_limit→50 tweak (pending commit). Full suite 824 passed.

### Update 3 (2026-06-04 pre-open) — Research Funnel v2 + GTC bracket-protection fix
**Full suite 820 passed. Watch loop restarted pre-open so the GTC fix is live for today.**

1. **Research Funnel v2 implemented (DEFAULT OFF).** Pure staging core `data/research_funnel.py`
   (`build_funnel` + `SymbolSignals` + `FunnelStageConfig` + `FunnelResult`; cheap screen → catalyst →
   rank/shortlist; advisory-by-default so a missing/failed API never drops a symbol; `always_include`
   protects core/open names). Provider adapters `data/research_providers.py` (`FmpProvider` screener+
   earnings+revenue-growth, `FinnhubProvider` news-sentiment+recommendation, `TwelveDataProvider` quote;
   HTTP dependency-injected; inert without keys; failures→None) + `gather_funnel_signals` (one bulk FMP
   earnings call + per-symbol Finnhub capped by `enrich_limit`). Wired into `run_watch` after the
   pre-screener, behind `research_funnel.enabled` (false), try/except fail-safe → feeds the rotator a
   ranked shortlist. Config block in `default_config.yaml`; `ScannerSettings.research_funnel` field.
   Tests: `test_research_funnel.py` (16) + `test_research_providers.py` (15). To enable later: set
   `research_funnel.enabled: true`, ensure FMP_API_KEY/FINNHUB_API_KEY in `.env`, tune thresholds, restart.
2. **GTC bracket-protection fix (stop/target now persist).** Was `paper_trading.time_in_force: day`.
   The entry is a **market order** (`alpaca_paper.submit_bracket` → MarketOrderRequest+BRACKET) that fills
   at trigger and never rests — so "day" wasn't expiring stale entries, it was expiring the protective
   take-profit/stop-loss legs at the close, leaving overnight positions UNPROTECTED (and `reconcile_closed`
   relies on those legs to detect target/stop exits). Fix: `time_in_force: gtc` in config + `gtc` is now
   the safe default/fallback in `paper_config.py`. Tests updated (`test_paper_trading_config.py`).
   **⚠️ EXISTING 10 open paper positions** were opened under day-TIF yesterday — their protective legs
   already expired at the 2026-06-03 close, so they are currently UNPROTECTED. The config fix only covers
   NEW orders. **REMEDIATION DONE (2026-06-04 pre-open):** new `paper-reprotect` CLI built
   (`broker.submit_protection`/`open_protective_symbols` OCO seam; `AlpacaPaperBroker` submits a GTC
   SELL OCO = take_profit.limit_price + stop_loss.stop_price — note Alpaca rejects a bare top-level
   limit_price, it needs the take_profit leg). Ran live against the paper account: **all 10 open positions
   re-protected** with GTC stop/target OCO (LYFT/CVS/PINS/D/DAL/OXY/SLB/BAC/HIMS/DKNG), using each
   position's stored levels. Verified idempotent (2nd run skipped all 10 — no double-protection). Tests:
   `test_broker_protection.py`. Re-run anytime with
   `python -m trading_bot.cli paper-reprotect --config config/default_config.yaml`.

### Pending work — do AFTER market close, prefer a fresh (cheaper) session
1. ~~**`GET /api/command-center` endpoint (bot)**~~ — ✅ DONE (see "Update" above).
1b. ~~**EOD bridge collision**~~ — ✅ DONE (Update 2). ~~**Universe expansion (staged)**~~ — ✅ DONE 349→548 (Update 2).
2. **Tony teaching / divergence memory layer** — spec `docs/superpowers/specs/2026-06-03-tony-teaching-divergence-design.md`.
3. **Research Funnel v2** (FMP/Finnhub/Twelve Data, staged universe) — spec `docs/superpowers/specs/2026-06-03-research-funnel-design.md`.
4. **Scan-coverage UTC-date edge** — after-hours scans (past UTC midnight) can mis-bucket coverage; make
   the coverage/`today_events` filter ET-market-date aware.
5. **CC-side (their terminal, not this repo):** add a bracket-validity guard so an override with
   target/stop invalid vs live price still places (D-override didn't place today); investigate why the
   "Forge" worker didn't spawn for a queued bug-fix; keep the memory-poison fix (reset `signal-ledger.md`
   + trim `_load_vault_history`).

### Restart commands (after close, if needed)
- Watch: `$env:PYTHONPATH="src"; python -m trading_bot.cli watch --config config/default_config.yaml`
- Backend: `$env:PYTHONPATH="src"; python -m uvicorn trading_bot.api.main:app --port 8001`
- Frontend: `cd dashboard-web; npm run dev`

---

## 2026-06-02 handoff — Outcomes bridge to Command Center + paper-trading phase 1

Branch: `feat/outcomes-emitter` (5 commits, suite 696 passed). Not merged to `main` yet.

### What shipped (in order)

1. **Tony outcomes emitter** (`src/trading_bot/vault/outcomes_bridge.py`) — commit `3c78e3f`.
   - `build_tony_outcomes(records, *, eod_date)` (pure): normalizes resolved records to the
     Command Center schema `{symbol, pick_date, result, entry, exit, return_pct, days_held,
     resolved_date}`. `result` ∈ `target_hit|stop_hit|closed|expired`. Unresolved rows skipped.
     `pick_date` = originating bridge date (day-1), the CC `(symbol, date)` join key — never entry_date.
   - `write_tony_outcomes(records, path=None)` honors `TONY_OUTCOMES_FILE`, defaults
     `reports/tony_stocks_outcomes.json`. `_to_float` guards NaN/inf → null (valid JSON).
   - 37 tests in `tests/test_outcomes_bridge.py`.

2. **Test-suite repair** (commits `3c78e3f` part, `e7d2862`). The Streamlit `trading_bot.dashboard`
   module was deleted in the Next.js overhaul but 4 test files still imported it. Deleted dead
   `test_v27a_regression.py`; repointed survivors to new homes (`cli._is_heartbeat_stale`,
   `cli._is_within_regular_market_hours`, `cli._summarize_product_reconciliation`); dropped tests
   for removed display helpers + the per-row reconciliation accounting the lightweight cli version
   intentionally dropped. `run_tests.ps1` is green again.

3. **Resolved-outcomes assembly + backfill** (commit `112916a`).
   - `analytics.build_resolved_outcome_records(rows)` walks each symbol's snapshot history into
     per-episode resolved records (episode = first appearance → first terminal row; consecutive
     terminal echoes collapse; a re-pick = a new episode with its own `pick_date`). Non-entered
     picks (empty `tracking_status`) are non-terminal and excluded. Exit/PL come from stored
     stop/target levels via `compute_terminal_outcome_fields`.
   - Wired through `cli._emit_tony_outcomes` → `build_tony_outcomes` → `write_tony_outcomes`,
     replacing the always-empty `outcomes_since_last_brief` source in the vault export.
   - New CLI: `python -m trading_bot.cli emit-outcomes --config config/default_config.yaml [--days N]`.
   - **Live backfill produced 37 real resolved outcomes** (13 target / 12 stop / 12 closed),
     pick_dates 2026-05-18→05-22, into `reports/tony_stocks_outcomes.json` (gitignored).
   - 9 tests in `tests/test_resolved_outcomes.py`.

4. **Paper-trading phase 1 — config + flags** (commit `9edefee`).
   - `src/trading_bot/execution/paper_config.py`: `PaperTradingConfig` + `load_paper_trading_config`
     (fail-closed: a misconfigured enabled:true → disabled + `disabled_reason`) +
     `assert_paper_base_url` (rejects the live `api.alpaca.markets` endpoint).
   - `paper_trading:` block in `default_config.yaml` (OFF; independent of `live_trading_enabled`).
   - `settings.paper_trading` dict field loads it. 18 tests in `tests/test_paper_trading_config.py`.
   - **Locked decisions** (encoded in config + dataclass defaults): risk-% of equity sizing,
     DAY entry TIF, `gate_on_command_center=false` (trade on Tony's trigger, not CC-gated),
     `close_on_command_center_exit=true` (flatten when CC verdict says sell/get-out),
     `account_label` for a future 2nd (CC) paper account.

### Coordination action for the operator (NOT code)
The Command Center lives at `C:/Users/alexa/Downloads/AI Operations Command Center` (separate dir).
The outcomes file is written to the **bot repo's** `reports/tony_stocks_outcomes.json`. To unblock
the CC's Phase 3/4 learning, point the CC at it via the **`TONY_OUTCOMES_FILE`** env var (the agreed
contract). Until then the CC stays in `awaiting_outcomes` cleanly.

### Also shipped this session (after the 4 items above)
5. **Intraday bridge handoffs** (commit `2510909`). `vault/bridge_schedule.py:due_bridge_slots` +
   `write_bridge_export(slot=...)` (timestamped `YYYY-MM-DDTHHMM.md`, `export_type: intraday-bridge`).
   Watch loop emits at US-Eastern checkpoints **10:30 / 13:00 / 15:30 / 16:00 EOD** (top of loop,
   before the market-hours guard so EOD fires after close; disk-idempotent; resets per ET day).
   `export-to-vault --slot {1030,1300,1530,eod}` for manual runs. 16 tests. **CC must recognize the
   timestamped intraday files, dedup on timestamp, and spawn a lighter "intraday update" task.**
6. **Paper-trading phase 2 — pure order router** (commit `743ae01`). `execution/order_router.py`:
   `size_position` (risk-% of equity from entry→stop, max_notional cap, whole shares) + `should_trade`
   (fail-closed gates: enabled, kill switch, market open, dedup one-per-symbol, max_open_positions,
   max_daily_orders, plan validity, size>0; state via `PortfolioState`). 18 tests. Suite **727 passed**.

### Paper trading phases 3–6 COMPLETE this session
3. `AlpacaPaperBroker` over alpaca-py (paper=True) + FakeBroker (commit `0b389f1`).
4. `paper_orders`/`paper_positions` tables + repo methods (commit `2a8fc34`).
5. `paper_engine.run_paper_cycle` (reconcile → CC exits → open) + watch-loop wiring, no-op when
   disabled, kill switch via `data/STOP_PAPER_TRADING` (commit `e3e57d1`).
6. `GET /api/paper/positions` + `paper-status` / `paper-flatten` CLIs (commit `4478684`).
Suite **766 passed**. Paper trading OFF by default (`paper_trading.enabled: false`).

### Remaining for the cross-project loop test (bot side)
- **CC verdicts reader** ✅ DONE — bot reads `reports/tony_stocks_verdicts.json` via
  `load_cc_verdicts`/`cc_exit_symbols`. BUT execution is now **PURE SEPARATION**
  (`close_on_command_center_exit: false`): the bot does NOT act on Tony's verdicts. They will become a
  teaching/divergence MEMORY layer (spec `docs/superpowers/specs/2026-06-03-tony-teaching-divergence-design.md`).
- **Alpaca paper account** ✅ verified — bot account `PA3P0RN75VL1` (label "Trading Bot"), $100k,
  SEPARATE from the CC's Tony account. Both buy + close flows exercised end-to-end, then all test
  artifacts wiped (orders cancelled, ledger cleared). `paper_trading.enabled: true`.
- CLIs: `paper-status`, `paper-flatten` (kill switch), `paper-check [--test-order SYM]`. Kill file:
  `data/STOP_PAPER_TRADING`. Bot also reads CC verdicts but only records (pure separation).
- **Dashboard visual** — Board real-P/L cell + StatusBar account chip consuming `/api/paper/positions`
  (API ready; small Next.js follow-up).

### At the open (operator, 2026-06-03)
Confirm the CC runner is up (`http://127.0.0.1:8765`); let the CC's 9:25 ET purge clear last night's
TEST bridges/verdicts; then `python -m trading_bot.cli watch --config config/default_config.yaml`
during market hours. The real scan exercises the full live loop on both (separate) paper books.

### Next initiative: Research Funnel v2
Spec: `docs/superpowers/specs/2026-06-03-research-funnel-design.md` — staged funnel (FMP screener +
earnings, Finnhub news-sentiment, Twelve Data breadth/fallback) feeding the existing scorer, evaluated
against live paper outcomes. Default-off, TDD, staged universe growth.

### Known bug (low priority)
Scan-coverage aggregation buckets scan runs by **UTC** date, so scans after ~20:00 ET (past UTC
midnight) show `Universe:0/Scored:0` for the ET report date. Harmless during market hours; fix = make
the coverage/`today_events` filter ET-market-date aware.

### Pre-existing note
`src/trading_bot/dashboard/` (Streamlit) is gone; the dashboard is Next.js (`dashboard-web/`) +
FastAPI (`src/trading_bot/api/`). The empty Board/Track Record in screenshots is expected when no
scan is running and the CC second-layer is awaiting — not a bug.

---

## Live Market Data handoff — Subsystem A (real-time Alpaca prices + alerts)

Live Market Data is complete. The dashboard now polls Alpaca for live prices, detects near-entry and stop-violation events, and surfaces them via SSE toasts with audio + desktop notifications.

**Backend (`src/trading_bot/api/`)**
- `market_calendar.py` — `market_status()` / `is_market_open()` via `pandas_market_calendars` NYSE calendar
- `live_prices.py` — `LiveQuote` dataclass, `PriceCache` (symbol rebuild, Alpaca batch fetch at `/v2/stocks/snapshots`, event detection), `run_price_poll_loop()` background task. Events: `near_entry` (crosses within 0.5% of entry, 5-min cooldown) and `stop_violation` (once per snapshot_id when triggered+open drops below stop).
- `routes/prices.py` — `GET /api/prices`, `GET /api/prices/{symbol}` (503 without Alpaca keys)
- `main.py` — lifespan initialises `PriceCache`, wires `asyncio.Queue` as `live_event_queue`, starts poll loop, registers prices router
- `routes/events.py` — SSE generator drains `live_event_queue` each 5-second cycle
- `schemas.py` — added `LiveQuoteSchema`, `MarketStatus`, `PricesResponse`

**New tests (22 total, all pass)**
- `tests/test_market_calendar.py` (6), `tests/test_price_cache.py` (6), `tests/test_event_detection.py` (6), `tests/test_api_prices.py` (4)

**Frontend (`dashboard-web/`)**
- Types: `SSELiveAlert`, `LiveQuote`, `MarketStatus`, `PricesResponse` added to `lib/types.ts`
- API: `api.prices()`, `api.priceSymbol(symbol)` added to `lib/api.ts`; `SSELiveAlert` added to `lib/sse.ts` union
- Hooks: `useLivePrices` (15s/120s poll), `useMarketStatus` (60s poll), `useAlerts` (toast state + beep + Web Notification)
- Sound: `lib/sound.ts` — 880Hz/200ms for near_entry, 330Hz/400ms for stop_violation
- Components: `LivePrice`, `DistanceToBar`, `MarketClock` (under `components/market/`); `ToastStack`, `AlertManager`, `PermissionBanner` (under `components/alerts/`)
- Layout: `PermissionBanner` + `AlertManager` mounted at root; `MarketClock` pinned to Sidebar bottom
- Existing components updated: `TradeCard` (live price + distance bar), `ScanTable` (LIVE column replaces CLOSE), `SymbolDrawer` (live price in header + distance bar)

**TypeScript build:** clean (`tsc --noEmit` → no errors)

**Dependency added:** `pandas-market-calendars>=4.4`

**Commits:** `b9c060a` (backend), `b6b722c` (frontend)

**Demo mode:** without `ALPACA_API_KEY`/`ALPACA_SECRET_KEY`, prices endpoint returns 503 and poll loop is a no-op — all other dashboard features work normally.

---

## V38 handoff — Next.js + FastAPI Dashboard

V38 is complete. The Streamlit dashboard has been replaced with a Next.js 15 (App Router) + FastAPI stack with a Bloomberg financial terminal aesthetic.

**What was built:**

**FastAPI layer (`src/trading_bot/api/`)**
- `main.py` — FastAPI app, lifespan sets `db_path`/`vault_dir` from env, CORS for localhost:3000, 10 routers under `/api`
- `deps.py` — `get_repo()` FastAPI dependency
- `schemas.py` — all Pydantic v2 response models
- `routes/health.py` — `GET /api/health`
- `routes/today.py` — `GET /api/today` (KPIs, watch status, events, snapshots)
- `routes/picks.py` — `GET /api/picks`, `GET /api/tracking`
- `routes/outcomes.py` — `GET /api/outcomes?filter=all|open|targets|stops`
- `routes/scan.py` — `GET /api/scan/latest`, `GET /api/scan/overview`
- `routes/analytics.py` — `GET /api/analytics/backtest`
- `routes/events.py` — `GET /api/events`, `GET /api/events/stream` (SSE)
- `routes/system.py` — `GET /api/system/health`
- `routes/symbols.py` — `GET /api/symbols/{symbol}/detail`, `/chart`
- `routes/vault.py` — `GET /api/vault/bridge`, `GET /api/insights`

**Next.js frontend (`dashboard-web/`)**
- App Router pages: `/today`, `/watchlist`, `/outcomes`, `/scan`, `/analytics`, `/system`
- Design tokens: `--bg-base:#050505`, `--green:#00e676`, `--amber:#ffab00`, `--cyan:#00e5ff` (JetBrains Mono)
- Components: `Sidebar`, `KPIBar`, `ScanTable`, `ActivityFeed`, `TradeCard`, `EquityCurve`, `ScoreBreakdown`
- Overlays: `SymbolDrawer` (slide-in on ticker click), `NotificationDrawer`
- Data: TanStack Query v5 (30s stale), `useSSE()` hook for live event stream
- Build: passes `next build` cleanly, all 6 routes as static pages

**Infrastructure**
- `Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`, `Makefile`
- `requirements.txt` updated: `fastapi`, `uvicorn[standard]`, `sse-starlette`, `httpx`

**Tests:** 9 API smoke tests in `tests/test_api_smoke.py` — all pass. Full suite: 849+ passed.

**To launch (local dev):**
```powershell
# Terminal 1 — API
$env:PYTHONPATH = "src"; .venv\Scripts\uvicorn.exe trading_bot.api.main:app --port 8000 --reload

# Terminal 2 — Web
cd dashboard-web; npm run dev
```

**To launch (Docker):**
```powershell
docker compose up
```

**No changes to:** Streamlit dashboard (still present), scoring, CLI, backtest, vault, trading rules.

---
## B-Phase 1 handoff â€” Obsidian Memory Layer

B-Phase 1 is complete. The trading bot now writes Obsidian-compatible markdown to two vault locations after every EOD run.

**What was built:**
- `src/trading_bot/vault/sector_map.py` â€” static tickerâ†’`{sector, etf}` lookup (180+ tickers, 11 sector ETFs + benchmarks)
- `src/trading_bot/vault/writer.py` â€” `write_daily_note()`, `upsert_ticker_page()`, `update_vault_index()`
- `src/trading_bot/vault/bridge.py` â€” `write_bridge_export()` with cluster detection and ETF snapshot
- `src/trading_bot/vault/__init__.py` â€” re-exports all four public functions
- `scripts/seed_vault.py` â€” one-time backfill: `python scripts/seed_vault.py --days-back 60`
- `src/trading_bot/settings.py` â€” added `vault: dict[str, Any] | None = None` field
- `config/default_config.yaml` â€” added `vault:` block with `enabled`, `vault_dir`, `command_center_dir`, `bridge_enabled`
- `src/trading_bot/cli.py` â€” vault import, `_run_vault_export()`, `run_export_to_vault()`, step 8 in `run_after_market_review()`, `export-to-vault` subcommand

**Architecture:**
- Vault 1 (`vault/` in repo): daily notes, ticker signal pages, index â€” full operational history
- Bridge: after EOD, writes curated analyst brief to `{command_center_dir}/bridge/tony-stocks/YYYY-MM-DD.md`
- Vault 2 (AI Operations Command Center): Tony Stocks agent reads bridge files for deep analysis
- All writes are direct Python disk writes (no MCP in write path)

**Signal tiers in bridge export:**
- Tier 1: `days_active >= 3` â€” full conviction block with R/R
- Tier 2: `days_active == 2` â€” monitor table
- Tier 3: `days_active == 1` â€” new signals table
- Sector ETF Snapshot + Cluster Risk Flags (3+ signals same sector)

**Tests:** 32 new tests in `tests/test_vault_writer.py` and `tests/test_vault_bridge.py`. Full suite: 849 passed.

**No changes to:** scoring, entry triggers, rotation, trading logic, demo/real data guards.

**To run seed (one-time):**
```powershell
$env:PYTHONPATH = "src"; python scripts/seed_vault.py --days-back 60
```

**To run standalone export:**
```powershell
$env:PYTHONPATH = "src"; python -m trading_bot.cli export-to-vault --config config/default_config.yaml
```

---

## V37 handoff - Dashboard Revamp (4-tab Professional Slate)

V37 is complete. The Streamlit dashboard has been fully redesigned with a uniform Professional Slate visual system across 4 pages.

**What changed:**
- Navigation: 5 tabs â†’ 4 tabs: **Today / Watchlist / Outcomes / Research**
- Added `render_compact_card()` to `theme.py` â€” single unified card renderer used by all pages
- `render_today()`: Split Hero layout â€” KPI header band always visible; briefing left, live setups right
- `render_watchlist()`: Compact cards with chip filter (All/Watching/Active/Pending)
- `render_outcomes()`: KPI bar + chip filter (All/Open/Targets/Stops) + compact cards
- `render_research()`: Discovery funnel strip + signals table + backtest + agent insights + system health expander
- Removed old dispatchers: `render_home`, `render_tony_watchlist`, `render_results`, `render_intelligence`

**Files changed:** `src/trading_bot/dashboard/theme.py`, `src/trading_bot/dashboard/app.py`, `tests/test_dashboard_theme.py`, `tests/test_dashboard_helpers.py`

**Design tokens (Professional Slate):** base `#0f172a`, surface `#1e293b`, header `#111827`, blue `#3b82f6`, violet `#8b5cf6`, green `#34d399`, red `#ef4444`, amber `#fbbf24`

No changes to: helpers.py logic, database, CLI, backtest module, scoring, or trading rules.

---

## V31A handoff - Coverage and Rotation Diagnostic Label Consistency

### Current active task

V31A is complete. EOD report and after-market-review output no longer display two confusing "unique symbols scanned today" numbers. Both sections now have distinct, self-explaining labels and a bridging note that explicitly states why the counts differ.

### Problem solved

The EOD report previously showed:
- Scan coverage: "Unique symbols scanned today: 345 unique symbols scanned (98.85%)"
- Rotation diagnostics: "Unique symbols scanned today: 141 unique symbols scanned (40.4%)"

Both used the same label string "Unique symbols scanned today" but measured completely different things, causing operator confusion.

### Changes

- **`src/trading_bot/cli.py`**
  - `_build_eod_report_markdown()`: Scan coverage line changed from "Unique symbols scanned today" to "Unique symbols with bar data today (all symbols that returned OHLCV bars across all scan cycles)". Scored-symbols line changed from "Unique symbols scored today" to "Unique symbols fully scored today". Added bridging note after the percent-coverage line explaining the two counts differ by design. Rotation diagnostics line changed from "Unique symbols scanned today" to "Unique symbols in rotation tracking (discovery-rotation-selected symbols â€” subset of total bar-data symbols)".
  - `_print_scan_coverage_summary()`: Same label changes for stdout output. Added bridging note after percent coverage print.
  - `_print_rotation_diagnostics()`: Same rotation label change for stdout output.

- **`tests/test_outcome_analytics.py`**
  - Added 5 new V31A tests: `test_v31a_coverage_label_differs_from_rotation_label`, `test_v31a_markdown_coverage_uses_bar_data_label`, `test_v31a_markdown_rotation_uses_tracking_label`, `test_v31a_markdown_bridging_note_present`, `test_v31a_markdown_rotation_section_count_value`.

### Files changed

- `src/trading_bot/cli.py`
- `tests/test_outcome_analytics.py`
- `AGENT_STATE.md`

### Tests/checks run

- `pytest tests/test_outcome_analytics.py -x -q` â†’ **123 passed**
- `pytest tests/test_v31_rotation_diagnostics.py -x -q` â†’ **17 passed**
- `powershell -ExecutionPolicy Bypass -File scripts/run_tests.ps1` â†’ **799 passed** (up from 794)

### Behavior changed

Labels only â€” no scoring, rotation, trigger, or data-flow changes. The numbers themselves are unchanged; only the text labels and an explanatory note were added.

### Safety

No scoring changes. No rotation behavior changes. No trigger-rule changes. No trading/paper/broker/orders. No demo data. No data deletion. No dashboard visual changes. Label-only edits plus new test assertions.

---

## V36B handoff - Lightweight Pre-Screener Funnel

### Current active task

V36B is complete. A lightweight pre-screener funnel now filters the symbol universe ONCE per watch cycle before the discovery rotation picks symbols for full scoring. No extra API calls per symbol. Uses cached scan_results data.

### Problem solved

EOD reports showed ~88 of ~163 selected symbols failing cheap checks (volume/price/bars) per cycle, wasting rotation slots on always-failing symbols. Only ~75 of 349 symbols were actually scored per cycle (~40% universe coverage).

### Changes

- **`src/trading_bot/data/pre_screener.py`** (new file)
  - `pre_screen_universe(symbols, *, recent_metrics, min_price, max_price, min_avg_volume, min_symbols_after_filter)` â€” applies price and volume filters using cached data; missing-data symbols pass through unconditionally.
  - `build_recent_symbol_metrics(scan_result_rows, *, max_cache_age_days)` â€” builds per-symbol metrics dict from recent scan_results rows; picks most-recent row per symbol within the cache window.
  - `load_pre_screener_config(settings_dict)` â€” returns normalized config dict with defaults.
  - `PreScreenResult` dataclass â€” carries filtered symbol list and diagnostic counts (original_count, filtered_count, screened_out_count, no_cache_data_count, fallback_used, reasons).

- **`src/trading_bot/storage/repositories.py`**
  - Added `get_recent_scan_result_metrics(max_age_days, limit)` â€” lightweight query fetching only `symbol`, `latest_close`, `avg_volume_20`, `created_at` from scan_results within the age window.

- **`src/trading_bot/settings.py`**
  - Added `pre_screener: dict[str, Any] | None = None` field to `ScannerSettings` so YAML config is loaded without being ignored.

- **`src/trading_bot/cli.py`**
  - Added import of `PreScreenResult`, `build_recent_symbol_metrics`, `load_pre_screener_config`, `pre_screen_universe` from `trading_bot.data.pre_screener`.
  - `run_watch()`: after quarantine, before `WatchUniverseRotator.__init__()`, runs the pre-screener to filter `universe_symbols`. Pre-screener failure is caught and logged; the full list is used as fallback.
  - Added `_log_pre_screen_result(result)` helper â€” prints one-line summary with screened-out reasons to stdout.

- **`config/default_config.yaml`**
  - Added `pre_screener:` block with `enabled: true`, `min_symbols_after_filter: 50`, `use_snapshot_cache: true`, `max_cache_age_days: 7`.

- **`tests/test_pre_screener.py`** (new file, 38 tests)
  - `TestPreScreenUniverse` â€” price below/above bounds excluded, volume below excluded, exact boundary passes, no-cache-data passes, partial cache passes, fallback trigger, no-fallback, immutability, count consistency, to_dict keys.
  - `TestBuildRecentSymbolMetrics` â€” empty input, newest row wins, age cutoff, within cutoff, missing close/volume handled, missing symbol/created_at skipped, uppercase normalization, multiple symbols.
  - `TestLoadPreScreenerConfig` â€” defaults when None/empty, overrides, partial overrides keep defaults.
  - `TestRepositoryGetRecentScanResultMetrics` â€” empty DB, within window, outside window, correct fields, multiple symbols (real in-memory SQLite).
  - `TestPreScreenerEndToEnd` â€” full pipeline filters bad symbols, no-data pass-through, stale data excluded from metrics.

### Files changed

- `src/trading_bot/data/pre_screener.py` (new)
- `src/trading_bot/storage/repositories.py`
- `src/trading_bot/settings.py`
- `src/trading_bot/cli.py`
- `config/default_config.yaml`
- `tests/test_pre_screener.py` (new)
- `AGENT_STATE.md`

### Tests/checks run

- `.venv/Scripts/python.exe -m pytest tests/test_pre_screener.py -v` â†’ **38 passed**
- `.venv/Scripts/python.exe -m pytest --tb=short -q` â†’ **794 passed** (up from 756)

### How the pre-screener integrates

```
run_watch() startup (once, before cycle loop):
  1. load_universe() â†’ 349 symbols
  2. apply_symbol_quarantine() â†’ ~344 symbols
  3. [NEW] pre_screen_universe() â†’ ~200 quality-eligible symbols
     (uses get_recent_scan_result_metrics â†’ build_recent_symbol_metrics)
  4. WatchUniverseRotator(universe_symbols=filtered_pool, ...)
     â†’ discovery rotation now draws from ~200 symbols instead of 344
```

First run after a cold start: no scan_results data yet â†’ all 344 symbols have no cached metrics â†’ all pass through (no_cache_data_count=344). After the first scan cycle, future restarts of watch will have metrics and start filtering.

### Safety

No scoring changes. No trigger-rule changes. No trading/paper/broker/orders. No demo data inclusion. No data deletion. Pre-screener is read-only â€” it only filters which symbols enter the rotation discovery pool. Worst-case failure mode is catching the exception and using the full list (existing behavior).

### Next recommended step

1. Run `watch --max-cycles 1` to confirm pre-screener prints its summary line during startup.
2. After a few cycles, check that EOD rotation diagnostics show improved universe coverage (fewer repeat symbols in discovery bucket).
3. Consider adding the pre-screen result to the scan_coverage EOD report section so operators can see screened_out counts in daily output.

---

## V35 handoff - Backtest CLI Enhancements

### Current active task

V35 is complete. The `backtest` command now supports multi-ticker runs, date ranges, CLI strategy params, and report saving.

### Changes

- **`src/trading_bot/cli.py`**
  - `run_backtest()`: rewrote to support multi-ticker (`--ticker SPY,QQQ`), `--start`/`--end` date range, `--fast-window`/`--slow-window`/`--starting-cash` overrides, and `--save-report` flag.
  - Added `_save_backtest_report()` and `_build_backtest_markdown()` helpers.
  - Updated import: added `load_yfinance_range`.
  - Fixed `_build_eod_report_markdown`: skip-reason section header no longer renders when all counts are zero.
  - Fixed `run_scan`: `no_eligible_setup` removed from `skip_reason_counts`, tracked separately as `no_eligible_setup_count`.

- **`src/trading_bot/data/__init__.py`**
  - Added `load_yfinance_range(ticker, start, end)` â€” fetches bars for a specific date range.

- **`src/trading_bot/config.py`**
  - Added `default_ticker` and `default_period` fields to `BacktestConfig`.

- **`tests/test_backtest_cli.py`** (new)
  - 7 tests covering: date-range fetch, multi-ticker, report file creation, start/end routing, parser args.

- **`tests/test_outcome_analytics.py`**
  - Added `test_eod_markdown_skip_section_hidden_when_all_zero`.

### Files changed

- `src/trading_bot/cli.py`
- `src/trading_bot/data/__init__.py`
- `src/trading_bot/config.py`
- `tests/test_backtest_cli.py` (new)
- `tests/test_outcome_analytics.py`
- `CURRENT_STATUS.md`
- `FILE_STRUCTURE.md`
- `AGENT_STATE.md`

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **756 passed**

### Safety

No scoring changes. No trigger-rule changes. No trading/paper/broker/orders. The `backtest` command remains research-only. All reports carry `research_only: True` and a `not_applied_note`.

---

## V35A handoff - Backtest CLI Enhancements (Task 3 of 5)

### Current active task

Task 3 complete: Added CLI args for multi-ticker, date range, and strategy params to the `backtest` subparser.

### Changes

- **`src/trading_bot/cli.py`**
  - Updated `backtest` subparser in `build_parser()`:
    - Updated help text: "Run a backtest against historical OHLCV data."
    - `--ticker` now accepts comma-separated multi-ticker input (e.g., "SPY,QQQ")
    - `--csv` documented as single symbol only
    - `--period` note: "Ignored when --start/--end set"
    - **New args:**
      - `--start` (str, default None): Start date for historical data (YYYY-MM-DD)
      - `--end` (str, default None): End date for historical data (YYYY-MM-DD)
      - `--fast-window` (int, default None): Fast MA window. Overrides config value.
      - `--slow-window` (int, default None): Slow MA window. Overrides config value.
      - `--starting-cash` (float, default None): Starting cash for the backtest. Overrides config value.
      - `--save-report` (action="store_true"): Save backtest_report.json and backtest_report.md to --output-dir.
      - `--output-dir` (str, default "reports"): Base directory for saved reports.

- **`tests/test_backtest_cli.py`**
  - Added `test_backtest_parser_accepts_start_end_args()` â€” verifies parser accepts all new args and parses types correctly (int for fast/slow window, float for starting-cash).

### Files changed

- `src/trading_bot/cli.py` (backtest subparser block in `build_parser()`)
- `tests/test_backtest_cli.py` (new test appended)

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **753 passed** (new test included)
- Specific test `test_backtest_parser_accepts_start_end_args` â†’ **passed**

### Commit

- `92d5598` - 2026-05-21 - Backtest - Add --start/--end/--fast-window/--slow-window/--save-report CLI args

### Safety

Parser-only change. No scoring, trigger, rotation, trading, demo, or data changes. No behavior changes; args are just available for future `run_backtest()` implementation (Task 4).

### Next recommended step

Task 4: Implement multi-ticker backtest and report saving in `run_backtest()`. This will consume the new parser args and build the backtest logic.

---

## V34B handoff - Code Review Bug Fixes

### Current active task

V34B is complete. Three correctness bugs found by code review were fixed. No behavior changes to scanning, scoring, trigger rules, or trading.

### Changes

- **`src/trading_bot/cli.py`**
  - `_build_scan_coverage_summary()`: backward-compat fold of `not_enough_data` into `not_enough_bars` now only applies when the payload does NOT already have `not_enough_bars` set. Previously the fold ran unconditionally, causing double-counting for any payload that carried both keys (e.g. during a mixed deploy window).
  - `run_scan()`: removed `skip_reason_counts["no_eligible_setup"] += no_eligible_setup_count`. Scored symbols with weak/invalid setup categories are not pre-scoring skips â€” adding them to `skip_reason_counts` inflated skip totals and broke funnel math. The count is now stored separately as `summary["no_eligible_setup_count"]`.

- **`src/trading_bot/dashboard/app.py`**
  - `render_system_health()`: wrapped the `render_agent_insights()` call in `try/except Exception` with `st.warning()` fallback. A missing or broken `agent_bridge` module previously crashed the entire Settings tab.

### Files changed

- `src/trading_bot/cli.py`
- `src/trading_bot/dashboard/app.py`
- `AGENT_STATE.md`

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **717 passed**

### Safety

No scoring changes. No trigger-rule changes. No rotation changes. No trading/paper/broker/orders. No demo data. No data deletion. No dashboard visual changes. Fixes are to skip-reason accounting and dashboard error handling only.

---

## V33 handoff - Better Skipped And Not-Scored Reasons

### Current active task

V33 is complete. Scan coverage reporting now uses more granular skip/not-scored reason categories instead of collapsing everything into broad buckets. No scoring, trigger, rotation, or trading behavior changes.

### Changes

- **`src/trading_bot/cli.py`**
  - Expanded `SCAN_SKIP_REASON_KEYS` from 6 to 11 keys: added `not_enough_bars`, `avg_volume_below_minimum`, `stale_data`, `no_eligible_setup`, `duplicate_tracked`. Old keys kept for backward compat.
  - Added `_SKIP_REASON_LABELS` dict mapping each key to a human-readable label for print/markdown output.
  - `run_scan()` loop:
    - Bar-count skip (`len(data) < 60`) now uses `not_enough_bars` instead of `not_enough_data`.
    - Liquidity check split: `avg_volume_below_minimum` when avg share volume fails; `liquidity_below_minimums` when dollar volume fails.
    - After scoring loop: counts symbols with weak/invalid setup_category (`Weak / Avoid`, `Overextended / Wait`, `Invalid Trade Plan`, `Insufficient Data`) â†’ `no_eligible_setup`.
    - After Alpaca provider block: counts `provider.stale_symbols` â†’ `stale_data` in skip_reason_counts and scan summary.
  - `_build_scan_coverage_summary()`: aggregates new keys; backward compat folds old `not_enough_data` payloads into `not_enough_bars`.
  - `_print_scan_coverage_summary()`: uses `_SKIP_REASON_LABELS` for human-readable output; omits zero-value backward-compat keys unless non-zero.
  - `_build_eod_report_markdown()`: uses `_SKIP_REASON_LABELS` for labeled markdown skip-reason list.

- **`tests/test_outcome_analytics.py`**
  - Updated `test_after_market_review_markdown_includes_scan_coverage_section` to match new label format.
  - Added 6 V33 tests: new keys in output, backward compat `not_enough_data` folding, unknown fallback, missing/quarantine specific reasons, labels in markdown, empty fallback all-zero.

### Files changed

- `src/trading_bot/cli.py`
- `tests/test_outcome_analytics.py`
- `AGENT_STATE.md`

### Tests/checks run

- `pytest -x -q -k "scan_coverage or skip_reason or v33"` â†’ **12 passed**
- `pytest -x -q` â†’ running

### Safety

No scoring changes. No trigger-rule changes. No rotation changes. No trading/paper/broker/orders. No demo data. No data deletion. No dashboard visual changes. The scan loop changes only affect which skip-reason bucket a symbol lands in â€” which symbols are scored is unchanged.

---

## V34A handoff - Terminal Outcome Model Fields

### Current active task

V34A is complete. Backend/model helpers for terminal exit price and final research P/L are added without changing dashboard layout or visuals.

### Changes

- **`src/trading_bot/snapshots/active_tracking.py`**
  - Added `compute_terminal_outcome_fields(snapshot: dict) -> dict` â€” pure helper that computes terminal outcome fields from any snapshot dict.
  - Returns: `is_terminal_outcome`, `terminal_exit_price`, `terminal_exit_reason`, `terminal_research_pl_pct`, `terminal_exit_price_note`.
  - `stop_hit` (tracking_status or outcome_label): exit price from `current_stop_price` â†’ `original_stop_price` â†’ `stop`.
  - `target_hit` (tracking_status or outcome_label): exit price from `current_target_price` â†’ `original_target_price` â†’ `target`.
  - Other closed states: exit price from `current_price` â†’ `intraday_close` â†’ `close` with inferred note.
  - Active positions and `insufficient_future_data` â†’ `is_terminal_outcome=False`.
  - P/L = `(exit_price - original_entry_price) / original_entry_price * 100` (None when exit price unavailable).

- **`src/trading_bot/snapshots/__init__.py`**
  - Exported `compute_terminal_outcome_fields`.

- **`src/trading_bot/analytics/outcomes.py`**
  - Added `build_terminal_outcome_summary(rows: pd.DataFrame) -> dict` â€” aggregates per-row terminal fields into a summary with stop_hit, target_hit, other_closed groups, avg P/L, positive/negative counts, inferred_exit_price_count.
  - Added `OutcomeAnalytics.terminal_outcome_summary()` delegation method.

- **`src/trading_bot/analytics/__init__.py`**
  - Exported `build_terminal_outcome_summary`.

- **`src/trading_bot/cli.py`**
  - Imported `build_terminal_outcome_summary`.
  - `run_eod_report()`: calls `build_terminal_outcome_summary(prepared)` and includes `terminal_outcome_summary` in return dict.

- **`tests/test_v15_8_active_tracking.py`**
  - Added `TestTerminalOutcomeFields` class with 12 tests: stop_hit exit price, stop P/L, target_hit exit price, target P/L, active not terminal, insufficient_future_data not terminal, other closed inferred price, missing exit price note, stop_before_target, target_before_stop, current > original stop preference, current > original target preference, no broker/order fields.

- **`tests/test_outcome_analytics.py`**
  - Imported `build_terminal_outcome_summary` and `pytest`.
  - Added 7 V34A tests: empty df, stop P/L, target P/L, active excluded, insufficient excluded, inferred exit counted, EOD return dict includes key.

### Files changed

- `src/trading_bot/snapshots/active_tracking.py`
- `src/trading_bot/snapshots/__init__.py`
- `src/trading_bot/analytics/outcomes.py`
- `src/trading_bot/analytics/__init__.py`
- `src/trading_bot/cli.py`
- `tests/test_v15_8_active_tracking.py`
- `tests/test_outcome_analytics.py`
- `AGENT_STATE.md`

### Tests/checks run

- `pytest tests/test_v15_8_active_tracking.py tests/test_outcome_analytics.py -x -q` â†’ **147 passed**
- `pytest -x -q` â†’ running

### Safety

No dashboard visual changes (app.py and theme.py untouched). No scoring changes. No trigger-rule changes. No trading/paper/broker/orders. No demo data. No data deletion. No position-ledger filtering changes. Terminal P/L is research-only and uses stored stop/target levels, not actual filled prices.

---

## V31 handoff - Discovery Rotation Diagnostics

### Current active task

V31 is complete. `eod-report` and after-market review now include a research-only discovery rotation diagnostics section that measures whether Tony is rotating through the expanded universe or repeatedly scanning the same symbols.

### Changes

- **`src/trading_bot/analytics/outcomes.py`**
  - Added `build_rotation_diagnostics(scan_results_today, *, configured_universe_size, active_symbols, core_symbols, rotation_bucket_summary)` standalone function.
  - Returns: `note`, `unique_symbols_scanned`, `total_scan_appearances`, `repeat_scan_count`, `top_repeated_symbols` (symbol/scan_count/universe_role/repeat_label), `active_core_repeats`, `estimated_fresh_discovery`, `percent_universe_touched`, `rotation_bucket_summary`, `symbols_never_scanned_today`.
  - Active/core symbols labeled "expected (active/core)" in `repeat_label`; discovery repeats are not.
  - Added `OutcomeAnalytics.rotation_diagnostics()` delegation method.

- **`src/trading_bot/analytics/__init__.py`**
  - Added `build_rotation_diagnostics` to imports and `__all__`.

- **`src/trading_bot/cli.py`**
  - Added `build_rotation_diagnostics` to analytics import.
  - In `_build_scan_coverage_summary()`: calls `build_rotation_diagnostics()` and includes `rotation_diagnostics` in the returned dict.
  - Added `_print_rotation_diagnostics(diag)` helper.
  - In `_print_scan_coverage_summary()`: calls `_print_rotation_diagnostics()`.
  - In `_build_eod_report_markdown()`: added "### Discovery Rotation Diagnostics" subsection.

- **`tests/test_v31_rotation_diagnostics.py`** (new file, 17 tests)
  - 14 pure unit tests: empty df, no symbol column, unique count, repeat count, no repeats, fallback, no universe_role, active labeled expected, core labeled expected, discovery not expected, active_core_repeats empty, percent universe, percent none, note always present.
  - 3 integration tests using `_make_test_db` + `_patch_eod` helpers.

### Files changed

- `src/trading_bot/analytics/outcomes.py`
- `src/trading_bot/analytics/__init__.py`
- `src/trading_bot/cli.py`
- `tests/test_v31_rotation_diagnostics.py` (new)
- `tests/test_outcome_analytics.py` (import added)
- `AGENT_STATE.md`

### Tests/checks run

- `pytest tests/test_v31_rotation_diagnostics.py -x -q` â†’ **17 passed**
- `pytest -x -q` â†’ **691 passed**

### Safety

No scoring changes, no trigger-rule changes, no rotation-behavior changes, no broker/paper/live execution, no orders, no demo-data inclusion in active analytics, no dashboard visual changes, no data deletion. This is additive reporting only.

### Next recommended step

Collect real market days with the rotation diagnostics in EOD output to calibrate repeat thresholds before acting on them.

---

## V30 handoff - Safe Universe Expansion To 300-500 Symbols

### Current active task

V30 is complete. Tony's active research universe has been expanded in a staged, liquid-first way so scan coverage can increase without changing scoring rules, trigger rules, quarantine behavior, or trading execution behavior.

### Changes

- **`config/universe_swing_research_config.yaml`**
  - Added a staged liquid expansion batch made up of major sector ETFs plus liquid, actively traded common stocks across technology, financials, healthcare, industrials, energy, consumer, communication, real estate, and utilities.
  - Kept existing core/watchlist/priority symbols intact.
  - Left known bad symbols in the universe file so no data was deleted, but quarantine behavior still excludes them from real-data-only product flow.
  - Added notes clarifying that this is a staged expansion before a broader screener funnel and not a jump to thousands of symbols.
  - Raised `filters.max_universe_size` from `200` to `350`.

- **`config/default_config.yaml`**
  - Raised `max_symbols` from `100` to `175` so the expanded universe can actually increase scan coverage while still staying within the existing Alpaca/watch rotation caps.
  - Added a short note that this remains a staged pre-screener expansion.

- **`tests/test_universe.py`**
  - Updated production-universe expectations to the new size band.
  - Added coverage that default-config quarantine still removes `HCP`, `SAMSF`, `SMAR`, and `SQ` from real-data-only flow.
  - Added coverage that larger-universe rotation still respects the cycle cap, preserves core symbols first, and carries open/previous-priority symbols without duplicates.

### Current size

- Previous configured universe load: `171` symbols (`168` non-excluded)
- New configured universe load: `349` symbols (`346` non-excluded)
- Default scan cap now: `175` symbols per scan

### Files changed

- `config/default_config.yaml`
- `config/universe_swing_research_config.yaml`
- `tests/test_universe.py`
- `AGENT_STATE.md`

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` -> **674 passed**
- `git diff --check` -> passed (CRLF normalization warnings only)

### Safety

No scoring changes, no trigger-rule changes, no broker/paper/live/order changes, no quarantine removal, no data deletion, no demo data additions, and no dashboard visual changes. This is a staged universe/config expansion only.

### Next recommended step

Review a few live scan-coverage reports with the larger rotation pool before considering any further expansion beyond `350` or moving toward a full-market screener funnel.

---

## V29 handoff - Scan Coverage And Scoring Funnel Report

### Current active task

V29 is complete. `eod-report` and after-market review output now include a research-only scan coverage and scoring funnel section built from stored scan run data and Tony event payloads.

### Changes

- **`src/trading_bot/cli.py`**
  - `run_scan()` now records additive reporting metadata in the existing scan summary payload only: selected symbol list, scored symbol list, real-data symbol count, and best-available skip-reason counts.
  - Added scan-coverage helpers that aggregate latest-run funnel counts plus same-day unique coverage, batch/API usage, rotation bucket summary, and best-available skip reasons from stored scan/watch data.
  - `run_eod_report()` now prints a `Scan coverage and funnel:` section and returns `scan_coverage` in the result payload.
  - After-market markdown output now includes a `Scan Coverage And Funnel` section when coverage data is present.

- **`src/trading_bot/storage/repositories.py`**
  - Added recent scan-run listing and scan-results-by-run-id helpers so EOD reporting can aggregate todayâ€™s scan coverage without changing scan logic.

- **`tests/test_outcome_analytics.py`**
  - Added V29 coverage for coverage summary counts, not-scored count, missing/quarantine counts, percent-coverage fallback, skip-reason fallback, and markdown/EOD output presence.

### Files changed

- `src/trading_bot/cli.py`
- `src/trading_bot/storage/repositories.py`
- `tests/test_outcome_analytics.py`
- `AGENT_STATE.md`

### Safety

No scoring changes, no trigger-rule changes, no rotation-behavior changes, no broker/paper/live execution changes, no orders, no demo-data inclusion in active analytics, no dashboard visual changes, and no data deletion. This is additive reporting only.

### Next recommended step

Collect a few real market days with the new additive scan summary payloads so the coverage funnel and skip-reason counts can be reviewed on live data before considering any rotation or universe changes.

---

## V28 handoff - Tony Signal Scorecard

### Current active task

V28 is complete. Outcome analytics and `eod-report` now build a research-only Tony Signal Scorecard from existing stored real-only snapshot fields so future outcome attribution can be reviewed without changing scoring or trigger logic.

### Changes

- **`src/trading_bot/analytics/outcomes.py`**
  - Added `build_signal_scorecard()` plus `OutcomeAnalytics.signal_scorecard()`.
  - Scorecard groups existing stored signals by signal value and reports: `total_rows`, `triggered_rows`, `active_rows`, `conclusive_rows`, `target_hits`, `stop_hits`, `partial_moves`, and `insufficient_future_data`.
  - Included signal dimensions from existing data only: `setup_category`, above/below VWAP, opening-range breakout/breakdown, volume signal, ATR risk, market context, risk/reward bucket, reassessment label, score bucket, and universe role.
  - Added `SIGNAL_NOT_STORED` fallback for rows where a signal was not stored.
  - `insufficient_future_data` is counted as pending and excluded from conclusive/stop outcomes.

- **`src/trading_bot/cli.py`**
  - `run_outcome_analytics()` now prints and returns the Signal Scorecard.
  - `run_eod_report()` now prints an `Signal Scorecard:` section and returns it in the result payload.
  - After-market EOD markdown builder includes a Signal Scorecard section when present.

- **`tests/test_outcome_analytics.py`**
  - Added V28 coverage for sample signal rows, missing-signal fallback, real-only filtering, pending `insufficient_future_data`, and EOD signal-scorecard output.

### Files changed

- `src/trading_bot/analytics/__init__.py`
- `src/trading_bot/analytics/outcomes.py`
- `src/trading_bot/cli.py`
- `tests/test_outcome_analytics.py`

### Safety

No scoring changes, no trigger-rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion in active analytics, no dashboard visual changes, and no data deletion. Signal attribution is explicitly labeled preliminary and research-only.

### Next recommended step

Collect more real-only market days before using any signal-count differences for judgment. This pass is reporting only.

---

## V27A handoff - Restore V26D Ledger/Product Filters After V27 Visual Redesign

### Current active task

V27A is complete. V27 committed its helpers.py from the pre-V26A baseline, silently dropping all data integrity fixes. V27A re-applies all V26A-D fixes on top of V27 visual design without touching the render/theme layer.

### Regression cause

The V27 commit (`7a785fc`) was authored against the pre-V26A state of `helpers.py` and `app.py`. It added the unified Watchlist visual design but overwrote the V26A-D integrity fixes (DQ filters, stale lifecycle, Results ledger source, unreconciled diagnostic). The V26A-D changes had been in the working directory but were overwritten by the commit.

### Changes

**`helpers.py`**
- `_BAD_DQ_VALUES` frozenset: `{"missing_real_data", "fallback_data", "intraday_fallback_demo", "demo_data"}` (re-added)
- `_product_rows_only`: restored `used_demo_data`, `tony_data_quality_read`, `snapshot_provider` filters (HCP/SMAR/CYBR/SQ/TRUE fix)
- `_closed_results_pool`: re-added â€” wider pool allowing `missing_real_data` for prior-active rows
- `_is_stale_tracked_position`: re-added â€” detects PATH-style triggered+lost-real-data rows
- `build_stale_tracking_rows`: re-added â€” one stale row per prior-active symbol
- `WATCHLIST_LIFECYCLE_STATES`: re-added `stale_tracking_needs_review`
- `_LIFECYCLE_SORT_PRIORITY`: re-added â€” `active=0, weakening=1, stale=2, waiting=3, watching=4`
- `build_tony_watchlist_rows`: restored `quarantine_symbols` param, stale rows, lifecycle priority sort
- `_is_valid_tony_pick_row`: restored tony_analysis_version guard for priority_label
- `build_results_product_rows`: restored â€” active first, closed without pick_rows exclusion (PATH fix), only waiting_alert picks (no watching-only in Results)
- `collect_health_issues`: restored `stale_symbols` and `missing_tracked_symbols` params
- `find_unreconciled_tracked_symbols`: re-added â€” ledger gap diagnostic
- `build_pick_card_model`: restored watching-only N/A target/stop, `needed_before_entry`, updated status label

**`app.py`**
- Imports: added `build_stale_tracking_rows`, `find_unreconciled_tracked_symbols`
- `_dashboard_context`: re-added `stale_df`, `stale_symbols_list`, `missing_tracked`; passes both to `collect_health_issues`; returns in context dict
- `render_tony_watchlist`: restored quarantine_symbols passthrough, "Stale / Needs review" filter, `stale_tracking_needs_review` lifecycle card handling
- `render_results`: restored `research_snaps` for product cards (active positions no longer disappear on "Today" period filter)
- `render_system_health`: re-added "Tracked position ledger gaps" section

**`tests/test_v27a_regression.py`** (new file, 30 tests in 7 classes)
- `TestV27ADataQualityFilters`: demo/missing/quarantine/bad-DQ/fallback-provider/used-demo hidden from Watchlist
- `TestV27APathLifecycle`: stale detection, stale in Watchlist, not silently dropped, not in Results, derive_pick_phase stays tracking
- `TestV27ALifecycleSortOrder`: active before stale, stale before watching
- `TestV27AResultsLedger`: Results not empty with active positions, active phase, watching-only excluded, active symbols match Watchlist
- `TestV27AUnreconciledDiagnostic`: gap detection, terminal outcome ignored, stale set accounted, no triggered rows
- `TestV27AHealthIssues`: stale and missing_tracked warnings, silent when no gaps
- `TestV27AWatchingOnlyCardModel`: N/A target/stop, needed_before_entry, waiting_for_trigger has real values

### What happened to PATH

PATH had `entry_triggered=1`, `tracking_status=missing_real_data`, `data_source=missing_real_data`. In V27 baseline, `_product_rows_only` excluded `data_source=missing_real_data` rows and there was no stale path â€” so PATH disappeared entirely. After V27A: `_closed_results_pool` allows these rows; `build_stale_tracking_rows` picks PATH up; `build_tony_watchlist_rows` includes it as `stale_tracking_needs_review`. If no stored row exists at all, `find_unreconciled_tracked_symbols` produces a Settings/System Health error.

### Tests/checks run

- `pytest tests/test_v27a_regression.py tests/test_dashboard_helpers.py tests/test_dashboard_theme.py -x -q` â†’ **212 passed**
- `pytest -x -q` â†’ **662 passed**

### Safety

No scoring changes, no trigger-rule changes, no config changes, no broker/paper/live execution, no orders, no data deletion. All changes are dashboard filtering and diagnostic only.

---

## V26D handoff - Results Ledger Source + Unreconciled Symbol Diagnostics

### Current active task

V26D is complete. Results tab now uses the same tracked-position ledger as Watchlist. Missing tracked symbols (PATH-style) produce a health warning instead of disappearing silently. Ledger diagnostic wired into Settings/System Health.

### Changes

- **`find_unreconciled_tracked_symbols(snapshots, *, active_symbols, stale_symbols) -> list[str]`** â€” new public helper in `helpers.py`. Finds `entry_triggered=1` symbols not in active or stale sets and with no terminal outcome/tracking_status. Returns sorted list of gap symbols.
- **`collect_health_issues`** â€” added `missing_tracked_symbols: list[str] | None = None` parameter; appends an `st.error`-level warning when any unreconciled symbols are found.
- **`app.py: _dashboard_context`** â€” computes `missing_tracked` via `find_unreconciled_tracked_symbols(research_snaps, active_symbols=..., stale_symbols=...)` after building stale_df; appends missing_tracked warning to health_issues; returns `missing_tracked` in context dict.
- **`app.py: render_results`** â€” now loads `research_snaps = _load_research_snapshots(repo)` separately from `prepared`; uses `research_snaps` for `build_active_tracking_product_rows` and `build_results_product_rows` (product cards); `prepared` used for period-filtered stats text only. Fixes Results showing 0 cards when active positions exist.
- **`app.py: render_system_health`** â€” added "Tracked position ledger gaps" section: `st.warning` for stale symbols, `st.error` for missing_tracked symbols.

### Tests changed/added

- New `TestV26DResultsLedgerAndDiagnostics` class with 12 tests (appended to `test_dashboard_helpers.py`).
- Import of `find_unreconciled_tracked_symbols` added to test file.

### Files changed

- `src/trading_bot/dashboard/helpers.py`
- `src/trading_bot/dashboard/app.py`
- `tests/test_dashboard_helpers.py`

### Tests/checks run

- `.venv/Scripts/python -m pytest tests/test_dashboard_helpers.py -x -q` â†’ **205 passed**
- `.venv/Scripts/python -m pytest -x -q` â†’ **667 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no data deletion. All changes are dashboard display/filtering and diagnostic only.

---

## V26C handoff - Position Ledger Integrity + Strict Product Filters

### Current active task

V26C is complete. Stale tracking lifecycle added, watching-only cards cleaned up, stale symbols wired into Settings/System Health.

### Changes

- **`WATCHLIST_LIFECYCLE_STATES`** â€” added `"stale_tracking_needs_review"`.
- **`derive_pick_phase`** â€” reverted V26A change: `tracking_status=missing_real_data` stays `"tracking"` (not `"closed"`). Stale symbols now appear in Watchlist, not pushed to Results.
- **`_is_stale_tracked_position`** â€” new private helper: True when `entry_triggered=1`, `tracking_status=missing_real_data`, and an original entry price exists.
- **`build_stale_tracking_rows`** â€” new public function: uses `_closed_results_pool`; returns one row per prior-active symbol with `lifecycle_state=stale_tracking_needs_review`.
- **`_LIFECYCLE_SORT_PRIORITY`** â€” updated: `stale_tracking_needs_review=2`, `waiting_for_trigger=3`, `watching=4`.
- **`build_tony_watchlist_rows`** â€” now includes stale rows (at priority 2); stale symbols excluded from the pick frame.
- **`build_pick_card_model`** â€” for watching-only rows (no `has_planned_entry`): `target="N/A"`, `stop="N/A"`, `risk_reward="N/A"`, `needed_before_entry="Tony has not created an actionable trigger yet."`.
- **`collect_health_issues`** â€” added `stale_symbols: list[str] | None = None` parameter; appends a plain-English warning listing stale symbols when present.
- **`app.py: _dashboard_context`** â€” builds `stale_df` and `stale_symbols_list` before `collect_health_issues`; passes `stale_symbols` to it; returns `stale_df` and `stale_symbols` in context dict.
- **`app.py: render_tony_watchlist`** â€” added "Stale / Needs review" to lifecycle filter dropdown; handles `stale_tracking_needs_review` using `build_tracked_setup_card_model`.

### Tests changed/added

- 6 V26A/V26B tests updated to reflect V26C contract (PATH â†’ Watchlist stale, not Results closed).
- New `TestV26CPositionLedger` class with 16 tests.

### Files changed

- `src/trading_bot/dashboard/helpers.py`
- `src/trading_bot/dashboard/app.py`
- `tests/test_dashboard_helpers.py`

### Tests/checks run

- `.venv/Scripts/python -m pytest -x -q` â†’ **656 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no data deletion. All changes are display/lifecycle filtering only.

---

## V26B handoff - Watchlist Ordering + Results Product Cleanup

### Current active task

V26B is complete. Watchlist ordering, Results cleanup, PATH fix, and quarantine integration are all done.

### Changes

- **`_LIFECYCLE_SORT_PRIORITY`** â€” new module-level dict: `{active: 0, weakening: 1, waiting_for_trigger: 2, watching: 3}`.
- **`build_tony_watchlist_rows`** â€” added `quarantine_symbols: set[str] | None = None` parameter; sorts by lifecycle priority first (active â†’ weakening â†’ waiting_for_trigger â†’ watching), then by time descending; filters quarantined symbols from output.
- **`_is_valid_tony_pick_row`** â€” when `tony_analysis_version` is present in the row, also requires a non-null `tony_priority_label`. Pre-Tony rows (no `tony_analysis_version`) pass through unchanged.
- **`build_results_product_rows`** â€” restructured: builds closed without excluding pick_rows (fixes PATH being blocked by old pick row); only includes `waiting_alert` phase picks (with a real planned entry trigger) in Results â€” plain watching-only rows are excluded.
- **`app.py: render_tony_watchlist`** â€” now passes `quarantine_symbols` from `_dashboard_context` into `build_tony_watchlist_rows`.

### Files changed

- `src/trading_bot/dashboard/helpers.py` â€” `_LIFECYCLE_SORT_PRIORITY`, `build_tony_watchlist_rows` (sort + quarantine), `_is_valid_tony_pick_row` (tony_analysis_version guard), `build_results_product_rows` (PATH fix + watching-only exclusion).
- `src/trading_bot/dashboard/app.py` â€” quarantine_symbols passed to `build_tony_watchlist_rows`.
- `tests/test_dashboard_helpers.py` â€” new `TestV26BWatchlistOrderingAndResultsCleanup` class with 14 tests.

### Tests/checks run

- `.venv/Scripts/python -m pytest -x -q` â†’ **640 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no data deletion. All changes are dashboard display/filtering only.

---

## V26A handoff - Watchlist Data Quality + Prior-Active Lifecycle + Watching-Only Label

### Current active task

V26A is complete. Three gaps from V26 are closed:
1. HCP/SMAR/CYBR/SQ/TRUE-style symbols with demo, fallback, or bad-DQ data are now excluded from Tony Watchlist.
2. PATH-style prior-active symbols (tracking_status=missing_real_data + entry_triggered=1) now appear in Results as closed rather than vanishing silently.
3. Watching-only cards (no entry trigger) now read "Watching only â€” no actionable trigger yet" instead of "Watching only".

### Changes

- **`_BAD_DQ_VALUES`** â€” new module-level frozenset: `{"missing_real_data", "fallback_data", "intraday_fallback_demo", "demo_data"}`.
- **`_product_rows_only`** â€” strengthened: also filters `used_demo_data=1`, bad `tony_data_quality_read`, and snapshot_provider containing "demo" or "fallback".
- **`_closed_results_pool`** â€” new function: wider pool for closed results; allows prior-active rows (entry_triggered=1) even if missing_real_data, but always excludes demo_generated / legacy_unknown / used_demo_data.
- **`derive_pick_phase`** â€” now returns `"closed"` when `tracking_status == "missing_real_data"` (in addition to the existing `"invalidated"` check), preventing data-lost active symbols from staying in tracking.
- **`_is_valid_closed_result_row`** â€” now uses `_effective_tracking_target()` and `_effective_tracking_stop()` instead of `row.get("target")` / `row.get("stop")`, so prior-active rows with only `original_target_price` / `original_stop_price` are accepted as valid closed results.
- **`build_closed_results_product_rows`** â€” now uses `_closed_results_pool` instead of `_product_rows_only` as its data pool.
- **`build_pick_card_model`** â€” `status` for no-trigger rows changed from `"Watching only"` to `"Watching only â€” no actionable trigger yet"`.

### Files changed

- `src/trading_bot/dashboard/helpers.py` â€” all 7 changes above.
- `tests/test_dashboard_helpers.py` â€” new `TestV26ADataQualityAndLifecycle` class with 16 tests.

### Tests/checks run

- `.venv/Scripts/python -m pytest -x -q` â†’ **626 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no data deletion. All changes are dashboard display/lifecycle filtering only.

---

## V26 handoff - Position Lifecycle + Unified Watchlist + Results Filters

### Current active task

V26 is complete. Tony Picks and Active Tracking are merged into one "Tony Watchlist" tab. Symbols with `tracking_status=invalidated` now surface in Results (not silently vanish). All Results filters return correct visible cards.

### Changes

- **`WATCHLIST_LIFECYCLE_STATES`** â€” new tuple constant in `helpers.py`: `watching`, `waiting_for_trigger`, `active`, `weakening`, `invalidated`, `closed`, `expired`.
- **`derive_pick_phase`** â€” now returns `"closed"` when `tracking_status == "invalidated"` or `reassessment_label == "invalidated"`, preventing active symbols from vanishing silently.
- **`_watchlist_lifecycle_state`** â€” new private helper mapping a row to its lifecycle state string.
- **`build_tony_watchlist_rows`** â€” new public function that combines pick rows + active tracking rows into one deduped list with a `lifecycle_state` column. Active tracking wins over pick when a symbol appears in both.
- **`app.py: render_tony_watchlist`** â€” new render function; shows pick cards for watching/waiting rows, tracking cards for active/weakening rows; lifecycle filter dropdown.
- **`app.py: main()`** â€” tabs changed from 5 ("Home", "Tony Picks", "Active Tracking", "Results", "Settings") to 4 ("Home", "Tony Watchlist", "Results", "Settings / System Health").
- **`app.py: render_home`** â€” Home stat grid now shows "Tony Watchlist" (combined count) instead of separate "Tony Picks".

### Files changed

- `src/trading_bot/dashboard/helpers.py` â€” `WATCHLIST_LIFECYCLE_STATES`, `derive_pick_phase` fix, `_watchlist_lifecycle_state`, `build_tony_watchlist_rows`.
- `src/trading_bot/dashboard/app.py` â€” `render_tony_watchlist`, merged tab list, Home stat grid, import added.
- `tests/test_dashboard_helpers.py` â€” 21 new V26 tests; `build_tony_watchlist_rows` imported.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **611 passed**

### Safety

No scoring changes, no trigger rule changes, no config changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All changes are dashboard display/lifecycle only.

---

## V25 handoff - Replay Strategy Proposal

### Current active task

V25 is complete. `after-market-review` now builds and saves a research-only proposal replay that compares the current baseline replay against any approved strategy proposal. Approved never means applied.

### Changes

- **`_MIN_CONCLUSIVE_FOR_PROPOSAL_VALIDATION = 3`** â€” local threshold constant in `cli.py`.
- **`_build_proposal_replay(report_date, proposal, baseline_replay)`** â€” three paths:
  - `no_approved_suggestions`: no approved decisions exist â†’ replay skipped.
  - `insufficient_data`: approved decisions exist but `total_conclusive == 0` â†’ "proposal cannot be validated yet."
  - `validated` / `preliminary`: has conclusive data; attaches each approved suggestion with baseline setup rates as context. `validated=True` when `total_conclusive >= 3`.
- **`_build_proposal_replay_markdown(replay)`** â€” markdown with header, validation status, baseline stats + setup rates table, approved suggestions list.
- **`run_after_market_review`** â€” step 7: builds replay from `analytics_result["replay_summary"]` (already computed) and `proposal`; saves `proposal_replay.json` + `proposal_replay.md`; prints validation status; adds to `files_created` (now 9 total); adds `proposal_replay` to return dict.

### Files changed

- `src/trading_bot/cli.py` â€” `_MIN_CONCLUSIVE_FOR_PROPOSAL_VALIDATION`, `_build_proposal_replay`, `_build_proposal_replay_markdown`, updated `run_after_market_review`.
- `tests/test_outcome_analytics.py` â€” 7 new V25 tests + `_amr_args_v25` / `_baseline_replay_with_conclusive` helpers; 3 existing file-count assertions updated (7â†’9).

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **590 passed**

### Safety

No scoring changes, no trigger rule changes, no config/default_config.yaml changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. Every replay carries `research_only: True` and a `not_applied_note`. Approved does not mean applied.

---

## V24 handoff - Strategy Proposal Package

### Current active task

V24 is complete. `after-market-review` now builds and saves a research-only strategy proposal derived from approved suggestion decisions. Approved never means applied.

### Changes

- **`_next_proposed_version(current)`** â€” simple version bumper: "v1"â†’"v1.1", "v1.1"â†’"v1.2", "v2"â†’"v2.1".
- **`_build_strategy_proposal(report_date, decisions, current_version)`** â€” filters decisions to `status=="approved"`, computes `proposed_version` (bumped only when approved suggestions exist), returns `{current_version, proposed_version, approved_count, approved_suggestions, not_applied_note, research_only}`.
- **`_build_strategy_proposal_markdown(proposal)`** â€” markdown with "Strategy Proposal â€” YYYY-MM-DD" header, approved suggestions list, or "No strategy proposal today." when empty.
- **`run_after_market_review`** â€” step 6: builds proposal from loaded decisions, saves `strategy_proposal.json` + `strategy_proposal.md`, prints summary, adds to `files_created` (now 7 total), adds `strategy_proposal` to return dict.

### Files changed

- `src/trading_bot/cli.py` â€” `_next_proposed_version`, `_build_strategy_proposal`, `_build_strategy_proposal_markdown`, updated `run_after_market_review`.
- `tests/test_outcome_analytics.py` â€” 6 new V24 tests + `_approved_decisions` helper; 3 existing V21/V22 file-count tests updated (5â†’7).

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **583 passed**

### Safety

No scoring changes, no trigger rule changes, no config/default_config.yaml changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. Every proposal carries `research_only: True` and a `not_applied_note` stating "Approved does not mean applied."

---

## V23 handoff - Human Approval Gate

### Current active task

V23 is complete. Rule suggestions can now be marked approved, rejected, applied_later, or needs_review via `record-suggestion-decision`. Decisions are stored in `reports/suggestion_decisions.json` and reflected in the approval package on the next `after-market-review` run. Approved never means applied.

### Changes

- **`_suggestion_key(suggestion, strategy_version)`** â€” 12-char sha256 key for stable suggestion identification across dates.
- **`_load_suggestion_decisions(output_dir)`** â€” reads `reports/suggestion_decisions.json`, returns dict keyed by suggestion_key.
- **`_save_suggestion_decision(output_dir, record)`** â€” upserts a decision record by suggestion_key.
- **`run_record_suggestion_decision(args)`** â€” reads the date's `approval_package.json`, looks up suggestion at `--index` (1-based), writes decision record with `{status, decided_at, note, not_applied: True}` to `suggestion_decisions.json`. Prints "Approved does not mean applied."
- **`_build_approval_package`** â€” now accepts optional `decisions` dict; enriches each suggestion with `status`, `decided_at`, `decision_note`, `not_applied` from prior decisions; returns `pending_count` (needs_review only) and new `decided_count`.
- **`run_after_market_review`** â€” loads decisions before building the approval package so prior decisions appear in the next day's package.
- **`record-suggestion-decision` CLI command** â€” `--date`, `--index` (required), `--status` (required, choices: approved/rejected/needs_review/applied_later), `--note`, `--output-dir`.

### Files changed

- `src/trading_bot/cli.py` â€” `hashlib` import; parser entry; `_suggestion_key`, `_load_suggestion_decisions`, `_save_suggestion_decision`, `run_record_suggestion_decision`; updated `_build_approval_package`; updated `run_after_market_review`; `main()` wire-up.
- `tests/test_outcome_analytics.py` â€” 8 new V23 tests + `_write_approval_package` helper.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **577 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. Every decision record carries `not_applied: True`. The `not_applied_note` in the package explicitly states "Approved does not mean applied." Decisions only update the JSON ledger.

---

## V22 handoff - Approval Package

### Current active task

V22 is complete. `after-market-review` now builds and saves a research-only approval package for pending rule suggestions.

### Changes

- **`_build_approval_package(report_date, suggestions, strategy_version)`** â€” assembles the approval dict: filters to `needs_review` suggestions, includes `pending_count`, `not_applied_note`, `research_only: True`.
- **`_build_approval_package_markdown(report_date, package)`** â€” builds readable markdown with numbered suggestion entries (confidence, reason, status, version) or "No approval items today." when empty.
- **`run_after_market_review`** â€” extracts suggestions from `eod_result["tony_self_review"]["rule_suggestions"]`, builds package, saves `approval_package.json` + `approval_package.md`, prints summary, adds both to `files_created` (now 5 total), adds `"approval_package"` to return dict.
- No suggestions auto-applied; all remain `status: needs_review`.

### Files changed

- `src/trading_bot/cli.py` â€” `_build_approval_package`, `_build_approval_package_markdown`, updated `run_after_market_review`.
- `tests/test_outcome_analytics.py` â€” 6 new V22 tests + `_sample_eod_with_suggestions` helper; updated 2 V21 tests (file count 3â†’5, added approval file assertions).

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **570 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All suggestions remain `needs_review`; the `not_applied_note` field explicitly states nothing has been applied.

---

## V21B handoff - Report Cleanup Consistency

### Current active task

V21B is complete. EOD/report wording now clearly separates raw rows, deduped positions, conclusive outcomes, and future-pending rows. NaN values render as N/A in tables. Negative conclusive count is prevented.

### Changes

- **`outcomes.py: build_tony_self_review`**
  - `conclusive = max(0, triggered - insufficient)` â€” prevents a negative count when insufficient > triggered due to data anomalies.
  - "conclusive row(s)" in needs_more_data â†’ "rows with a finalized outcome" (clearer: this is triggered-minus-insufficient, not the rate-eligible conclusive set).
  - `{insufficient_count} triggered row(s) labeled insufficient_future_data` â†’ `{insufficient_count} row(s) labeled insufficient_future_data` (not all of these are triggered; the label applies to the outcome window, not the trigger state).

- **`cli.py: _print_dataframe`** â€” `data.fillna("N/A").to_string()` replaces NaN with N/A in all report tables.

- **`cli.py: run_eod_report`**
  - Added `"Raw rows = full stored history; product rows = deduped, current-state-only view."` to the reconciliation section header.
  - Expanded data-quality notes with a row-type guide:
    - `raw rows` = all stored candidate snapshot history
    - `product rows` = deduped, current-state-only view
    - `insufficient_future_data` = outcome window still open, not a failure
    - `conclusive rows` = rows eligible for target/stop/partial/failure rate calculations

### Files changed

- `src/trading_bot/analytics/outcomes.py` â€” `build_tony_self_review`: `max(0, ...)` guard, wording fixes.
- `src/trading_bot/cli.py` â€” `_print_dataframe` NaN fix; EOD reconciliation note; data-quality row-type guide.
- `tests/test_outcome_analytics.py` â€” 5 new V21B tests.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **564 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All changes are display/wording only.

---

## V21A handoff - After-Hours Review Guard

### Current active task

V21A is complete. `after-market-review` now detects whether the current ET time is within regular market hours (9:30â€“16:00 weekdays) and skips live snapshot refresh by default when outside, preventing stale intraday loops.

### Changes

- **`_is_within_regular_market_hours(now=None)`** â€” new helper in `cli.py`. Returns True only for weekday 9:30â€“16:00 ET. No holiday calendar; weekends always treated as outside.
- **`after-market-review`** guard logic (priority order):
  1. `--skip-update-snapshots` â†’ always skip (unchanged)
  2. `--force-update-snapshots` â†’ always run, even outside hours
  3. Outside market hours â†’ skip + print `"Outside market hours; skipping live snapshot refresh. Using stored close/tracking data."`
  4. Inside market hours â†’ run normally
- Return dict gains `market_hours_active` and `snapshot_refresh_ran` for testability.
- `--force-update-snapshots` flag added to `after-market-review` parser.
- `update-snapshots` command behavior is **unchanged**.

### Files changed

- `src/trading_bot/cli.py` â€” `after-market-review` parser (`--force-update-snapshots`); `_is_within_regular_market_hours`; updated guard in `run_after_market_review`.
- `tests/test_outcome_analytics.py` â€” 10 new V21A tests (outside-hours skip, force override, inside-hours normal, skip-flag priority, report files still created, helper unit tests).

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **559 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. The guard only controls whether `update-snapshots` is called; the EOD report and analytics always run.

---

## V21 handoff - After-Market Review Package

### Current active task

V21 is complete. A single `after-market-review` CLI command now runs the full post-session review in one step: update-snapshots â†’ EOD report â†’ real-only outcome analytics â†’ save reports to `reports/YYYY-MM-DD/`.

### Changes

- **`after-market-review` CLI command** added to `build_parser()` with `--config`, `--date`, `--skip-update-snapshots`, `--output-dir` flags.
- **`run_after_market_review(args)`** â€” calls `run_update_snapshots`, `run_eod_report`, and `run_outcome_analytics` in sequence; saves three files:
  - `eod_report.json` â€” full EOD report return dict (includes memory, self-review, suggestions, strategy version, replay, reconciliation)
  - `eod_report.md` â€” formatted markdown built from the return dict
  - `outcome_analytics.json` â€” slim outcome analytics return dict
  - Prints file paths to stdout.
- **`_build_eod_report_markdown(report_date, eod)`** â€” builds human-readable markdown from the eod-report dict; sections: Operational Summary, EOD Reconciliation, Tony Self-Review, Rule Suggestions, Strategy Version, Replay Summary.
- Uses America/New_York market date by default; `--date` overrides.
- Real-only filtering is always enforced for `outcome-analytics` step.
- Suggestions remain `status: needs_review` â€” nothing is auto-applied.

### Files changed

- `src/trading_bot/cli.py` â€” `after-market-review` parser; `run_after_market_review`; `_build_eod_report_markdown`; `main()` wire-up.
- `tests/test_outcome_analytics.py` â€” 8 new V21 tests + `_sample_eod_result()` helper.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **549 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All suggestions remain `needs_review` and are never auto-applied. Report files are read-only JSON/markdown artifacts.

---

## V20 handoff - Backtest Replay Foundation

### Current active task

V20 is complete. `eod-report` now prints a research-only replay summary that groups real-only outcome rows by setup_category and reports triggered/target/stop/partial/insufficient counts with rates computed on conclusive rows only.

### Changes

- **`build_replay_summary(rows, strategy_version)`** â€” new standalone function in `outcomes.py`. Groups by `setup_category`, computes per-setup counts and rates (target_rate, stop_rate on conclusive rows only). Flags `insufficient_future_data` rows in notes without treating them as failures. Returns `strategy_version`, `total_rows`, `total_triggered`, `total_conclusive`, `total_insufficient_future_data`, `setups` list, `notes` list.
- **`_empty_replay_summary(strategy_version)`** â€” zero-value fallback for empty input.
- **`OutcomeAnalytics.replay_summary(strategy_version)`** â€” convenience method on the dataclass.
- **`eod-report`** prints a "Replay summary" section and includes `replay_summary` in the return dict.

### Files changed

- `src/trading_bot/analytics/outcomes.py` â€” `build_replay_summary`, `_empty_replay_summary`, `replay_summary()` method.
- `src/trading_bot/analytics/__init__.py` â€” exported `build_replay_summary`.
- `src/trading_bot/cli.py` â€” imported `build_replay_summary`; replay print section in `run_eod_report`; added `"replay_summary": replay` to return dict.
- `tests/test_outcome_analytics.py` â€” imported `build_replay_summary`; 6 new V20 tests.

### Tests/checks run

- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **541 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. Replay is strictly read-only and rates are never auto-applied.

---

## V19 handoff - Strategy Versioning Foundation

### Current active task

V19 is complete. Rule suggestions now carry a strategy version label and a full strategy version report is included in the EOD report output and return dict.

### Changes

- **`CURRENT_STRATEGY_VERSION = "v1"`** and **`SUGGESTION_STATUSES`** constants added to `outcomes.py`.
- **`generate_tony_rule_suggestions()`** now accepts an optional `strategy_version` parameter (defaults to `CURRENT_STRATEGY_VERSION`). Every suggestion dict includes `"strategy_version"`.
- **`build_strategy_version_report(suggestions, version)`** â€” new function that returns `current_version`, `pending_suggestions`, `status_counts`, the full suggestions list, and a plain-English note. Never auto-applies anything.
- **`eod-report`** prints a "Strategy version" section (version, pending suggestion count, status breakdown, note) and includes `strategy_version_report` in the return dict.

### Files changed

- `src/trading_bot/analytics/outcomes.py` â€” constants, `generate_tony_rule_suggestions` signature, `build_strategy_version_report`, `_no_data_suggestion` updated.
- `src/trading_bot/analytics/__init__.py` â€” exported `CURRENT_STRATEGY_VERSION`, `SUGGESTION_STATUSES`, `build_strategy_version_report`.
- `src/trading_bot/cli.py` â€” imported new symbols; strategy version print + return in `run_eod_report`.
- `tests/test_outcome_analytics.py` â€” imported new symbols; 6 new V19 tests.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` â†’ **39 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **535 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, no data deletion. All suggestions remain `status: needs_review` and are never auto-applied.

## V18A handoff - Active vs Future Outcome Wording

### Current active task

V18A is complete. Tony self-review and EOD report now correctly distinguish same-day active tracking from future outcome windows.

### Changes

- **`build_tony_self_review`**: `tomorrow_watch` now uses the reconciliation `deduped_active_positions` for the carry-over count (one per symbol), while the raw active row count from tracking data drives the note trigger. Raw triggered rows are exposed separately. `insufficient_future_data` rows are now called out in `needs_more_data` as "outcome windows are still open; these are not failures" rather than silently disappearing. Added same-day summary fields: `active_symbols`, `deduped_active_positions`, `raw_triggered_rows`, `waiting_picks`, `pending_triggers`.
- **`generate_tony_rule_suggestions`**: Now excludes `insufficient_future_data` rows from rate calculations. Only rows with conclusive outcomes (target/stop/partial/failure) count toward the denominator. If not enough conclusive rows exist, the no-data fallback message explains how many are still waiting.
- **`eod-report` self-review print section**: Added "Same-day summary" block showing deduped active positions, active symbols, waiting picks, raw triggered rows, and pending triggers.
- **`_empty_self_review`**: Added the new summary fields with zero defaults.

### Files changed

- `src/trading_bot/analytics/outcomes.py` â€” `build_tony_self_review`, `generate_tony_rule_suggestions`, `_empty_self_review`.
- `src/trading_bot/cli.py` â€” self-review print section in `run_eod_report`.
- `tests/test_outcome_analytics.py` â€” 4 new V18A tests.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` â†’ **33 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **529 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion.

## V16B handoff - Date Consistency for Reports

### Current active task

V16B is complete. `eod-report` and `outcome-analytics` now use the same America/New_York market-date filtering everywhere.

- **`outcome-analytics --date YYYY-MM-DD`** added. Filters snapshots by ET market date. Prints `Report date: YYYY-MM-DD America/New_York`. Overrides `--today` when both are given.
- **`eod-report --date` watch-run scoping fixed.** Previously used `latest_watch_run()` (globally newest), which caused cross-date contamination. Now uses `_watch_run_summary_for_date()` to filter recent watch runs by ET `started_at` date and sum `cycles_completed` across all runs on that date. A date with no watch runs correctly reports 0 cycles.
- **`run_outcome_analytics` now returns a dict** (`snapshots_reviewed`, `symbols`, `date_filter`) for testability.

### Files changed

- `src/trading_bot/storage/repositories.py` â€” added `recent_watch_runs(limit=100)`.
- `src/trading_bot/cli.py` â€” added `--date` to `outcome-analytics` argparser; updated `run_outcome_analytics` to handle `--date`, apply the ET mask post-`prepared()`, print date header, return result dict; added `_watch_run_summary_for_date()` helper; replaced `repo.latest_watch_run()` in `run_eod_report` with the date-scoped helper.
- `tests/test_outcome_analytics.py` â€” added `_make_dummy_tony()` helper and 4 new V16B tests.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` â†’ **29 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **525 passed**

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion. Stored timestamps remain UTC.

## V18 handoff - Tony Rule Suggestions

### Current active task

V18 is complete. Tony self-review now includes `rule_suggestions` â€” plain-English research-only scoring/filter ideas derived from real-only outcome rows. Suggestions are never applied automatically; each carries a confidence level (`low`/`medium`/`high`) and `status: needs_review`. A no-data fallback is returned when fewer than 3 triggered rows exist. The `eod-report` prints suggestions under "Rule suggestions (research-only, not applied automatically)". Suggestions are stored inside the Tony learning event payload alongside the memory summary.

### Files changed

- `src/trading_bot/analytics/outcomes.py` â€” added `generate_tony_rule_suggestions()`, `_no_data_suggestion()`, `_MIN_TRIGGERED_FOR_SUGGESTION`; added `rule_suggestions` field to `build_tony_self_review()` return and `_empty_self_review()`.
- `src/trading_bot/analytics/__init__.py` â€” exported `generate_tony_rule_suggestions`.
- `src/trading_bot/cli.py` â€” `eod-report` prints rule suggestions with confidence label and reason.
- `tests/test_outcome_analytics.py` â€” imported `generate_tony_rule_suggestions`; added 5 new tests.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` â†’ **25 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **521 passed**

### Suggestion logic

| Condition | Suggestion | Confidence |
|-----------|-----------|------------|
| Triggered < 3 (total) | No rule changes suggested yet | low |
| Setup target_rate â‰¥ 67%, triggered â‰¥ 2 | Consider prioritizing that setup | medium (high if â‰¥ 5 rows and â‰¥ 80%) |
| Setup stop_rate â‰¥ 67%, triggered â‰¥ 2 | Consider raising score threshold / reducing frequency | medium (high if â‰¥ 5 rows and â‰¥ 80%) |
| No setup meets threshold | Patterns not consistent enough | low |

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion. Suggestions have `status: needs_review` and are never auto-applied.

## V17 handoff - Tony Self-Review Report

### Current active task

V17 is complete. `eod-report` now prints a plain-English Tony self-review section after the Tony memory summary. The self-review is derived from real-only outcome rows using V16 memory summary data and V15.9 reassessment labels. It covers: strongest setup, weakest setup, what worked, what failed, what needs more data, and tomorrow watch notes. The self-review is also stored in the Tony learning event payload inside `memory_summary.self_review`.

### Files changed

- `src/trading_bot/analytics/outcomes.py` â€” added `build_tony_self_review()` standalone function and `_empty_self_review()` helper; added `tony_self_review()` method on `OutcomeAnalytics`.
- `src/trading_bot/analytics/__init__.py` â€” exported `build_tony_self_review`.
- `src/trading_bot/cli.py` â€” imported `build_tony_self_review`; `eod-report` now computes and prints the self-review section; includes `tony_self_review` in the return payload; stores self-review inside the Tony learning event `memory_summary` payload.
- `tests/test_outcome_analytics.py` â€” imported `build_tony_self_review`; added four new tests: `test_tony_self_review_from_sample_rows`, `test_tony_self_review_empty_day_fallback`, `test_tony_self_review_real_only_filtering`, `test_eod_report_includes_self_review`.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q` â†’ **20 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` â†’ **516 passed**

### Self-review output structure

```
Tony self-review:
  Research only. No scoring changes. No trigger changes. No trading behavior changes.
  Strongest setup: <best_setup_note from V16 memory>
  Weakest setup: <worst_setup_note from V16 memory>
  What worked:
    - <setup>: N target hit(s)... out of N triggered row(s).
  What failed:
    - <setup>: N stop or failure outcome(s) out of N triggered row(s).
  What needs more data:
    - <setup>: only N row(s) today â€” not enough context to read direction.
    - <setup>: reassessment flagged as needs_review â€” check current conditions.
  Tomorrow watch:
    - N active position(s) carry over â€” check reassessment labels at next open.
    - N pending trigger(s) still waiting â€” watch for intraday trigger levels.
    - N setup(s) flagged weakening â€” monitor for further deterioration.
```

### Known limitations

- Strongest/weakest setup notes are derived from the same `_best_worst_setup_notes` logic introduced in V16 and are only as meaningful as the current day's real-only sample size.
- The self-review is stored inside `memory_summary.self_review` in the Tony learning event payload, not in a separate dedicated field.

### Safety

No scoring changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion.

## V16A handoff - Market-Date Fix

### Current active task

V16A is complete. `eod-report`, `outcome-analytics --today`, and the daily Tony memory summary now use the America/New_York market date by default instead of the UTC calendar date.

### Root cause

Daily reporting code was mixing UTC-date string slicing with local-market expectations. That caused after-hours or near-midnight UTC rows to fall onto the wrong â€œtodayâ€ bucket for `eod-report`, `outcome-analytics --today`, and the Tony memory summary.

### Files changed

- `src/trading_bot/analytics/outcomes.py` - added ET market-date helpers and switched `today=True` filtering from UTC date slicing to parsed America/New_York market-date matching.
- `src/trading_bot/analytics/__init__.py` - exported the ET market-date helpers.
- `src/trading_bot/cli.py` - `eod-report` now defaults to the ET market date, filters snapshots/events/update timestamps by ET market date, keeps explicit `--date` overrides, and prints `Report date: YYYY-MM-DD America/New_York`.
- `tests/test_outcome_analytics.py` - added ET boundary coverage, `eod-report` default-date coverage, explicit override coverage, and Tony memory date-alignment coverage.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v16a_outcomes` -> **16 passed**

### Known limitations

- This change only updates daily filtering/report semantics. Stored timestamps remain UTC and existing raw history is unchanged.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion, and no data deletion.

## V16 handoff - Tony Memory Engine Foundation

### Current active task

V16 is complete. `eod-report` now builds a daily Tony memory summary from real-only outcome rows and stores the same research-only summary in the existing Tony learning event payload for later review.

### Root cause

Tony already stored raw outcome rows and could print grouped analytics, but there was no compact daily research memory artifact summarizing what triggered, what stayed active vs closed, what hit target/stop/partial outcomes, how reassessment labels were distributed, and what data-quality exclusions shaped that view.

### Files changed

- `src/trading_bot/analytics/outcomes.py` - added `daily_tony_memory_summary()` / `build_daily_tony_memory_summary()` plus setup, triggered, active/closed, reassessment, best/worst, and data-quality summary helpers.
- `src/trading_bot/analytics/__init__.py` - exported the new daily memory summary helper.
- `src/trading_bot/cli.py` - `eod-report` now prints a Tony memory summary section, returns it in the report payload, and stores it through the existing Tony learning event path; outcome-analytics learning events now also carry the same summary payload when applicable.
- `src/trading_bot/storage/database.py` - made additive migration loops idempotent against already-present columns so local DB initialization no longer fails on duplicate-column retries.
- `src/trading_bot/tony/events.py` - extended `record_tony_learning_updated()` payload to accept an optional `memory_summary`.
- `src/trading_bot/dashboard/helpers.py` - fixed boolean-index alignment when product filtering receives non-contiguous snapshot indexes.
- `tests/test_outcome_analytics.py` - added daily memory summary coverage for counts, real-only filtering, demo/legacy exclusion, reassessment rollups, raw-history-preserved notes, and no-deletion behavior.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v16_outcomes` -> **13 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v16_outcomes_fix` -> **13 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py -q --basetemp .pytest_tmp_v16_dashboard_helpers` -> **128 passed**
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` -> **509 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli eod-report --config config/default_config.yaml` -> succeeded
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml --real-only --today` -> succeeded

### Known limitations

- Best/worst setup notes are intentionally labeled preliminary and are only as useful as the current dayâ€™s real-only sample size.
- The memory summary is stored in the existing Tony event/reporting path, not in a new dedicated memory table.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no orders, no demo-data inclusion in Tony memory, no active-entry rewrites, and no raw-history deletion.

## V15.9 handoff - Tony Reassessment Labels

### Current active task

V15.9 is complete. Active tracked research setups now receive deterministic Tony reassessment labels during the existing refresh path: `still_valid`, `weakening`, `invalidated`, or `needs_review`.

### Root cause

Active Tracking already refreshed current price, research P/L, and status, but it had no compact research-only interpretation of whether the tracked setup still looked intact, was weakening, had effectively invalidated, or simply lacked enough current real context for a clean read.

### Files changed

- `src/trading_bot/storage/database.py` - added additive `reassessment_label` snapshot column.
- `src/trading_bot/storage/repositories.py` - repository updates now accept `reassessment_label`.
- `src/trading_bot/snapshots/active_tracking.py` - added deterministic reassessment derivation and stored label/note updates during active tracking refresh; tracked summary counts now include reassessment buckets.
- `src/trading_bot/snapshots/__init__.py` - exported reassessment constants/helper.
- `src/trading_bot/tony/events.py` - enabled `tracked_setup_updated` by default and expanded its payload/message with reassessment counts.
- `tests/test_v15_8_active_tracking.py` - label assignment, fixed entry preservation, demo-skip behavior, migration/repository support, and no-deletion coverage.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_v15_8_active_tracking.py -q --basetemp .pytest_tmp_v159_tracking` -> **23 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v159_outcomes` -> **10 passed**

### Known limitations

- Reassessment currently renders through the existing `reassessment_note` path on Active Tracking; there is not yet a dedicated visual pill/field for `reassessment_label`.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no order placement, no demo-data injection, no active-entry rewrites, and no snapshot deletion.

## V15.8C handoff - EOD Data Reconciliation

### Current active task

V15.8C is complete. `eod-report` now prints a raw-vs-product reconciliation section that proves dashboard dedupe/hiding changes visibility only and does not delete raw candidate snapshot history. Settings / System Health also includes a compact reconciliation summary.

### Root cause

The product dashboard intentionally hides duplicates, stale history rows, and incomplete product rows, but there was no explicit report proving those raw rows still existed in storage. That left the system looking lossy even though the database retained the full history.

### Files changed

- `src/trading_bot/analytics/outcomes.py` - added `classified_snapshots()` for raw history classification before active filters.
- `src/trading_bot/dashboard/helpers.py` - added `summarize_product_reconciliation()` for raw snapshot rows vs current product-view counts.
- `src/trading_bot/cli.py` - `eod-report` now prints reconciliation counts and an explicit raw-history-preserved note.
- `src/trading_bot/dashboard/app.py` - Settings / System Health now shows a small reconciliation summary.
- `tests/test_outcome_analytics.py` - reconciliation counts, raw-vs-product distinction, and no-deletion coverage.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v158c_outcomes` -> **10 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py -q --basetemp .pytest_tmp_v158c_helpers` -> **128 passed**

### Known limitations

- The compact Settings reconciliation summary uses the current research snapshot slice already loaded by the dashboard, not a separate full raw-history table dump. The full raw proof remains the CLI `eod-report` output and the legacy developer views.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no order placement, no demo-data injection, no snapshot deletion, and no API key output.

## V15.8B handoff - Product Dashboard Semantics: Entry Triggers, Current Positions, Closing Price, Results Rehaul

### Current active task

V15.8B code/test work is complete. Main dashboard product views now use entry-trigger vs active-entry semantics, after-hours closing-price labeling, deduped current-state Results filters/cards, and short complete Home preview sentences. Focus next on full Windows command run + manual browser verification.

### Root cause

Even after V15.8A symbol dedupe, the product layer was still exposing raw/internal semantics: `Planned entry` wording implied buy-now behavior, Home preview text clipped awkwardly, Results still behaved like a count summary instead of a current clean product state, and after-hours prices were not clearly labeled as closing prices.

### Files changed

- `src/trading_bot/dashboard/helpers.py` - added entry-trigger distance/risk-reward/trigger-explanation helpers; upgraded pick/tracking card models; added current-state Results row/filter/card/count helpers; aligned Results summary counts with deduped product semantics.
- `src/trading_bot/dashboard/theme.py` - changed visible labels to `Entry trigger`; preview cards use complete short sentences; tracking cards use dynamic current/closing price labels; added Results stock-card renderer and expanded summary bubbles.
- `src/trading_bot/dashboard/app.py` - Tony Picks / Active Tracking captions now explain trigger and risk/reward semantics; Results now renders deduped filters plus actual stock cards from current product rows.
- `tests/test_dashboard_helpers.py`, `tests/test_dashboard_theme.py` - added V15.8B coverage for trigger wording, trigger distance/explanations, fixed active entry + latest closing/current price, risk/reward fallback, Results filters/cards/counts, and no `NaN` / `unknown` product strings.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py tests/test_dashboard_theme.py -q --basetemp .pytest_tmp_v158b_focus` -> **140 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_outcome_analytics.py -q --basetemp .pytest_tmp_v158b_outcomes` -> **8 passed**

### Known limitations

- Full `run_tests.ps1`, CLI report commands, and `run_dashboard.ps1` have not yet been rerun for V15.8B in this handoff entry.
- Manual browser click-through is still pending for Home, Tony Picks, Active Tracking, and Results.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no order placement, no demo-data injection into product views, no snapshot deletion, and no API key output.

## V15.8 handoff - Freeze Original Plan + Active Tracking Fields

## V15.8A handoff - One Active Position Per Symbol + Planned vs Active Entry Cleanup

### Current active task

V15.8A complete. Main product dashboard views now collapse raw snapshot history into one current product card per symbol. The first valid triggered research entry stays fixed for Active Tracking, and later rows only refresh live tracking fields for that same symbol. **488 tests passed.**

### Root cause

Home, Tony Picks, Active Tracking, and Results were rendering and counting raw snapshot rows directly. Repeated watch cycles therefore surfaced duplicate symbols, stale planned-entry rows, incomplete triggered rows, and still-active counts that did not match visible active cards.

### Files changed

- `src/trading_bot/dashboard/helpers.py` - symbol-level product-row builders for Tony Picks and Active Tracking; fixed-entry anchor + latest-live-field overlay; stricter product-row filtering; results still-active alignment; planned vs active entry card fields.
- `src/trading_bot/dashboard/app.py` - product tabs and Home now consume deduped symbol-level rows; pending alert count on Home is symbol-level.
- `src/trading_bot/dashboard/theme.py` - pick/tracking cards now separate Planned entry, Active entry/Tracked from, and Current price.
- `tests/test_dashboard_helpers.py`, `tests/test_dashboard_theme.py` - dedupe/fixed-entry/latest-price/NaN cleanup/results-alignment coverage.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - updated.

### Tests/checks run

- `git diff --check`
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` -> **488 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_dashboard_helpers.py tests/test_dashboard_theme.py -q --basetemp .pytest_tmp_dashboard` -> **130 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_v15_8_active_tracking.py -q --basetemp .pytest_tmp_v158` -> **17 passed**
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli eod-report --config config/default_config.yaml`
- `$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml --real-only --today`
- `powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1` -> Streamlit startup verified at `http://localhost:8501`

### Known limitations

- Full manual browser click-through was not completed from this terminal session. Startup is verified; visual tab-by-tab inspection is still recommended.

### Safety

No scoring logic changes, no trigger rule changes, no broker/paper/live execution changes, no trade placement, no demo data injection, no history deletion, and no API key output.

### Current active task

V15.8 complete. Frozen original plan on trigger; live research tracking fields refresh during `update-snapshots`. **480 tests passed.**

### New tracking fields (nullable on `candidate_snapshots`)

`original_entry_price`, `original_target_price`, `original_stop_price`, `original_plan_captured_at`, `tracking_status`, `tracking_started_at`, `current_price`, `current_price_at`, `research_unrealized_pl_pct`, `current_target_price`, `current_stop_price`, `reassessment_note`, `last_reassessed_at`, `invalidation_reason`, `time_active_minutes`, `pick_phase`

### Files changed

- `src/trading_bot/storage/database.py` â€” V15.8 migrations
- `src/trading_bot/storage/repositories.py` â€” allow tracking field updates
- `src/trading_bot/snapshots/active_tracking.py` â€” **NEW** freeze/refresh/status logic
- `src/trading_bot/snapshots/__init__.py` â€” exports
- `src/trading_bot/cli.py` â€” freeze + refresh in `update-snapshots`
- `src/trading_bot/tony/events.py` â€” `tracked_setup_updated` event
- `src/trading_bot/dashboard/helpers.py` â€” card model uses frozen/current fields
- `src/trading_bot/dashboard/theme.py` â€” reassessment note on full tracking card
- `tests/test_v15_8_active_tracking.py` â€” **NEW**
- `tests/test_database.py`, `tests/test_dashboard_helpers.py` â€” updated
- Docs updated

### Safety

No broker, paper, live, orders, demo fake prices when `real_data_only` + non-Alpaca provider.

### Next

Market-hours validation: trigger a setup, run `update-snapshots`, confirm frozen plan + live P/L on Active Tracking tab.

---

## V15.7E handoff - Home Briefing Card Enrichment

### Current active task

V15.7E complete. Home Top 3 pick/tracking preview cards enriched (pills + compact metrics). Home status/missing-data copy calmer (count-only symbols on Home). **463 tests passed** (full suite via project venv).

### Files changed

- `src/trading_bot/dashboard/theme.py` â€” `build_pick_preview_card_html`, `build_tracking_preview_card_html`, preview CSS.
- `src/trading_bot/dashboard/helpers.py` â€” `tony_status_home_message`, `format_home_missing_data_summary`, preview field constants.
- `tests/test_dashboard_helpers.py`, `tests/test_dashboard_theme.py` â€” V15.7E coverage.
- Docs updated.

### Manual verify

`scripts\run_dashboard.ps1` â†’ Home cards show entry/target/stop and tracking levels; Tony Picks / Active Tracking still full detail.

### Safety

No scoring, entry trigger, DB, broker, paper, live, demo, or API-key changes.

### Next

V15.8: freeze Original Plan at trigger + live `current_price` refresh during watch cycles.

---

## V15.7D handoff - Active Tracking Render Hotfix + Home Clarity

### Current active task

V15.7D complete. Fixed Active Tracking `NameError` (missing theme import). Home status and missing-data copy softened for after-hours. **116 dashboard tests passed** (`test_dashboard_helpers.py`, `test_dashboard_theme.py`). Run full `run_tests.ps1` on Windows for full suite.

### Root cause

V15.7C refactored theme imports in `app.py` and dropped `render_tracking_position_card` while `render_active_tracking()` still called it.

### Files changed

- `src/trading_bot/dashboard/app.py` â€” re-import `render_tracking_position_card`; pass `watch_error_message` to Home status.
- `src/trading_bot/dashboard/helpers.py` â€” calmer `tony_status_home_message()`; `format_home_missing_data_summary()`.
- `tests/test_dashboard_theme.py` â€” import protection tests.
- `tests/test_dashboard_helpers.py` â€” status + missing-data tests.
- Docs updated.

### Manual verify

Streamlit started at http://localhost:8501 (WSL agent smoke: import + `streamlit run` OK). On Windows, run `scripts\run_dashboard.ps1` and click all five tabs â€” especially Active Tracking.

### Safety

No scoring, entry trigger, DB, broker, paper, live, demo, or API-key changes.

### Next

V15.8: freeze Original Plan at trigger + live `current_price` refresh during watch cycles.

---

## V15.7C handoff - Dashboard Render Fix + Home/Picks Separation

### Current active task

V15.7C complete. Fixed raw HTML on Home/Results; separated Home (executive briefing) from Tony Picks (full picker). **447 tests passed.**

### Root cause

Block-level theme HTML was emitted without consistent `st.markdown(..., unsafe_allow_html=True)` via a central helper; partial/broken fragments (and a bad `motionless` placeholder pass) caused Streamlit to show literal tags as page text after the first stat tile.

### Files changed

- `src/trading_bot/dashboard/theme.py` â€” `render_html()`, clean `build_stat_grid_html()`, preview card renderers, balanced div helpers.
- `src/trading_bot/dashboard/app.py` â€” Home briefing layout; Tony Picks full picker copy; `waiting_for_market` in context.
- `tests/test_dashboard_theme.py` â€” stat grid HTML + `render_html` tests.
- `tests/test_dashboard_helpers.py` â€” home preview cap, status messages, briefing items.
- `CURRENT_STATUS.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md`.

### Manual verify

`powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1` â†’ http://localhost:8501 â€” Home short briefing, Tony Picks full cards, Results stat tiles styled.

### Safety

No scoring, entry trigger, DB, broker, paper, live, demo, or API-key changes.

### Next

V15.8: freeze Original Plan at trigger + live `current_price` refresh during watch cycles.

---

## V15.7B hotfix - Theme CSS NameError

Fixed `_TONY_APP_CSS` NameError (`TONY_APP_CSS` renamed to `_TONY_APP_CSS`). Added `tests/test_dashboard_theme.py`. **438 tests passed.**

---

## V15.7B handoff - Visual Product Polish

### Current active task

V15.7B complete. Modern AI stock-picker visual layer (theme.py). **436 tests passed.** UI only.

### Files changed

- `src/trading_bot/dashboard/theme.py` - **NEW** app CSS, hero, stat tiles, signal/tracking/results cards.
- `src/trading_bot/dashboard/app.py` - wired theme into Home, Picks, Tracking, Results.
- Docs updated.

### Next

V15.8: freeze Original Plan + live current_price refresh.

---

## V15.7A handoff - Dashboard Crash Fix + Card Polish

### Current active task

V15.7A complete. Fixed TypeError on Tony Picks (NaN `tony_reasons_json`). Removed `$nan`/`+nan%` from UI. Card CSS polish. **436 tests passed.**

### Files changed

- `src/trading_bot/dashboard/helpers.py` - safe `_parse_json_list`, display formatters, home sort/filter.
- `src/trading_bot/dashboard/app.py` - HTML card polish, home pick/tracking selection.
- `tests/test_dashboard_helpers.py` - V15.7A tests.

### Next

V15.8: freeze Original Plan at trigger + live current_price refresh.

---

## V15.7 handoff - Trading-App Dashboard Shell

### Current active task

V15.7 complete. Five-tab Tony Stocks dashboard (Home, Tony Picks, Active Tracking, Results, Settings / System Health). Legacy developer views under Settings only. No DB/scoring/trigger changes.

### Files changed

- `src/trading_bot/dashboard/helpers.py` - V15.7 helpers: pick phase, card models, research P/L, results/system health summaries.
- `src/trading_bot/dashboard/app.py` - Five-tab shell, card renderers, legacy views in Settings.
- `tests/test_dashboard_helpers.py` - V15.7 tests (14 new cases).
- Docs updated.

### Tests/checks

- `run_tests.ps1`: **421 passed**.
- `eod-report`: OK.
- `outcome-analytics --real-only`: run locally if needed.
- `run_dashboard.ps1`: start Streamlit and spot-check five tabs.

### Safety

No scoring, entry trigger, broker, paper, live, demo, or API-key changes. No new DB columns.

### Next

V15.8: freeze Original Plan at trigger + live current_price refresh in watch cycle.

---

## V15.5 handoff - Dashboard UI/UX Simplification

### Current active task

V15.5 complete. Command Center redesigned for non-technical 30-second review. V15.5 simplifies the dashboard for non-technical review. It does not change trading/scoring behavior. Next: market-hours watch validation.

### Files changed

- `src/trading_bot/dashboard/helpers.py` - Beginner-friendly Command Center helpers (status, data safety, market read, top watches, triggers, EOD, health/review).
- `src/trading_bot/dashboard/app.py` - Command Center redesign; advanced details in collapsed expander.
- `tests/test_dashboard_helpers.py` - V15.5 helper tests added.
- Docs updated.

### Tests/checks

- `run_tests.ps1`: **407 passed** (includes V15.5 `test_dashboard_helpers.py`).
- `eod-report --config config/default_config.yaml`: OK (research-only banner; 7 real snapshots today).
- `outcome-analytics --real-only`: OK (7 real_alpaca rows; demo excluded).
- `run_dashboard.ps1`: Streamlit started at http://localhost:8501 (Command Center import OK).

### Safety

No scoring, entry trigger, broker, paper, live, demo, or API-key changes.

### Next

Market-hours `watch --max-cycles 1` with simplified Command Center review.

---

## V15.2 handoff - Symbol Quarantine for Missing Real Data

### Current active task

V15.2 complete. HCP, SAMSF, SMAR, and SQ are quarantined in config for real-data-only scan/watch (non-destructive; still in universe YAML). Next: market-hours `watch --max-cycles 1` to validate cleaner Tony runs.

### Files changed

- `config/default_config.yaml` - `symbol_quarantine` block; Tony `symbol_quarantine_applied` event.
- `src/trading_bot/data/symbol_quarantine.py` - **NEW** quarantine load/filter helpers.
- `src/trading_bot/settings.py` - `symbol_quarantine` config field.
- `src/trading_bot/cli.py` - Filter before fetch/score; watch rotation pool; eod-report output.
- `src/trading_bot/tony/events.py` - `record_symbol_quarantine_applied()`.
- `src/trading_bot/dashboard/app.py` - Market Day Review quarantine display.
- `tests/test_symbol_quarantine.py` - **NEW** (7 tests).
- Docs updated.

### Tests/checks

- `run_tests.ps1`: **391 passed**, All tests passed.
- `run_scanner.ps1`: quarantine printed; symbols loaded 97 (4 excluded from 101-cap slice).
- `eod-report`: lists configured quarantine HCP, SAMSF, SMAR, SQ.
- `outcome-analytics --real-only`: 7 real_alpaca rows.

### Safety

No trading, scoring rule, broker, paper, live, demo, or API-key changes.

### Next

Market-hours watch validation with quarantine active.

---

## V15.1 handoff - Windows pytest temp cleanup

### Current active task

V15.1 complete. `scripts/run_tests.ps1` now uses `%LOCALAPPDATA%\TradingBotTests\pytest` for `--basetemp` and a separate `tmp` folder for `TMP`/`TEMP`. `tests/conftest.py` sets the same default when pytest is run without `--basetemp`. Full suite: **384 passed, 0 teardown errors**.

### Root cause

Pytest basetemp under the repo (`.pytest_tmp` or `.pytest_tmp_sessions`) hit Windows `PermissionError` on teardown. Common causes: IDE/WSL file locks on the project tree, stale locked temp dirs, and SQLite `tmp_path` dirs under a locked parent. Moving basetemp to `%LOCALAPPDATA%\TradingBotTests` avoids those locks. Setting `TMP`/`TEMP` to a sibling `tmp` folder (not the basetemp root) avoids extra files blocking basetemp deletion.

### Files changed

- `scripts/run_tests.ps1` - LOCALAPPDATA basetemp/tmp, prune old sessions, explicit exit codes.
- `tests/conftest.py` - **NEW** default basetemp outside repo; autouse `gc.collect()` after each test.
- `pyproject.toml` - Comment on basetemp policy.
- `.gitignore` - Ignore `.pytest_tmp_sessions/`.
- `src/trading_bot/snapshots/followup.py` - One-line tz-naive normalize for `actual_entry_time` vs daily index (exposed after clean runner; not a trading-rule change).
- `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - Updated.

### Tests/checks run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
```

Result: **384 passed in 101.72s**, `All tests passed.`, no teardown errors.

### Safety confirmation

No trading, scoring, broker, paper, live, demo, or API-key changes beyond test infrastructure and one datetime comparison normalize in outcome follow-up.

### Next recommended task

Run `watch --max-cycles 1` during market hours and validate V15 intraday trigger simulation on live 5Min bars.

---

## V15 handoff - Intraday Entry Trigger Simulation

### Current active task

V15 complete. Research-only intraday entry trigger simulation is implemented on candidate snapshots. V15 adds research-only intraday trigger simulation. It does not create paper trades or broker orders. Next: run one supervised market-hours `watch --max-cycles 1` and `update-snapshots` to validate live 5Min trigger hits on same-day snapshots.

### Files changed in this pass

- `config/default_config.yaml` - Added `entry_trigger_simulation` block and `entry_trigger_summary` Tony event.
- `src/trading_bot/settings.py` - Added `entry_trigger_simulation` config field.
- `src/trading_bot/storage/database.py` - Added nullable V15 snapshot columns via migrations.
- `src/trading_bot/storage/repositories.py` - Persist/read trigger fields; count helpers for dashboard.
- `src/trading_bot/snapshots/entry_triggers.py` - **NEW** planned-entry rules and 5Min trigger simulation.
- `src/trading_bot/snapshots/followup.py` - Outcomes evaluate from `actual_entry_time` when triggered.
- `src/trading_bot/snapshots/__init__.py` - Export V15 symbols.
- `src/trading_bot/cli.py` - Plan triggers at snapshot creation; simulate on `update-snapshots`; console summary.
- `src/trading_bot/tony/events.py` - `record_entry_trigger_summary()` and event type.
- `src/trading_bot/dashboard/app.py` - Candidate Snapshots + Command Center trigger metrics/columns.
- `tests/test_v15_entry_triggers.py` - **NEW** mocked trigger tests.
- `tests/test_database.py` - Schema assertions for V15 columns.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `FILE_STRUCTURE.md`, `AGENT_STATE.md` - Updated.

### New snapshot fields

- `snapshot_price`, `snapshot_bar_time`
- `planned_entry_price`, `planned_entry_rule`, `planned_entry_buffer_pct`
- `actual_entry_price`, `actual_entry_time`, `entry_status`
- `entry_trigger_source`, `entry_trigger_timeframe`, `entry_trigger_notes`

Legacy rows load with NULL trigger fields.

### Planned entry rule behavior

| Setup | Rule | Planned level |
|-------|------|----------------|
| Breakout Watch | `breakout_above_recent_high` | max(snapshot_price, recent intraday high) + buffer |
| Momentum Continuation | `momentum_break_5min_high_above_vwap` | recent 5Min high when above VWAP |
| Pullback Watch | `pullback_reclaim_vwap_or_prior_high` | max(VWAP, recent 5Min high) when available |
| Missing intraday / real data | `missing_intraday_context` / `no_intraday_trigger_rule` | no planned price; status `missing_real_data` or `no_intraday_trigger` |

These are research triggers, not buy/sell recommendations.

### Actual trigger simulation behavior

- Runs in `update-snapshots` when `entry_trigger_simulation.enabled: true`.
- Fetches real Alpaca 5Min bars (skipped when `real_data_only` and provider is not `alpaca_iex`).
- Uses only bars strictly after `snapshot_bar_time` or `snapshot_time`.
- Trigger when `bar.high >= planned_entry_price`; `actual_entry_time` = first qualifying bar; `actual_entry_price` = planned price (configurable).
- Same day without trigger â†’ `pending`; after window â†’ `expired` or `not_triggered`.
- Does not use end-of-day close as entry.

### No-lookahead protection

- `_bars_after_snapshot()` filters `index > snapshot_reference_time`.
- Pre-snapshot highs cannot trigger entry (covered by tests).

### Dashboard changes

- Candidate Snapshots table: snapshot/planned/actual entry columns and `entry_status`.
- Detail panel shows trigger fields.
- Command Center metrics: planned triggers today, triggered entries today, pending, expired/no-trigger.

### Tests/checks run

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli scan --config config/default_config.yaml --save-snapshots
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli update-snapshots --config config/default_config.yaml --limit 15
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli eod-report --config config/default_config.yaml
```

Results:

- Full test script: **278 passed** (106 pytest tmp teardown permission errors on Windows/WSL; no assertion failures in V15 tests).
- V15 unit tests: **15 passed** (5 teardown errors on tmp cleanup only).
- Scanner passed with Alpaca IEX (stale after-hours bars).
- `scan --save-snapshots` created 7 snapshots; planned entries printed above snapshot price (example: AVGO snapshot=420.6 planned=427.45).
- `update-snapshots` ran on 15 open rows (legacy rows without planned prices).
- `eod-report` completed.
- `watch --max-cycles 1` not run (outside market hours / not requested for safe path).

### Safety confirmation

No broker execution, live trading, automatic paper trades, orders, options/Greeks logic, API key logging, LLM trade decisions, or profitability claims were added. Demo provider is not used for trigger simulation when `real_data_only` is enabled.

### Next recommended task

Run `watch --max-cycles 1` during market hours, then `update-snapshots`, and verify `entry_status=triggered` rows have `actual_entry_time` on first post-snapshot 5Min bar. Compare `outcome-analytics --real-only --today` for trigger-aware outcomes.

---

## V14.7 handoff - Real-Data-Only Enforcement / No Demo Provider

### Current active task

V14.7 real-data-only enforcement implemented. First live market-hours Tony run completed successfully; next focus is real-data-only analytics hygiene before intraday scoring. Active Tony watch/learning runs are real-data-only. Demo provider data is never allowed in watch, snapshots, Tony learning, analytics, paper trading, or live trading. Tests may use mocks or recorded real fixtures, but not synthetic demo market series.

### Files changed in this pass

- `config/default_config.yaml` - Added real-data-only guard fields, disabled active demo fallback, disabled default demo snapshot seeding, and set Alpaca fail-safe/fallback flags false.
- `src/trading_bot/settings.py` - Added config fields and `real_data_only_enabled()`.
- `src/trading_bot/data/market_data.py` - Real-only Alpaca config forces `fail_safe_to_demo=false`; provider now tracks missing symbols separately from explicit dev fallback symbols.
- `src/trading_bot/storage/database.py` - Added nullable candidate snapshot data-source metadata columns.
- `src/trading_bot/storage/repositories.py` - Candidate snapshots and old demo seed snapshots can persist data-source metadata.
- `src/trading_bot/analytics/outcomes.py` - Analytics defaults to real rows only, adds `--include-demo`/legacy behavior support, and reports exclusion counts.
- `src/trading_bot/cli.py` - Real-only scan/watch rejects demo providers, records missing real-data symbols, excludes demo/legacy rows by default in analytics, and expands EOD report fields.
- `src/trading_bot/tony/analysis.py` - Missing real data is labeled `missing_real_data`; Tony learning uses real-only analytics by default.
- `src/trading_bot/tony/events.py` - Real-run event wording now reports missing real data and says no demo data was used.
- `src/trading_bot/dashboard/app.py` - Market Day Review now shows real rows, demo/legacy excluded rows, missing real-data symbols, quarantine candidates, and intraday real/stale counts.
- `tests/test_outcome_analytics.py`, `tests/test_database.py`, `tests/test_scanner_smoke.py`, `tests/test_tony_analyst.py` - Updated/added mocked tests for real-only defaults, include-demo review, missing-symbol behavior, schema compatibility, EOD output, and no paper/order behavior.
- `CURRENT_STATUS.md`, `ROADMAP.md`, `KNOWN_BACKLOG.md`, `TESTING_CHECKLIST.md`, `AGENT_STATE.md` - Updated hard rule, status, backlog, and handoff notes.

### Behavior

- With `real_data_only: true`, active scan/watch refuses `demo_generated` and `demo_csv` providers.
- Alpaca no-bar or provider-missing symbols are marked missing real data, are not scored from demo data, do not create snapshots, and do not enter Tony learning.
- Snapshot classifications are now `real_alpaca`, `missing_real_data`, `recorded_real_fixture`, `legacy_unknown`, and old `demo_generated`.
- Outcome analytics defaults to real rows only and prints: `Real-data rows only. Demo and legacy rows excluded.`
- `--include-demo` explicitly reviews old demo rows; old demo rows are not deleted automatically.
- Repeated missing symbols such as `HCP`, `SAMSF`, `SMAR`, and `SQ` are report-only quarantine/replacement candidates.

### Tests/checks run

```powershell
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m compileall src\trading_bot
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m pytest tests/test_database.py tests/test_outcome_analytics.py tests/test_scanner_smoke.py tests/test_tony_analyst.py -q --basetemp=.pytest_tmp
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_scanner.ps1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli outcome-analytics --config config/default_config.yaml --include-demo
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli eod-report --config config/default_config.yaml
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli watch --config config/default_config.yaml --max-cycles 1
$env:PYTHONPATH='src'; .\.venv\Scripts\python.exe -m trading_bot.cli tony-events --config config/default_config.yaml --limit 50
powershell -ExecutionPolicy Bypass -File .\scripts\run_dashboard.ps1
git diff --check
```

Results:

- Focused tests passed: 91 passed.
- Full test script passed: 371 passed.
- Scanner script completed. This sandbox blocked Alpaca HTTPS (`WinError 10013`), so 100 symbols were marked missing real data, 0 symbols were scored, and no demo fallback was used.
- Default `outcome-analytics` reviewed 77 `real_alpaca` rows and excluded demo/legacy/missing rows.
- `outcome-analytics --include-demo` reviewed 257 rows and explicitly surfaced old demo warning rows.
- `eod-report` completed and showed real symbols scanned as 0 after the blocked scanner smoke, repeated missing real-data symbols including `HCP`, `SAMSF`, `SMAR`, and `SQ`, plus the older live-run real-only snapshot counts.
- `watch --max-cycles 1` timed out because default config is market-hours-only and the command ran outside the configured market window; it waited for market open and did not scan, trade, or fallback to demo. The resulting running watch row was marked error with a verification-timeout note so the dashboard is not left with a stale running process.
- `tony-events --limit 50` completed.
- Dashboard script started Streamlit at `http://localhost:8501`; the command timed out because Streamlit runs in the foreground. No lingering Streamlit/Python process remained.
- `git diff --check` passed with CRLF normalization warnings only.

### Safety confirmation

No broker execution, live trading, automatic paper trades, orders, options/Greeks logic, API key logging, LLM trade decisions, or profitability claims were added. Tony remains research-only.

### Next recommended task

Run one supervised market-hours watch cycle with the hardened config. If `HCP`, `SAMSF`, `SMAR`, and `SQ` continue to report missing real data, manually quarantine or replace them before intraday scoring work.

---

## V14.7 handoff - Real Market-Day Review Cleanup

_(Prior handoffs retained below for history.)_

