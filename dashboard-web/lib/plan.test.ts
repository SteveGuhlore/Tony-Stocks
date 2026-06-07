import { describe, it, expect } from "vitest"
import { computeRail } from "./plan"
import { sparklinePoints } from "./sparkline"
import { statusBadge, subScoreArray, effectivePrice, scoreDelta } from "./rows"
import type { CockpitRow } from "./types"

function row(p: Partial<CockpitRow>): CockpitRow {
  return {
    symbol: "X",
    name: null,
    sector: null,
    universe_role: null,
    setup_category: null,
    score: null,
    sub_scores: null,
    close: null,
    entry: null,
    stop: null,
    target: null,
    rr: null,
    trade_plan_valid: false,
    last_price: null,
    day_change_pct: null,
    price_status: "unavailable",
    rvol: null,
    sparkline: null,
    status: "watching",
    entry_triggered: false,
    distance_to_entry_pct: null,
    current_price: null,
    research_unrealized_pl_pct: null,
    reassessment_label: null,
    time_active_minutes: null,
    original_entry: null,
    original_stop: null,
    original_target: null,
    tony: null,
    ...p,
  }
}

describe("computeRail", () => {
  it("returns not-ok when levels missing", () => {
    expect(computeRail({ stop: null, entry: 10, target: 12, current: 10 }).ok).toBe(false)
  })
  it("orders stop < entry < target on the track and clamps within span", () => {
    const g = computeRail({ stop: 178.2, entry: 183, target: 192.5, current: 182.4 })
    expect(g.ok).toBe(true)
    expect(g.stopPct).toBeLessThan(g.entryPct)
    expect(g.entryPct).toBeLessThan(g.targetPct)
    expect(g.curPct).toBeGreaterThanOrEqual(0)
    expect(g.curPct).toBeLessThanOrEqual(100)
    expect(g.curAboveEntry).toBe(false)
  })
})

describe("sparklinePoints", () => {
  it("flags empty for <2 points", () => {
    expect(sparklinePoints([]).empty).toBe(true)
    expect(sparklinePoints(null).empty).toBe(true)
  })
  it("computes up direction", () => {
    expect(sparklinePoints([1, 2, 3]).up).toBe(true)
    expect(sparklinePoints([3, 2, 1]).up).toBe(false)
  })
})

describe("row selectors", () => {
  it("statusBadge", () => {
    expect(statusBadge(row({ status: "triggered" })).label).toBe("TRIGGERED")
    expect(statusBadge(row({ entry_triggered: true })).kind).toBe("triggered")
    expect(statusBadge(row({ status: "near", distance_to_entry_pct: 0.3 })).label).toBe("NEAR · 0.3%")
    expect(statusBadge(row({ status: "watching" })).label).toBe("watching")
  })
  it("subScoreArray nulls to zero in TMVRS order", () => {
    expect(subScoreArray(null)).toEqual([0, 0, 0, 0, 0])
    expect(
      subScoreArray({ trend: 88, momentum: 80, volume: 95, risk: null, setup: 82 }),
    ).toEqual([88, 80, 95, 0, 82])
  })
  it("effectivePrice prefers current then last then close", () => {
    expect(effectivePrice(row({ current_price: 1, last_price: 2, close: 3 }))).toBe(1)
    expect(effectivePrice(row({ last_price: 2, close: 3 }))).toBe(2)
    expect(effectivePrice(row({ close: 3 }))).toBe(3)
    expect(effectivePrice(row({}))).toBeNull()
  })
  it("scoreDelta awaiting-safe", () => {
    expect(scoreDelta(row({ score: 91, tony: { score: 88, verdict: "", reasoning: null, returned_at: null } }))).toBe(3)
    expect(scoreDelta(row({ score: 91 }))).toBeNull()
  })
})
