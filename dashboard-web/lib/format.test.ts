import { describe, it, expect } from "vitest"
import { formatPrice, formatSignedPct, plPercent, scanAgeLabel } from "@/lib/format"

describe("formatPrice", () => {
  it("formats to 2 decimals", () => expect(formatPrice(124.857)).toBe("124.86"))
  it("renders em dash for null", () => expect(formatPrice(null)).toBe("—"))
})

describe("formatSignedPct", () => {
  it("adds + for non-negative", () => expect(formatSignedPct(2.85)).toBe("+2.85%"))
  it("keeps - for negative", () => expect(formatSignedPct(-1.1)).toBe("-1.10%"))
  it("renders em dash for null", () => expect(formatSignedPct(null)).toBe("—"))
})

describe("plPercent", () => {
  it("computes percent vs entry", () => expect(plPercent(121.4, 124.86)).toBeCloseTo(2.85, 1))
  it("is null when not in trade", () => {
    expect(plPercent(null, 124.86)).toBeNull()
    expect(plPercent(121.4, undefined)).toBeNull()
  })
})

describe("scanAgeLabel", () => {
  it("handles no scan", () => expect(scanAgeLabel(null)).toBe("no scan yet"))
  it("handles under a minute", () => expect(scanAgeLabel(30)).toBe("just now"))
  it("handles minutes", () => expect(scanAgeLabel(125)).toBe("2m ago"))
  it("handles hours", () => expect(scanAgeLabel(7200)).toBe("2h ago"))
})
