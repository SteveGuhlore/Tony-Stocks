"use client"
import { formatPrice } from "@/lib/format"
import type { PrepCandidate } from "@/lib/types"

const COLS = "1.4fr .6fr 1.2fr .8fr .8fr .8fr .6fr 1fr 1.6fr"

function Cell({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return <div style={{ textAlign: align, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{children}</div>
}

function HeaderRow() {
  return (
    <div className="mono" style={{
      display: "grid", gridTemplateColumns: COLS, gap: 10, padding: "8px 16px",
      fontSize: 9, letterSpacing: "0.06em", color: "var(--text-tertiary)",
      borderBottom: "1px solid var(--border)",
    }}>
      <div>SYMBOL</div>
      <div style={{ textAlign: "right" }}>SCORE</div>
      <div>SETUP</div>
      <div style={{ textAlign: "right" }}>ENTRY</div>
      <div style={{ textAlign: "right" }}>STOP</div>
      <div style={{ textAlign: "right" }}>TARGET</div>
      <div style={{ textAlign: "right" }}>R/R</div>
      <div>CONVICTION</div>
      <div>CATALYSTS</div>
    </div>
  )
}

function fmtRr(rr: number | null): string {
  return rr != null ? `${rr.toFixed(1)}x` : "—"
}

function catalystSummary(catalysts: Record<string, unknown>): string {
  const keys = Object.keys(catalysts)
  if (keys.length === 0) return "—"
  return keys.slice(0, 3).join(", ") + (keys.length > 3 ? ` +${keys.length - 3}` : "")
}

function CandidateRow({ candidate }: { candidate: PrepCandidate }) {
  const convictionColor =
    candidate.conviction === "high" ? "var(--green)"
      : candidate.conviction === "medium" ? "var(--amber)"
        : "var(--text-secondary)"

  return (
    <div
      className="board-row"
      style={{
        display: "grid", gridTemplateColumns: COLS, gap: 10, alignItems: "center",
        padding: "10px 16px", borderBottom: "1px solid var(--border-soft)",
      }}
    >
      <Cell>
        <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>{candidate.symbol}</span>{" "}
        <span style={{
          fontSize: 8, fontWeight: 800, letterSpacing: "0.06em", padding: "1px 4px", borderRadius: 3,
          background: "var(--brass)", color: "var(--bg-base)", verticalAlign: "middle",
        }}>PLANNED</span>
      </Cell>
      <Cell align="right">
        <span className="mono" style={{ fontSize: 12, color: "var(--text-primary)", fontWeight: 700 }}>
          {candidate.score.toFixed(1)}
        </span>
      </Cell>
      <Cell>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          {candidate.setup || "—"}
        </span>
      </Cell>
      <Cell align="right">
        <span className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          {formatPrice(candidate.entry)}
        </span>
      </Cell>
      <Cell align="right">
        <span className="mono" style={{ fontSize: 12, color: "var(--red)" }}>
          {formatPrice(candidate.stop)}
        </span>
      </Cell>
      <Cell align="right">
        <span className="mono" style={{ fontSize: 12, color: "var(--green)" }}>
          {formatPrice(candidate.target)}
        </span>
      </Cell>
      <Cell align="right">
        <span className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>
          {fmtRr(candidate.rr)}
        </span>
      </Cell>
      <Cell>
        <span className="mono" style={{ fontSize: 11, color: convictionColor, textTransform: "capitalize" }}>
          {candidate.conviction || "—"}
        </span>
      </Cell>
      <Cell>
        <span className="mono" style={{ fontSize: 10, color: "var(--text-tertiary)" }} title={Object.keys(candidate.catalysts).join(", ")}>
          {catalystSummary(candidate.catalysts)}
        </span>
      </Cell>
    </div>
  )
}

export const sectionLabel = (t: string) => (
  <div style={{ fontSize: 9, letterSpacing: "0.08em", color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: 4, padding: "0 16px" }}>{t}</div>
)

export function ShortlistTable({ candidates }: { candidates: PrepCandidate[] }) {
  if (candidates.length === 0) {
    return (
      <p style={{ color: "var(--text-tertiary)", fontSize: 12, padding: "16px" }}>
        Awaiting next off-hours run — shortlist will appear here once the engine has run.
      </p>
    )
  }
  return (
    <div>
      <HeaderRow />
      {candidates.map((c) => <CandidateRow key={c.symbol} candidate={c} />)}
    </div>
  )
}

export function NarrativeBlock({ label, text }: { label: string; text: string }) {
  return (
    <div style={{ padding: "12px 16px" }}>
      {sectionLabel(label)}
      {text
        ? <p style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6, margin: 0, whiteSpace: "pre-wrap" }}>{text}</p>
        : <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0 }}>—</p>
      }
    </div>
  )
}
