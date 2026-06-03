import { describe, it, expect } from "vitest"
import { priceBounds, scaleY, priceTicks, type Bar } from "@/lib/chart"

const bars: Bar[] = [
  { date: "2026-05-01", open: 100, high: 105, low: 98, close: 103, volume: 1000 },
  { date: "2026-05-02", open: 103, high: 108, low: 102, close: 107, volume: 1200 },
]

describe("priceBounds", () => {
  it("spans bar lows/highs with padding", () => {
    const b = priceBounds(bars)!
    expect(b.min).toBeLessThan(98)
    expect(b.max).toBeGreaterThan(108)
  })
  it("includes plan levels outside the bar range", () => {
    const b = priceBounds(bars, [90, 120])!
    expect(b.min).toBeLessThan(90)
    expect(b.max).toBeGreaterThan(120)
  })
  it("returns null for empty input", () => {
    expect(priceBounds([], [])).toBeNull()
  })
  it("handles a degenerate single value", () => {
    const b = priceBounds([], [100])!
    expect(b.min).toBeLessThan(100)
    expect(b.max).toBeGreaterThan(100)
  })
})

describe("scaleY", () => {
  it("maps max to top (0) and min to bottom (height)", () => {
    expect(scaleY(110, 100, 110, 200)).toBe(0)
    expect(scaleY(100, 100, 110, 200)).toBe(200)
  })
  it("maps the midpoint to the middle", () => {
    expect(scaleY(105, 100, 110, 200)).toBe(100)
  })
})

describe("priceTicks", () => {
  it("produces evenly spaced inclusive ticks", () => {
    expect(priceTicks(100, 130, 4)).toEqual([100, 110, 120, 130])
  })
})
