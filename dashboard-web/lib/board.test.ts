import { describe, it, expect } from "vitest"
import { isClosedOutcome, nearEntry, boardStatus, STATUS_DISPLAY } from "@/lib/board"

describe("isClosedOutcome", () => {
  it("treats terminal labels as closed", () => {
    expect(isClosedOutcome("target_hit")).toBe(true)
    expect(isClosedOutcome("stop_hit")).toBe(true)
    expect(isClosedOutcome("failed_setup")).toBe(true)
  })
  it("treats open/null as not closed", () => {
    expect(isClosedOutcome(null)).toBe(false)
    expect(isClosedOutcome("still_open")).toBe(false)
    expect(isClosedOutcome(undefined)).toBe(false)
  })
})

describe("nearEntry", () => {
  it("is true within the default 0.75% band", () => {
    expect(nearEntry(100, 100.5)).toBe(true)
    expect(nearEntry(100, 99.5)).toBe(true)
  })
  it("is false outside the band", () => {
    expect(nearEntry(100, 102)).toBe(false)
  })
  it("honors a custom threshold", () => {
    expect(nearEntry(100, 102, 3)).toBe(true)
  })
  it("is false on missing/zero inputs", () => {
    expect(nearEntry(null, 100)).toBe(false)
    expect(nearEntry(100, undefined)).toBe(false)
    expect(nearEntry(0, 0)).toBe(false)
  })
})

describe("boardStatus", () => {
  const base = { entry_triggered: false, outcome_label: null as string | null, entry: 100 }
  it("is closed for a terminal outcome", () =>
    expect(boardStatus({ ...base, outcome_label: "target_hit" }, 100)).toBe("closed"))
  it("is triggered when entry fired", () =>
    expect(boardStatus({ ...base, entry_triggered: true }, 105)).toBe("triggered"))
  it("is armed when near entry but not triggered", () =>
    expect(boardStatus(base, 100.4)).toBe("armed"))
  it("is watching when far from entry", () =>
    expect(boardStatus(base, 90)).toBe("watching"))
  it("prefers closed over triggered", () =>
    expect(boardStatus({ ...base, entry_triggered: true, outcome_label: "stop_hit" }, 90)).toBe("closed"))
})

describe("STATUS_DISPLAY", () => {
  it("has an entry for every StatusKind with a label and tone", () => {
    for (const kind of ["triggered", "armed", "watching", "closed"] as const) {
      expect(STATUS_DISPLAY[kind].label.length).toBeGreaterThan(0)
      expect(STATUS_DISPLAY[kind].tone.length).toBeGreaterThan(0)
    }
  })
})
