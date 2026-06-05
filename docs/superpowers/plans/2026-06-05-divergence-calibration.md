# Divergence Calibration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the dead-end Tony divergence ledger into a human-gated, two-key, bounded retuning signal for the scanner's five score weights.

**Architecture:** A pure deterministic core (`divergence_calibration.py`, no I/O) computes per-component outcome attribution AND per-cohort divergence confirmation; only when both agree does it emit one tiny capped weight nudge. CLI edges load/join the data, surface proposals through the existing approval-package gate (Key 1 = `record-suggestion-decision`, unchanged), and a new `activate-strategy-version` command (Key 2) is the sole path that writes live weights.

**Tech Stack:** Python 3.14, pandas, pytest, PyYAML, SQLite (existing `signal_snapshots` store). Tests run via `scripts\run_tests.ps1` (sets `PYTHONPATH=src`).

**Reference spec:** `docs/superpowers/specs/2026-06-05-divergence-calibration-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `src/trading_bot/analytics/divergence_calibration.py` (NEW) | Pure core: dataclasses, attribution, cohort overrides, bridge, AND-gate, nudge math, `build_divergence_calibration`. |
| `tests/test_divergence_calibration.py` (NEW) | Exhaustive unit tests (T1–T9 + loader integration). |
| `src/trading_bot/cli.py` (MODIFY) | `_load_pick_records` join helper; surface `weight_proposals` in `after-market-review`/`eod-report` + approval package; new `activate-strategy-version` command. |
| `src/trading_bot/analytics/outcomes.py` (MODIFY) | Add `weight_proposals` passthrough to the self-review payload. |
| `tests/test_activate_strategy_version.py` (NEW) | Activation gate tests (A1–A6). |
| `config/strategy_versions/` (NEW dir) | Per-version provenance YAML, written at activation. |
| `reports/strategy_versions.json` (NEW, runtime) | Append-only activation lineage ledger. |

Module-level constants in `divergence_calibration.py`:
```python
_COMPONENTS = ("trend", "momentum", "volume", "risk", "setup_quality")
_WEIGHT_KEYS = {c: f"{c}_weight" for c in _COMPONENTS}
_WIN_RESULTS = {"target_hit"}
_LOSS_RESULTS = {"stop_hit", "failed_setup"}
_CONF_ORDER = {"insufficient": 0, "low": 1, "med": 2, "high": 3}
_WEIGHT_FLOOR, _WEIGHT_CEIL = 0.05, 0.50
```

---

## Task 1: Pure core scaffolding (dataclasses + win/loss helper)

**Files:** Create `src/trading_bot/analytics/divergence_calibration.py`; Test `tests/test_divergence_calibration.py`.

- [ ] **Step 1: Failing test**
```python
from trading_bot.analytics.divergence_calibration import PickRecord, _outcome_is_win, _COMPONENTS

def _pick(**kw):
    base = dict(symbol="AAA", pick_date="2026-05-01", result="target_hit", return_pct=5.0,
                setup_category="Breakout Watch", score_band="80-89", trend_score=70.0,
                momentum_score=80.0, volume_score=60.0, risk_score=55.0, setup_quality_score=65.0)
    base.update(kw); return PickRecord(**base)

def test_outcome_is_win_semantics():
    assert _outcome_is_win(_pick(result="target_hit")) is True
    assert _outcome_is_win(_pick(result="stop_hit")) is False
    assert _outcome_is_win(_pick(result="failed_setup")) is False
    assert _outcome_is_win(_pick(result="closed", return_pct=2.0)) is True
    assert _outcome_is_win(_pick(result="closed", return_pct=-2.0)) is False
    assert _outcome_is_win(_pick(result="expired", return_pct=None)) is None

def test_components_constant():
    assert _COMPONENTS == ("trend", "momentum", "volume", "risk", "setup_quality")
