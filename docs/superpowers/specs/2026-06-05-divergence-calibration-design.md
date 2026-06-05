# Divergence Calibration — Design Spec

**Date:** 2026-06-05
**Status:** Approved for implementation
**Author:** Claude (planner/coder) + Stephen
**Roadmap vein:** V44 — human-approved strategy version bump (extends the existing suggestion → approve → activate gate)

## 1. Problem

The bot (layer 1, the scanner) and the Command Center's Tony agent (layer 2) disagree often, and
that disagreement is the richest untapped signal in the system. Every disagreement is already graded
into `reports/tony_teaching_log.json` (the divergence ledger) against resolved outcomes, but the
ledger is a **dead-end log** — nothing flows back to make the scanner smarter.

Live proof (2026-06-05): scanner scored CVS 100 + CSX 96 (its top names); Tony closed both and passed
on 7 of 17 high-scoring picks. When Tony systematically overrides a cohort **and resolved outcomes
prove him right**, that is evidence the scanner's weighting over-trusts whatever sub-score inflated
that cohort.

## 2. Goal

Convert the divergence ledger + resolved outcomes into a **human-gated retuning signal for the
scanner's five score weights** (`trend / momentum / volume / risk / setup_quality`). Each calibration
is a tiny, bounded, fully-attributable, reversible nudge that requires **two distinct human keys**
(approve, then activate) before it changes any live behavior.

### Non-goals
- No change to thresholds, role adjustments, or tag penalties (weights only, this iteration).
- No auto-application. No live-trading impact. No profitability claim.
- No reaction to live Tony verdicts — this is offline statistical learning from files the bot
  already produces.

## 3. Hard constraints (CC-tandem safety)

- **Pure separation preserved.** Read-only on `tony_teaching_log.json`, `tony_stocks_outcomes.json`,
  and the snapshot SQLite store. The bot never trades on CC's live verdict; one-way file handoffs are
  unchanged; zero bridge-contract changes.
- **No auto-apply.** Two human keys: (1) approve the proposal at the existing gate, (2) explicitly
  activate the new version.
- **Bounded & reversible.** ≤ `max_delta_pts` (default 3.0) weight-points moved per proposal; every
  weight clamped to `[0.05, 0.50]`; weights always renormalized to sum 1.0; the prior weight-set is
  stored in the version artifact so any version can be reverted by re-activating the predecessor.
- **Sample-gated.** `insufficient` confidence on either the attribution signal or the divergence
  signal ⇒ **no proposal**. A quiet calibrator at low sample is correct behavior.

## 4. Existing machinery this builds on (verified in code)

| Piece | Location | Role here |
|---|---|---|
| Divergence ledger | `analytics/tony_divergence.py` → `reports/tony_teaching_log.json` | Per-verdict grading into 4 quadrants (`agreed_right/wrong`, `cc_overrode_saved/missed`) on `(symbol, pick_date)`. Read-only input. |
| Sample-gated confidence | `analytics/nightly_learning.py::confidence_for(n)` | Reused verbatim: `insufficient/low/med/high`. |
| Resolved outcomes | `reports/tony_stocks_outcomes.json` | `{symbol, pick_date, result, return_pct, ...}`. Win/loss spine. |
| Per-pick sub-scores | SQLite `signal_snapshots` (`storage/database.py:30-34`, `storage/repositories.py:40`) | The 5 sub-scores per `(symbol, pick_date)`. Joined into attribution. |
| Approval gate (Key 1) | `cli.py::run_record_suggestion_decision` → `suggestion_decisions.json` (keyed by `_suggestion_key(suggestion, strategy_version)`) | Records approve/reject. **Records ≠ applies** — unchanged. |
| Self-review payload | `analytics/outcomes.py::build_tony_self_review` (returns `rule_suggestions`) | We add a parallel `weight_proposals` list. |
| Replay | `analytics/outcomes.py::build_replay_summary(rows, strategy_version=...)` | Re-score history under proposed weights for the report. |
| Live weights | `config/scoring_config.yaml` → `load_scoring_config` → `ScoreWeights` | Activation target. Current: trend 0.22 / momentum 0.28 / volume 0.18 / risk 0.14 / setup_quality 0.18. |

