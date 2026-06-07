# Plan Review Log: Kinetic Tape — Bot Dashboard Rebuild
Act 1 (grill) complete — plan locked with the operator (Stephen) on 2026-06-07. MAX_ROUNDS=5.

Design spec: `docs/superpowers/specs/2026-06-07-kinetic-tape-dashboard-design.md`
Plan: `PLAN.md` · Visual contract: `.superpowers/brainstorm/9752-1780851075/content/` (11 mockups)

---

## Round 1 — Codex (VERDICT: REVISE)
Thread `019ea33a-ee4e-7d12-b186-b2f9829ead4f`. 13 findings:
1. Shared browser token for money actions is weak (replayable/phishable). Fix: per-action PIN, Origin/Host check, signed nonce + idempotency, audit row.
2. No hard guarantee local dev can't hit the VM paper account. Fix: server-side env-role fence (ENV_ROLE + DB root + account fingerprint).
3. Tape/drawer assume tracking fields the read model omits (current_price, research_unrealized_pl_pct, reassessment_label, time_active_minutes, original_*) though columns exist. Fix: extend read models first.
4. `/api/paper/positions` has no per-position unrealized mark / protection / order metadata. Fix: add before designing those controls.
5. Chart backend doesn't exist (`chart_bars=[]`; on-request yfinance). Fix: first-party chart endpoint from stored bars/cache, or downgrade scope.
6. Wrong composition boundary (Tony in /command-center, day-change in /prices, sparkline/RVOL/agreement nowhere). Fix: add `/api/cockpit` aggregate view-model.
7. Phone re-render storm (1000+ symbols + polling + SSE + per-row motion + SVG + Pixi). Fix: cap hero nodes, virtualize tape, isolate price updates, disable off-screen animation.
8. `/api/prices` 503s without keys; UI must not collapse. Fix: stale/delayed/unavailable states + fall back to last close.
9. SSE too weak (fixed 5s reconnect, no resume). Fix: backoff + rehydrate-from-GET; treat polling as truth.
10. Frontend hard-codes verdict enum but backend passes through `pass`/unknown. Fix: transport verdict as string, normalize in one helper.
11. Control endpoints lack serialization for concurrent loops. Fix: DB-backed command queue w/ per-action locks + idempotent records.
12. Visual-diff gate targets the wrong failure mode; prod breakages are empty CC files, stale watch, 503 prices, CORS/env drift. Fix: recorded-real-fixture E2E against VM-shaped API + audit/metric assertions.
13. Wipe + read/write/full-motion in one pass = max blast radius on a 5x-failed surface. Fix: build side-by-side `/v2`, prove read-only parity on prod-shaped data, unlock POSTs after soak.

### Claude's response (Rev 3)
Accepted 1,2,3,4,5,6,7,8,9,10,12 in full — incorporated into PLAN.md:
- §A1 env-role fence (fail-closed); §A2 extended read models; §A3 `/api/cockpit` aggregate; §A4 paper marks+protection;
  §A5 first-party chart endpoint; §A6 per-action PIN/Origin/nonce/idempotency/audit; §B10 string verdicts + stale/503
  fallbacks + SSE backoff/rehydrate; §B13 virtualized tape + per-row price store + capped/paused Pixi; §C19 prod-shaped
  degraded-data E2E gate added alongside §C20 visual-diff.
Partially accepted:
- #11 — took per-action locks + idempotency keys + audit rows, but NOT a command-queue service (kill-switches are
  idempotent file writes; a queue is overkill for a single-operator tool). Logged.
- #13 — adopted the safety core (prove read-only parity on prod-shaped fixtures BEFORE wiring any POST control; old
  frontend recoverable via git tag `dashboard-web-legacy`) but NOT a separate `/v2` package — operator's hard
  constraint is wipe-only-`dashboard-web`. De-risk via sequencing + git, not a parallel surface. Logged.

---

## Round 2 — Codex (VERDICT: REVISE)
Down to 4 findings (13 → 4):
1. `per-action lock` underspecified — an in-process API mutex won't serialize against separate watch/paper processes. Fix: cross-process lock (SQLite row lock / lockfile shared by API+watch+paper) + 409 on conflict.
2. trigger-scan/flatten/re-protect need an explicit interaction contract with active loops. Fix: server-enforced preconditions (watch stopped / paper paused / single-symbol position version match).
3. Env fence fingerprint still implementable from config text. Fix: fingerprint from live broker/account identity at runtime, not YAML/env label.
4. Contradiction: "Keep ALL bot logic untouched" vs adding endpoints/models/locks. Fix: reword to "no scanner/scoring/strategy decision logic changes; additive API/control/read-model work only."

### Claude's response (Rev 4)
Accepted all 4 — PLAN.md updated:
- Goal reworded (#4): "No scanner/scoring/strategy decision-logic changes — additive API/control/read-model work only."
- §A1 (#3): fingerprint sourced at runtime from the live broker account id, not a config label; fail-closed.
- §A6 (#1,#2): concurrency is cross-process (shared SQLite advisory lock / lockfile honored by API + watch + paper), 409 on conflict; per-action server-enforced preconditions (trigger-scan 409s if scan running; flatten/re-protect require position snapshot/version match).

---

## Round 3 — Codex (VERDICT: REVISE, no findings)
Returned a bare "VERDICT: REVISE" with no enumerated flaws. Not actionable. Claude (final arbiter) declined to revise against nothing and pushed Codex for specifics (round 4).

## Round 4 — Codex (VERDICT: REVISE)
2 findings:
1. Goal says watch/paper "stay byte-for-byte" but step 6 needs them to honor a cross-process lock — contradiction. Fix: explicitly allow minimal additive lock/precondition hooks in watch+paper.
2. Chart endpoint data source still under-specified ("stored bars / price cache" has no concrete contract) — risks empty/stale charts again. Fix: lock the source + retention (persist price-poll/watch intraday bars to SQLite for N days; explicit stale/unavailable fallback).

### Claude's response (Rev 5)
Accepted both:
- Goal reworded: no scanner/scoring/strategy decision-logic changes; the ONLY watch/paper edits are minimal additive concurrency hooks (honor the shared lock/preconditions); learn+vault untouched.
- §A4 chart: locked data source — new SQLite `intraday_bars` table (rolling 10-trading-day retention) fed by the existing price-poll/watch cycle; daily from stored daily snapshots; chart endpoint reads ONLY stored sources (no hot-path yfinance); explicit unavailable/stale UI state.

---

## Round 5 — Codex (VERDICT: APPROVED) ✅
Both round-4 fixes verified. Plan converged after 5 rounds (findings 13 → 4 → bare → 2 → 0).
Operator pre-authorized the build ("continue once Codex and Claude agree; don't ask; build until done").
**Proceeding to implementation (Rev 5 = build-ready).**
