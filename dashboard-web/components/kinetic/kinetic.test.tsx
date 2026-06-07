import { describe, it, expect } from "vitest"
import { render, screen } from "@testing-library/react"
import { ScoreGlyph } from "./ScoreGlyph"
import { VerdictPill } from "./VerdictPill"
import { PlanRail } from "./PlanRail"

describe("ScoreGlyph", () => {
  it("renders score and an aria label with sub-scores", () => {
    render(<ScoreGlyph score={91} sub={{ trend: 88, momentum: 80, volume: 95, risk: 40, setup: 82 }} />)
    expect(screen.getByText("91")).toBeInTheDocument()
    expect(screen.getByRole("img").getAttribute("aria-label")).toContain("Risk 40")
  })
  it("degrades null score to em-dash without crashing", () => {
    render(<ScoreGlyph score={null} sub={null} />)
    expect(screen.getByText("—")).toBeInTheDocument()
  })
})

describe("VerdictPill", () => {
  it("shows reaffirm for known verdict", () => {
    render(<VerdictPill verdict="reaffirm" />)
    expect(screen.getByText(/reaffirm/)).toBeInTheDocument()
  })
  it("degrades unknown verdict to awaiting", () => {
    render(<VerdictPill verdict="pass" />)
    expect(screen.getByText(/awaiting/)).toBeInTheDocument()
  })
})

describe("PlanRail", () => {
  it("renders no-plan state when levels missing", () => {
    render(<PlanRail stop={null} entry={null} target={null} current={null} />)
    expect(screen.getByText("no plan")).toBeInTheDocument()
  })
  it("labels levels when valid", () => {
    const { container } = render(<PlanRail stop={178.2} entry={183} target={192.5} current={182.4} />)
    expect(container.querySelector("[aria-label*='entry']")).toBeTruthy()
  })
})