## 5. Architecture

```
resolved outcomes ─┐
snapshot sub-scores ┼─► divergence_calibration.py (PURE, no I/O) ─► CalibrationProposal(s)
divergence ledger ─┘                                                     │
                                                                         ▼
                            after-market-review  ──►  weight_proposals in self-review payload + report
                                                                         │
                                            Key 1: record-suggestion-decision  (approve)
                                                                         │ approved → materialize artifact
                                                                         ▼
                                            Key 2: activate-strategy-version --version vNN
                                                                         │
                                                       repoint config/scoring_config.yaml + append ledger
```

### 5.1 Component 1 — `src/trading_bot/analytics/divergence_calibration.py` (NEW, pure, deterministic, no I/O)

Mirrors `nightly_learning.py` / `tony_divergence.py`: pure functions + frozen dataclasses; all I/O
lives in the CLI layer. Sample-gated with `confidence_for`.

**Inputs (plain dicts/lists — caller does the joining/loading):**

```python
@dataclass(frozen=True)
class PickRecord:
    symbol: str
    pick_date: str
    result: str | None          # target_hit | stop_hit | failed_setup | closed | expired | None
    return_pct: float | None
    setup_category: str
    score_band: str             # reuse score_bucket(): "90-100"/"80-89"/"70-79"/"60-69"/"below 60"
    trend_score: float
    momentum_score: float
    volume_score: float
    risk_score: float
    setup_quality_score: float
```

`_COMPONENTS = ("trend", "momentum", "volume", "risk", "setup_quality")`
maps to weight keys `("trend_weight", ...)`.

**Win/loss reuse** the existing `_outcome_is_win` semantics (`target_hit` win; `stop_hit/failed_setup`
loss; `closed` decided by `return_pct` sign; else `None`/unresolved).

**Step 1 — Per-component attribution.** `attribution(picks) -> list[ComponentAttribution]`.
For each component S, over resolved picks only:
- `win_mean = mean(S | win)`, `loss_mean = mean(S | loss)`.
- `separation = win_mean - loss_mean` (units: raw 0–100 sub-score points).
- `predictive` if `separation >= +SEP_EPS`; `anti_or_non_predictive` if `separation <= +SEP_EPS`
  (default `SEP_EPS = 3.0` sub-score points — a component whose winners barely outscore its losers
  is not earning its weight).
- `confidence = confidence_for(n_resolved)`.

```python
@dataclass(frozen=True)
class ComponentAttribution:
    component: str
    n: int
    win_mean: float | None
    loss_mean: float | None
    separation: float | None
    predictive: bool | None     # None when insufficient
    confidence: str
```

**Step 2 — Divergence confirmation per cohort.** `cohort_overrides(ledger) -> list[CohortOverride]`.
Group the ledger's graded records by cohort key. **Two cohort dimensions, computed independently:**
`setup_category` and `score_band`. (Records lacking a band are grouped by `setup_category` only;
band may be absent from older ledger rows — see §8 data-availability.) For each cohort:
- `saved = count(cc_overrode_saved)`, `missed = count(cc_overrode_missed)`,
  `agreed_right = count(agreed_right)`, `agreed_wrong = count(agreed_wrong)`.
- `net_override = saved - missed`.
- `tony_correctly_overrode` if `net_override >= MIN_NET_OVERRIDE` (default 2) **and**
  `confidence_for(saved + missed) != "insufficient"`.
- `tony_correctly_kept` (symmetric, for up-nudges) if `agreed_right - agreed_wrong >= MIN_NET_OVERRIDE`
  and confidence sufficient.

```python
@dataclass(frozen=True)
class CohortOverride:
    dimension: str              # "setup_category" | "score_band"
    cohort: str
    saved: int
    missed: int
    agreed_right: int
    agreed_wrong: int
    net_override: int
    confidence: str
    tony_correctly_overrode: bool
    tony_correctly_kept: bool
```

