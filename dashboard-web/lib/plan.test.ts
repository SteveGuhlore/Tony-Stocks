import { describe, it, expect } from "vitest"
import { railPositionPct } from "@/lib/plan"

const stop = 117.9, entry = 121.4, target = 129.0

describe("railPositionPct", () => {
  it("puts stop at 0 and target at 100", () => {
    expect(railPositionPct(stop, { stop, entry, target })).toBe(0)
    expect(railPositionPct(target, { stop, entry, target })).toBe(100)
  })
  it("places entry between them", () => {
    const p = railPositionPct(entry, { stop, entry, target })
    expect(p).toBeGreaterThan(0)
    expect(p).toBeLessThan(100)
    expect(p).toBeCloseTo(31.5, 0) // (121.4-117.9)/(129-117.9)
  })
  it("clamps prices outside the span", () => {
    expect(railPositionPct(110, { stop, entry, target })).toBe(0)
    expect(railPositionPct(140, { stop, entry, target })).toBe(100)
  })
  it("returns null when any level is missing or live is missing", () => {
    expect(railPositionPct(124, { stop: null, entry, target })).toBeNull()
    expect(railPositionPct(null, { stop, entry, target })).toBeNull()
  })
  it("returns null on a degenerate span", () => {
    expect(railPositionPct(120, { stop: 120, entry: 120, target: 120 })).toBeNull()
  })
})
