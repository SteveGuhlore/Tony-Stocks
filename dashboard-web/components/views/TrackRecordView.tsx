"use client"

import { useCommandCenter, usePaper, usePaperEquityCurve } from "@/lib/hooks"
import { ViewHeader, Kpis, Panel, ResearchFooter, Awaiting } from "./shared"
import { MiniLine } from "@/components/kinetic/MiniLine"
import { fmtPct } from "@/lib/format"

export function TrackRecordView() {
  const { data } = useCommandCenter()
  const paper = usePaper()
  const curve = usePaperEquityCurve()
  const a = data?.agreement
  const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`)
  const r = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`)

  // Bot side from /paper (win rate + computed avg R) and the indexed equity curve;
  // Tony side from the command-center record (mapped to flat fields in the api layer).
  const botWr = paper.data?.win_rate
  const botPts = (curve.data?.points ?? []).map((p) => ({ t: p.t, equity: p.index ?? p.equity }))

  return (
    <div>
      <ViewHeader title="Track Record" sub="two records racing — bot (cyan) vs Tony (amber)" />
      <Kpis
        items={[
          { label: "Bot win rate", value: pct(botWr != null ? botWr * 100 : null) },
          { label: "Tony win rate", value: pct(data?.tony_win_rate != null ? data.tony_win_rate * 100 : null) },
          { label: "Bot avg R", value: r(paper.data?.avg_r) },
          { label: "Tony avg R", value: r(data?.tony_avg_r) },
        ]}
      />
      <Panel title="Equity · bot vs Tony (indexed 100)">
        <MiniLine
          baseline={100}
          series={[
            { points: botPts, color: "var(--cyan)", label: `Bot ${fmtPct(curve.data?.return_pct)}` },
            { points: data?.equity_tony ?? [], color: "var(--amber)", label: `Tony ${fmtPct(data?.tony_return_pct)}` },
          ]}
        />
      </Panel>
      <Panel title="Does the 2nd pass help?">
        {a ? (
          <div className="grid gap-[6px]" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
            <Agree n={a.agreed_right} label="agreed · right" color="var(--pos)" />
            <Agree n={a.agreed_wrong} label="agreed · wrong" color="var(--neg)" />
            <Agree n={a.tony_saved} label="Tony saved" color="var(--amber)" />
            <Agree n={a.tony_missed} label="Tony missed" color="var(--mut)" />
          </div>
        ) : (
          <Awaiting what="agreement stats" />
        )}
      </Panel>
      <ResearchFooter />
    </div>
  )
}

function Agree({ n, label, color }: { n: number; label: string; color: string }) {
  return (
    <div className="kt-panel" style={{ padding: "8px", textAlign: "center" }}>
      <b className="font-display block" style={{ fontSize: 17, color }}>
        {n}
      </b>
      <span className="text-dim" style={{ fontSize: 8.5 }}>
        {label}
      </span>
    </div>
  )
}