**Step 3 — Bridge (cohort → component).** `cohort_component_elevation(picks, cohort_dim, cohort)`.
For the picks belonging to a cohort, find which component is most **elevated vs the global mean**:
`elevation[S] = mean(S | pick in cohort) - mean(S | all resolved picks)`. The component with the
largest positive elevation is the one the engine leaned on to surface that cohort. Returns ranked
`(component, elevation)`.

**Step 4 — Confirmation gate (the AND of Option A).** `build_calibration_proposals(...)`:
For each cohort where `tony_correctly_overrode`:
1. `S* = argmax elevation` for that cohort (Step 3).
2. Require attribution for `S*` to be `anti_or_non_predictive` with sufficient confidence
   (Step 1). **Both must agree** — Tony correctly overrode the cohort `S*` inflates AND `S*`
   doesn't separate winners from losers. If attribution says `S*` is genuinely predictive, **skip**
   (Tony's override was cohort-specific noise, not a weighting fault).
3. Direction = **down** for `S*`. `confidence = min(attr_conf, cohort_conf)`
   (ordering insufficient<low<med<high); if `insufficient`, skip.
4. Symmetric up-nudge from `tony_correctly_kept` cohorts whose top-elevated component is
   `predictive` → direction **up**.
- **One component per proposal.** If multiple cohorts implicate the same `S*`, keep the
  highest-confidence/highest-net one (deterministic tiebreak: confidence desc, then net desc,
  then component name asc). Emit at most one **down** and one **up** proposal per run, and never
  both touching the same component.

**Step 5 — Propose the nudge.** `apply_nudge(current_weights, component, direction, max_delta_pts)`:
- `delta = max_delta_pts/100` (weight units), signed by direction.
- `new[S*] = clamp(current[S*] + delta, 0.05, 0.50)` (actual applied delta may shrink at the clamp).
- Redistribute `-applied_delta` across the other four **proportionally to their current weights**.
- Renormalize so the five sum to exactly 1.0 (correct any float drift on the largest weight).
- Round to 4 dp.

```python
@dataclass(frozen=True)
class CalibrationProposal:
    target_component: str
    direction: str              # "down" | "up"
    applied_delta_pts: float
    old_weights: dict[str, float]
    new_weights: dict[str, float]
    cohort_dimension: str
    cohort: str
    attribution_evidence: dict  # win_mean, loss_mean, separation, n, confidence
    divergence_evidence: dict   # saved, missed, net_override, confidence
    confidence: str             # low | medium | high  (mapped: med->medium)
    rationale: str              # plain-English, gate-ready
    strategy_version: str       # CURRENT_STRATEGY_VERSION at proposal time
    # Gate-compat fields so it slots into suggestion_decisions keying:
    suggestion: str             # == rationale (the gate keys on this string)
    status: str = "needs_review"
```

`confidence` is mapped to the gate's vocabulary `{low, medium, high}` (`confidence_for`'s `med`→
`medium`; `insufficient` never produces a proposal).

**Public entry point:**
```python
def build_divergence_calibration(
    picks: list[PickRecord],
    ledger: dict,                       # parsed tony_teaching_log.json
    current_weights: dict[str, float],
    *,
    max_delta_pts: float = 3.0,
    sep_eps: float = 3.0,
    min_net_override: int = 2,
    min_sample: int = 5,
    strategy_version: str = CURRENT_STRATEGY_VERSION,
) -> CalibrationReport: ...
```
`CalibrationReport` carries `proposals: list[CalibrationProposal]`, the full `attributions`,
`cohort_overrides`, a `headline`, and `research_only=True`. Empty `proposals` + an explanatory
headline when nothing clears the gate.

### 5.2 Component 2 — CLI / I/O edges (`cli.py`, `analytics/outcomes.py`)

