import { describe, it, expect } from "vitest"
import { fmtPrice, fmtPct, fmtMoney, fmtScore, fmtRvol, changeClass, priceStatusDisplay } from "./format"

describe("format helpers", () => {
  it("fmtPrice handles null/NaN", () => {
    expect(fmtPrice(null)).toBe("—")
    expect(fmtPrice(NaN)).toBe("—")
    expect(fmtPrice(182.4)).toBe("182.40")
  })
  it("fmtPct signs and degrades", () => {
    expect(fmtPct(2.1)).toBe("+2.1%")
    expect(fmtPct(-1)).toBe("-1.0%")
    expect(fmtPct(null)).toBe("—")
  })
  it("fmtMoney signed", () => {
    expect(fmtMoney(640, true)).toBe("+$640")
    expect(fmtMoney(-17, true)).toBe("-$17")
    expect(fmtMoney(null)).toBe("—")
  })
  it("fmtScore rounds, fmtRvol suffixes", () => {
    expect(fmtScore(90.6)).toBe("91")
    expect(fmtScore(null)).toBe("—")
    expect(fmtRvol(1.8)).toBe("1.8×")
  })
  it("changeClass", () => {
    expect(changeClass(1)).toBe("pos")
    expect(changeClass(-1)).toBe("neg")
    expect(changeClass(null)).toBe("mut")
  })
  it("priceStatusDisplay maps all states and never collapses", () => {
    expect(priceStatusDisplay("live").fresh).toBe(true)
    expect(priceStatusDisplay("stale").fresh).toBe(false)
    expect(priceStatusDisplay("unavailable").label).toBe("no quote")
    expect(priceStatusDisplay(undefined).label).toBe("—")
  })
})
