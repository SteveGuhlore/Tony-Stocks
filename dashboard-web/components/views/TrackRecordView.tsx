"use client"

import { useCommandCenter } from "@/lib/hooks"
import { ViewHeader, Kpis, Panel, ResearchFooter, Awaiting } from "./shared"
import { MiniLine } from "@/components/kinetic/MiniLine"
import { fmtPct } from "@/lib/format"

export function TrackRecordView() {
  const { data, isLoading } = useCommandCenter()
  const a = data?.agreement
  const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`)
  const r = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`)

  return (
    <div>
      <ViewHeader title="Track Record" sub="two records racing — bot (cyan) vs Tony (amber)" />
      <Kpis
        items={[
          { label: "Bot win rate", value: pct(data?.bot_win_rate) },
          { label: "Tony win rate", value: pct(data?.tony_win_rate) },
          { label: "Bot avg R", value: r(data?.bot_avg_r) },
          { label: "Tony avg R", value: r(data?.tony_avg_r) },
        ]}
      />
      <Panel title="Equity · bot vs Tony (indexed 100)">
        {isLoading ? (
          <Awaiting what="equity history" />
        ) : (
          <MiniLine
            series={[
              { points: data?.equity_bot ?? [], color: "var(--cyan)", label: `Bot ${fmtPct(data?.bot_return_pct)}` },
              { points: data?.equity_tony ?? [], color: "var(--amber)", label: `Tony ${fmtPct(data?.tony_return_pct)}` },
            ]}
          />
        )}
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
      {data?.by_setup && data.by_setup.length > 0 && (
        <Panel title="By setup">
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
            <thead>
              <tr style={{ color: "var(--dim)", fontSize: 9, textTransform: "uppercase" }}>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Setup</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Trades</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Win%</th>
                <th style={{ textAlign: "left", padding: "4px 6px" }}>Avg R</th>
              </tr>
            </thead>
            <tbody>
              {data.by_setup.map((s) => (
                <tr key={s.setup} style={{ borderTop: "1px solid var(--line)" }}>
                  <td style={{ padding: "6px" }}>{s.setup}</td>
                  <td style={{ padding: "6px" }}>{s.trades}</td>
                  <td style={{ padding: "6px" }}>{Math.round(s.win_pct)}%</td>
                  <td style={{ padding: "6px", color: s.avg_r >= 0 ? "var(--pos)" : "var(--neg)" }}>{r(s.avg_r)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      )}
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