- **Load + join (new helper, CLI layer):** read outcomes JSON + the divergence ledger + query the
  snapshot DB for sub-scores; build `list[PickRecord]` on `(symbol.upper(), pick_date)`. Outcomes
  with no matching snapshot are dropped (logged count). Reuses `score_bucket` for `score_band`.
- **Fold into self-review:** `build_tony_self_review` (or its CLI caller) gains a `weight_proposals`
  key alongside `rule_suggestions`. Surfaced in `after-market-review` and `eod-report` markdown:
  each proposal prints component, direction, old→new weights, both evidence blocks, confidence, and
  a `build_replay_summary` delta computed under `new_weights`.
- **Key 1 (reuse, NO code change):** weight proposals ride in the **same** `approval_package.json`
  `suggestions` list that `_build_approval_package` already produces, each carrying a
  `kind: "weight_calibration"` marker plus the `new_weights` / `target_component` payload (extra keys
  are ignored by the existing gate). `record-suggestion-decision --index N --status approved` records
  approval keyed by `_suggestion_key(suggestion, strategy_version)` into `suggestion_decisions.json`
  exactly as today — still **records ≠ applies**, no modification to that command.
- **Key 2 (new command, the SOLE apply path):** `activate-strategy-version`
  - Scans `suggestion_decisions.json` for records with `status == "approved"`, cross-references the
    persisted `approval_package.json` to recover the matching `kind == "weight_calibration"` proposal
    (and its `new_weights`). Refuses if no approved weight-calibration proposal is found.
  - `--key <suggestion_key>` selects a specific approved proposal when more than one exists; otherwise
    if exactly one is approved-and-not-yet-activated it is used.
  - Computes the next version id from `reports/strategy_versions.json` (baseline is `v1`; first
    activation → `v2`, etc.). Writes a provenance snapshot `config/strategy_versions/vNN.yaml`
    (new weights + cohort + both evidence blocks + predecessor + proposal_key) **at activation time**,
    writes the new `weights:` block into `config/scoring_config.yaml` (only the `weights:` mapping;
    thresholds/roles untouched), and appends an activation entry to `reports/strategy_versions.json`
    (`{version, activated_at, weights, predecessor, proposal_key, rationale}`).
  - `--revert` re-activates the predecessor weights recorded in the ledger.
  - Prints a clear weight diff and a reminder that the next scan will use the new weights.

### 5.3 Version ledger — `reports/strategy_versions.json`

Append-only list of activations: `{version, activated_at, weights, predecessor, proposal_key,
rationale}`. `CURRENT_STRATEGY_VERSION` derivation is unchanged for proposal tagging; activation
records the realized lineage.

## 6. Data flow (worst-case + happy path)