```
- [ ] **Step 2:** Run `scripts\run_tests.ps1 -- tests/test_divergence_calibration.py -v` → FAIL (ImportError).
- [ ] **Step 3: Implement** the module docstring + constants + `PickRecord` (with `component_score(name)` accessor) + `_to_float` + `_outcome_is_win` (reuse semantics from `nightly_learning`; import `confidence_for` from there). Full code in spec §5.1.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat(calibration): pure-core scaffolding — PickRecord + win/loss`

---

## Task 2: Per-component attribution

- [ ] **Step 1: Failing test**
```python
from trading_bot.analytics.divergence_calibration import attribution

def test_attribution_separation_and_predictive():
    picks = []
    for i in range(6):
        picks.append(_pick(symbol=f"W{i}", result="target_hit", momentum_score=80.0, trend_score=75.0))
        picks.append(_pick(symbol=f"L{i}", result="stop_hit", momentum_score=78.0, trend_score=55.0))
    attrs = {a.component: a for a in attribution(picks)}
    assert attrs["trend"].predictive is True and attrs["trend"].separation == 20.0
    assert attrs["momentum"].predictive is False        # +2 <= sep_eps(3)
    assert attrs["momentum"].confidence == "high"       # 12 resolved
```
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `ComponentAttribution` dataclass + `attribution(picks, *, sep_eps=3.0, min_sample=5)`: over resolved picks only, per component `separation = mean(win) - mean(loss)`, `predictive = sep >= sep_eps` (None if insufficient conf), `confidence = confidence_for(n)`. Round means/sep to 4dp.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat(calibration): per-component outcome attribution`

---

## Task 3: Per-cohort divergence confirmation

Ledger = parsed `tony_teaching_log.json` → `{"records":[{symbol, pick_date, classification}]}`, `classification ∈ agreed_right|agreed_wrong|cc_overrode_saved|cc_overrode_missed|pending`. Cohort values come from the joined picks on `(symbol.upper(), pick_date)`.

- [ ] **Step 1: Failing test**
```python
from trading_bot.analytics.divergence_calibration import cohort_overrides

def test_cohort_overrides_flags_proven_overrides():
    ledger = {"records": [{"symbol": f"S{i}", "pick_date": "2026-05-01",
                           "classification": "cc_overrode_saved"} for i in range(5)]
                          + [{"symbol": "M0", "pick_date": "2026-05-01",
                              "classification": "cc_overrode_missed"}]}
    picks = [_pick(symbol=f"S{i}", setup_category="Breakout Watch") for i in range(5)] \
            + [_pick(symbol="M0", setup_category="Breakout Watch")]
    bw = {(c.dimension, c.cohort): c for c in cohort_overrides(ledger, picks)}[("setup_category", "Breakout Watch")]
    assert bw.saved == 5 and bw.missed == 1 and bw.net_override == 4
    assert bw.tony_correctly_overrode is True
```
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `CohortOverride` dataclass + `cohort_overrides(ledger, picks, *, min_net_override=2, min_sample=5)`: build `pick_map`, tally classifications per `(dimension, cohort)` across both `setup_category` and `score_band` (skip empty/`pending`), compute `net_override`, set `tony_correctly_overrode = net>=min_net_override and confidence_for(saved+missed)!="insufficient"`, symmetric `tony_correctly_kept`. Full code in spec / Task body above.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat(calibration): per-cohort divergence confirmation`

---

## Task 4: Cohort→component bridge (elevation)

- [ ] **Step 1: Failing test**
```python
from trading_bot.analytics.divergence_calibration import cohort_component_elevation

def test_elevation_picks_most_inflated_component():
    picks = [_pick(symbol=f"C{i}", setup_category="Momentum Continuation", momentum_score=95.0,
                   trend_score=50.0, volume_score=50.0, risk_score=50.0, setup_quality_score=50.0)
             for i in range(4)] \
          + [_pick(symbol=f"O{i}", setup_category="Pullback Watch", momentum_score=40.0,
                   trend_score=50.0, volume_score=50.0, risk_score=50.0, setup_quality_score=50.0)
             for i in range(6)]
    ranked = cohort_component_elevation(picks, "setup_category", "Momentum Continuation")
    assert ranked[0][0] == "momentum" and ranked[0][1] > 0
```
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `cohort_component_elevation(picks, dimension, cohort)`: over resolved picks (fallback all), `elevation[c] = mean(c|in-cohort) - mean(c|pool)`; return sorted `(component, elevation)` desc, tie-break component name asc.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat(calibration): cohort->component elevation bridge`

---

## Task 5: Bounded nudge math (clamp / redistribute / renormalize) — spec T1 + T6

- [ ] **Step 1: Failing test**
```python
from trading_bot.analytics.divergence_calibration import apply_nudge
_W = {"trend_weight":0.22,"momentum_weight":0.28,"volume_weight":0.18,"risk_weight":0.14,"setup_quality_weight":0.18}

