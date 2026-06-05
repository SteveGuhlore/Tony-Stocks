"use client"
import { usePaper } from "@/lib/hooks/usePaper"
import { HeadToHeadEquity } from "@/components/charts/HeadToHeadEquity"
import { OpenBook, ClosedBook, sectionLabel } from "@/components/paper/PaperBook"

function pct(wr: number | null | undefined): string {
  return wr != null ? `${Math.round(wr * 100)}%` : "—"
}

function Stat({ value, label, color = "var(--text-primary)" }: { value: string; label: string; color?: string }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>{label}</div>
    </div>
  )
}

export default function PaperPage() {
  const paper = usePaper()
  const s = paper.summary
  const realizedColor = s.realized_pl >= 0 ? "var(--green)" : "var(--red)"

  return (
    <div style={{ maxWidth: 860 }}>
      {/* header / KPIs */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: 10 }}>
          <span style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--amber)" }}>
            📄 PAPER BOOK · {paper.account_label}
          </span>
          {!paper.enabled && (
            <span style={{ fontSize: 10, color: "var(--text-tertiary)" }}>
              ⋯ paper trading off{paper.disabled_reason ? ` · ${paper.disabled_reason}` : ""}
            </span>
          )}
        </div>
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          <Stat value={String(s.open_count)} label="open" />
          <Stat value={String(s.closed_count)} label="closed" />
          <Stat value={String(s.target_hits)} label="target hits" color="var(--green)" />
          <Stat value={String(s.stop_hits)} label="stop hits" color="var(--red)" />
          <Stat value={pct(s.win_rate)} label="win rate" color={s.win_rate != null ? "var(--green)" : "var(--text-tertiary)"} />
          <Stat
            value={`${s.realized_pl >= 0 ? "+" : "−"}$${Math.abs(s.realized_pl).toFixed(0)}`}
            label="realized P/L"
            color={realizedColor}
          />
        </div>
      </div>

      {/* head-to-head equity vs Tony, indexed to 100 */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ fontSize: 9, letterSpacing: "0.08em", color: "var(--text-tertiary)", marginBottom: 8 }}>
          HEAD-TO-HEAD EQUITY · indexed to 100
        </div>
        <HeadToHeadEquity />
      </div>

      {/* open book */}
      <div className="card" style={{ marginBottom: 12, padding: "12px 0" }}>
        {sectionLabel("Open positions · live")}
        <OpenBook positions={paper.open} />
      </div>

      {/* closed book */}
      <div className="card" style={{ marginBottom: 12, padding: "12px 0" }}>
        {sectionLabel("Closed trades")}
        <ClosedBook positions={paper.closed} />
      </div>

      <p style={{ fontSize: 10, color: "var(--text-tertiary)", borderTop: "1px solid var(--border)", paddingTop: 10 }}>
        ⓘ Paper trading only · real Alpaca paper account, no live capital · live P/L marks against delayed quotes · not investment advice.
      </p>
    </div>
  )
}
