import { describe, it, expect } from "vitest"
import { normalizeVerdict } from "./verdict"

describe("normalizeVerdict", () => {
  it("maps reaffirm-like strings", () => {
    for (const s of ["reaffirm", "REAFF", "confirmed", "agree", "↑ reaffirm"]) {
      expect(normalizeVerdict(s).kind).toBe("reaff")
    }
  })
  it("maps override-like strings", () => {
    for (const s of ["override", "reject", "avoid", "⤳ override"]) {
      expect(normalizeVerdict(s).kind).toBe("over")
    }
  })
  it("degrades pass / empty / null / unknown to awaiting (never throws)", () => {
    for (const s of ["pass", "", "   ", null, undefined, "weird-token"] as const) {
      expect(normalizeVerdict(s).kind).toBe("awaiting")
    }
  })
  it("always returns a className matching kt-pill suffixes", () => {
    const d = normalizeVerdict("reaffirm")
    expect(d.className).toBe("reaff")
    expect(d.label).toContain("reaffirm")
  })
})