def test_apply_nudge_down_keeps_sum_and_bounds():
    new, applied = apply_nudge(_W, "momentum", "down", max_delta_pts=3.0)
    assert abs(sum(new.values()) - 1.0) < 1e-9
    assert new["momentum_weight"] < _W["momentum_weight"] and applied == 3.0
    assert all(0.05 <= v <= 0.50 for v in new.values())

def test_apply_nudge_clamps_at_floor():
    w = {"trend_weight":0.06,"momentum_weight":0.40,"volume_weight":0.18,"risk_weight":0.18,"setup_quality_weight":0.18}
    new, applied = apply_nudge(w, "trend", "down", max_delta_pts=3.0)
    assert new["trend_weight"] >= 0.05 - 1e-9 and applied <= 1.0 + 1e-9
    assert abs(sum(new.values()) - 1.0) < 1e-9
```
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `apply_nudge(current_weights, component, direction, *, max_delta_pts=3.0) -> (new_weights, applied_delta_pts)` + `_clamp`: signed delta, clamp target to `[0.05,0.50]`, redistribute `-applied` across others proportional to current weight, clamp others, push residual onto largest other weight, round to 4dp, final exact-sum fix. Full code in spec §5.1 / Task body.
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5: Commit** `feat(calibration): bounded clamp/redistribute/renormalize nudge`

---

## Task 6: AND-gate + `build_divergence_calibration` — spec T2,T3,T5,T7,T8,T9 + happy path

- [ ] **Step 1: Failing tests** (down fires on convergence; no proposal when attribution disagrees; insufficient → empty; determinism — full code in spec / prior plan draft).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `CalibrationProposal` (frozen dc with `to_dict`; fields incl `kind="weight_calibration"`, `status="needs_review"`, `suggestion==rationale`), `CalibrationReport` (`to_dict` exposes `weight_proposals`/`attributions`/`cohort_overrides`/`headline`), `_min_conf`, `_CONF_TO_GATE` (`med→medium`), helper `_keep_best`/`_select_one`/`_rationale`/`_headline`, and `build_divergence_calibration(...)`:
  - run `attribution` + `cohort_overrides`;
  - for each cohort: `top = argmax elevation (>0)`; require `attr[top].predictive is not None`;
  - **down** when `tony_correctly_overrode and predictive is False`; **up** when `tony_correctly_kept and predictive is True`; `confidence = min(attr_conf, cohort_conf)` mapped to gate vocab;
  - keep best per component, select ≤1 down + ≤1 up, never same component;
  - build proposals via `apply_nudge`; empty → "No calibration yet — evidence has not converged." headline.
- [ ] **Step 4:** Run → PASS. Add T5/T7/T9 tests; green.
- [ ] **Step 5: Commit** `feat(calibration): AND-gate + build_divergence_calibration report`

---

## Task 7: CLI join + surface proposals in report/approval package

**Files:** Modify `cli.py` (`_load_pick_records`, wire into `after-market-review`); modify `outcomes.py` (`build_tony_self_review` echoes optional `weight_proposals`).

- [ ] **Step 1: Failing test** — `_load_pick_records(outcomes_path, db_path)` joins a temp SQLite `signal_snapshots` row to an outcome and derives `score_band` via `score_bucket`. (Full test in spec / prior draft.)
  > Confirm the real `signal_snapshots` column + date column names in `storage/database.py` / `storage/repositories.py` during implementation and adapt the SELECT (pick_date may map to a `scanned_at`/date column).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `_load_pick_records`; in the `after-market-review` handler load ledger (`teaching_log_path()`) + current weights (`load_scoring_config(...).weights` → dict via `dataclasses.asdict`), call `build_divergence_calibration`, attach `weight_proposals` to the self-review payload, and **append each proposal dict (carrying `kind`/`new_weights`/`target_component`/`rationale`) to the `suggestions` list feeding `_build_approval_package`** so Key 1 can approve it. Render a calibration section in the review markdown (component, direction, old→new, evidence, confidence, replay delta via `build_replay_summary`).
- [ ] **Step 4:** Run → PASS; then smoke: `after-market-review` exits 0 and prints the "No calibration yet" headline + attribution at low sample.
- [ ] **Step 5: Commit** `feat(calibration): join sub-scores + surface weight proposals in review/gate`

---

## Task 8: `activate-strategy-version` (Key 2 — sole apply path) — spec A1–A6

**Files:** Modify `cli.py` (`run_activate_strategy_version` + subparser); Create `tests/test_activate_strategy_version.py`.

- [ ] **Step 1: Failing tests** A1 (refuse without approval), A3/A4 (apply + ledger + `v2.yaml`), A5 (revert restores predecessor). Full code in spec / prior draft (seeds a temp `scoring_config.yaml`, `approval_package.json` with a `kind:"weight_calibration"` suggestion + `new_weights`, and `suggestion_decisions.json`).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3: Implement** `run_activate_strategy_version(args)`:
  - load `suggestion_decisions.json`, collect `status=="approved"`; recover matching `approval_package.json` suggestion by `_suggestion_key`, require `kind=="weight_calibration"` + `new_weights`; none → `{"error":"no_approved_calibration"}`.
  - `--key` disambiguates when >1 approved; compute next version `v{max+1}` from `reports/strategy_versions.json` (baseline `v1`).
  - load-modify-dump `config/scoring_config.yaml` writing only `weights:`; write provenance `config/strategy_versions/vNN.yaml`; append ledger `{version, activated_at, weights, predecessor, proposal_key, rationale}`. `--revert` re-applies predecessor weights. Idempotent if already-active. Print weight diff.
  - Register subparser `activate-strategy-version` with `--version/--key/--revert/--output-dir/--config-dir/--date`.
- [ ] **Step 4:** Run → PASS (A1–A6).
- [ ] **Step 5: Commit** `feat(calibration): activate-strategy-version two-key apply path`

---

## Task 9: Full-suite verification, regression, docs

- [ ] **Step 1:** `powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1` → all green, no regressions.
- [ ] **Step 2:** Smoke `after-market-review` + `eod-report` on demo data; exit 0; calibration section renders.
- [ ] **Step 3:** Update `AGENT_STATE.md` (handoff + how to approve/activate) and the V44 line in `ROADMAP.md`/`CURRENT_STATUS.md`.
- [ ] **Step 4: Commit** `docs(calibration): handoff + status update`
- [ ] **Step 5:** Offer PR via `superpowers:finishing-a-development-branch`.

---

## Self-Review (planner)

- **Spec coverage:** §5.1 → Tasks 1–6; §5.2 join/report → Task 7; §5.2 Key 2 + §5.3 ledger → Task 8; §7 tests → Tasks 2,5,6,8; §3 safety → Tasks 5,6,8; §8 risks → Tasks 5,6,7,8. No uncovered requirement.
- **Placeholder scan:** only deferred detail is the exact `signal_snapshots` column/date name in Task 7, explicitly flagged with the file to check. Not a silent placeholder.
- **Type consistency:** `PickRecord`/`ComponentAttribution`/`CohortOverride`/`CalibrationProposal`/`CalibrationReport` + `attribution`/`cohort_overrides`/`cohort_component_elevation`/`apply_nudge`/`build_divergence_calibration`/`run_activate_strategy_version` referenced consistently across tasks and tests.