1. Nightly/after-market: load outcomes + ledger + sub-scores → `build_divergence_calibration`.
2. Low sample (today's reality): every component or cohort `insufficient` → `proposals == []`,
   headline "No calibration yet — evidence has not converged." Report shows the attribution table so
   the human sees *why*. **No artifact, no gate entry.**
3. Convergence: e.g. attribution finds `momentum` separation +1.1 (non-predictive, med conf) AND the
   `Momentum Continuation` cohort has `net_override=+3` (Tony correctly closed them, med conf) with
   momentum the top-elevated component → one **down** proposal on `momentum_weight`, −3 pts,
   redistributed, confidence `medium`. Replay shows ranking deltas.
4. Human reviews → `record-suggestion-decision --index N --status approved` → approval recorded in
   `suggestion_decisions.json` (nothing applied yet).
5. Human runs `activate-strategy-version` → recovers the approved proposal, writes provenance
   `v_next.yaml`, updates `scoring_config.yaml` weights, appends the ledger. Next scan uses new weights.
6. Regret → `activate-strategy-version --revert`.

## 7. Testing (pure core ⇒ exhaustive, fast unit tests)

`tests/test_divergence_calibration.py` (synthetic `PickRecord` + ledger dicts):
- **T1 down-nudge fires:** anti-predictive component + confirmed override on the cohort it inflates →
  one down proposal on the right component; `new_weights` sum to 1.0 (±1e-9); `applied_delta_pts ≤ 3`;
  the four others moved proportionally; all weights in `[0.05, 0.50]`.
- **T2 AND-gate blocks:** attribution says component non-predictive BUT no cohort it inflates was
  overridden → **no proposal**.
- **T3 AND-gate blocks (other side):** Tony correctly overrode a cohort BUT its top component is
  genuinely predictive → **no proposal**.
- **T4 insufficient sample:** below `min_sample` on either signal → **no proposal**, explanatory
  headline.
- **T5 up-nudge:** `agreed_right` cohort whose top component is predictive → one up proposal.
- **T6 clamp:** component already at 0.50 (or near 0.05 on a down move) → applied delta shrinks,
  weights still sum to 1.0, no weight escapes `[0.05, 0.50]`.
- **T7 single-component invariant:** multiple cohorts implicating the same component collapse to one
  proposal (deterministic tiebreak); never two proposals on one component.
- **T8 determinism:** identical inputs → byte-identical proposals.
- **T9 confidence mapping:** `med`→`medium`; `insufficient` suppressed.

`tests/test_activate_strategy_version.py`:
- **A1 refuses** activation when no weight-calibration proposal is `approved`.
- **A2 refuses** activation when an approved proposal cannot be matched back to a package payload
  (no `new_weights` recoverable).
- **A3 applies** the right weights to `scoring_config.yaml`; thresholds/roles untouched; sum 1.0.
- **A4 ledger** appended with predecessor lineage; version id increments (`v1`→`v2`→…).
- **A5 revert** re-activates the predecessor weights.
- **A6 provenance** snapshot `vNN.yaml` written at activation time with full evidence; idempotent
  re-activation of an already-active version is a no-op (not a double-append).

Run via `scripts\run_tests.ps1`. Target: all green; no regression in existing suite.

## 8. Risks & mitigations

- **Sub-score join coverage.** Some historical outcomes may predate sub-score persistence. Mitigation:
  inner-join on the DB; drop + count unmatched; attribution `n` reflects only matched picks; confidence
  gating naturally suppresses proposals when coverage is thin.
- **`score_band` absent from older ledger rows.** Mitigation: the `setup_category` cohort dimension is
  always available; `score_band` is best-effort. Calibration works on whichever dimension has data.
- **Cohort→component bridge is heuristic.** Mitigation: it is gated *behind* outcome attribution
  (Step 4), so a wrong bridge guess cannot move a weight unless the component is independently
  non-predictive. Worst case: no proposal.
- **Float drift in renormalization.** Mitigation: renormalize and absorb residual on the largest
  weight; assert sum==1.0 within 1e-9 in tests.
- **Two-key bypass.** Mitigation: `activate-strategy-version` hard-refuses without an `approved`
  record; covered by A1/A2.

## 9. Files

**New**
- `src/trading_bot/analytics/divergence_calibration.py`
- `config/strategy_versions/` (artifacts) + `reports/strategy_versions.json` (ledger, created on first activation)
- `tests/test_divergence_calibration.py`
- `tests/test_activate_strategy_version.py`

**Edit**
- `src/trading_bot/analytics/outcomes.py` — add `weight_proposals` to self-review payload.
- `src/trading_bot/cli.py` — PickRecord loader/join; surface proposals in `after-market-review` +
  `eod-report`; materialize artifact on approval; add `activate-strategy-version`.
- `src/trading_bot/analytics/__init__.py` — export new public functions if needed.

## 10. Out of scope (explicit follow-ups)

- **Tier-3 contract-drift test guard** — freeze the bridge + verdicts/record schemas as an automated
  suite test so a future change can't silently break the 2nd layer. Cheap, high-value; recommended as
  the very next item after this ships.
- Calibrating thresholds, role adjustments, sectors, or tag penalties.
- Multi-component simultaneous re-fits (deliberately excluded — tiny one-cohort nudges only).
