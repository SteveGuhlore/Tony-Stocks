"use client"
import { useMorningPrep } from "@/lib/hooks/useMorningPrep"
import { ShortlistTable, NarrativeBlock, sectionLabel } from "@/components/morning/MorningPrep"

function Stat({ value, label, color = "var(--text-primary)" }: { value: string; label: string; color?: string }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>{label}</div>
    </div>
  )
}

function fmtPhase(phase: string): string {
  return phase ? phase.replace(/_/g, " ").toUpperCase() : "—"
}

function fmtDate(etDate: string): string {
  if (!etDate) return "—"
  return etDate
}

export default function MorningPage() {
  const prep = useMorningPrep()

  return (
    <div style={{ maxWidth: 1040 }}>
      {/* header / KPIs */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <span style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--brass)" }}>
            🌅 MORNING PREP · {fmtDate(prep.et_date)}
          </span>
          {prep.phase && (
            <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>
              {fmtPhase(prep.phase)}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <Stat value={String(prep.shortlist.length)} label="shortlisted" />
          <Stat
            value={prep.shortlist.length > 0 ? prep.shortlist[0].score.toFixed(1) : "—"}
            label="top score"
            color={prep.shortlist.length > 0 ? "var(--green)" : "var(--text-tertiary)"}
          />
          <Stat
            value={prep.generated_at ? new Date(prep.generated_at).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "—"}
            label="generated at"
            color="var(--text-secondary)"
          />
        </div>
      </div>

      {/* shortlist table */}
      <div className="card" style={{ marginBottom: 12, padding: "12px 0" }}>
        {sectionLabel("Shortlist · all positions planned only — no off-hours entries")}
        <ShortlistTable candidates={prep.shortlist} />
      </div>

      {/* what changed overnight */}
      <div className="card" style={{ marginBottom: 12 }}>
        <NarrativeBlock label="What changed overnight" text={prep.what_changed_overnight} />
      </div>

      {/* plan for open */}
      <div className="card" style={{ marginBottom: 12 }}>
        <NarrativeBlock label="Plan for open" text={prep.plan_for_open} />
      </div>

      <p style={{ fontSize: 10, color: "var(--text-tertiary)", borderTop: "1px solid var(--border)", paddingTop: 10 }}>
        ⓘ Off-hours research only · all rows are PLANNED — no positions are entered outside market hours · not investment advice.
      </p>
    </div>
  )
}
