import { describe, it, expect } from "vitest"
import { verdictDisplay, statusKind } from "@/lib/signal"

describe("verdictDisplay", () => {
  it("maps known verdicts to label + tone", () => {
    expect(verdictDisplay("reaffirm")).toEqual({ label: "✓ reaffirm", tone: "green" })
    expect(verdictDisplay("adjust")).toEqual({ label: "◐ adjust", tone: "amber" })
    expect(verdictDisplay("override")).toEqual({ label: "⊘ override", tone: "red" })
    expect(verdictDisplay("close")).toEqual({ label: "✕ close", tone: "red" })
  })
  it("treats null/unknown as awaiting handoff", () => {
    expect(verdictDisplay(null)).toEqual({ label: "⋯ awaiting", tone: "muted" })
    expect(verdictDisplay("banana")).toEqual({ label: "⋯ awaiting", tone: "muted" })
  })
})

describe("statusKind", () => {
  it("is triggered when entry fired and not closed", () =>
    expect(statusKind({ entry_triggered: true, status: "open" })).toBe("triggered"))
  it("is closed when status says closed", () =>
    expect(statusKind({ entry_triggered: true, status: "closed" })).toBe("closed"))
  it("is watching when not triggered", () =>
    expect(statusKind({ entry_triggered: false, status: "open" })).toBe("watching"))
})
