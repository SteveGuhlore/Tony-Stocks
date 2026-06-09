"use client"

import { useCommandCenter, usePaper, useEquityCompare } from "@/lib/hooks"
import { ViewHeader, Kpis, Panel, ResearchFooter, Awaiting } from "./shared"
import { MiniLine } from "@/components/kinetic/MiniLine"
import { fmtPct } from "@/lib/format"

export function TrackRecordView() {
  const { data } = useCommandCenter()
  const paper = usePaper()
  const cmp = useEquityCompare("1W", "1H") // both accounts, one shared HOURLY time axis
  const a = data?.agreement
  const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`)
  const r = (v: number | null | undefined) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${v.toFixed(2)}`)

  // Win/avg-R: bot from /paper, Tony from the command-center record. Equity chart:
  // the time-aligned /paper/equity-compare (both accounts, same period/timeframe).
  const botWr = paper.data?.win_rate

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
          yUnit="return"
          xTime
          series={[
            { points: cmp.data?.bot?.points ?? [], color: "var(--cyan)", label: `Bot ${fmtPct(cmp.data?.bot?.return_pct)}` },
            { points: cmp.data?.tony?.points ?? [], color: "var(--amber)", label: `Tony ${fmtPct(cmp.data?.tony?.return_pct)}` },
          ]}
        />
      </Panel>
      <Panel title="Does the 2nd pass help?">
        {a ? (
          <>
            <div className="grid gap-[6px]" style={{ gridTemplateColumns: "repeat(4,1fr)" }}>
              <Agree n={a.agreed_right} label="agreed · right" color="var(--pos)" />
              <Agree n={a.agreed_wrong} label="agreed · wrong" color="var(--neg)" />
              <Agree n={a.tony_saved} label="Tony saved" color="var(--amber)" />
              <Agree n={a.tony_missed} label="Tony missed" color="var(--mut)" />
            </div>
            <p className="text-mut" style={{ fontSize: 11, lineHeight: 1.7, marginTop: 10 }}>
              Tony is the 2nd pass: he reviews each bot pick and either backs it or overrides (skip/close).
              Each is graded once the pick resolves.
              <br />
              <b style={{ color: "var(--pos)" }}>agreed · right</b> — backed the bot, it won ·{" "}
              <b style={{ color: "var(--neg)" }}>agreed · wrong</b> — backed it, it lost ·{" "}
              <b style={{ color: "var(--amber)" }}>Tony saved</b> — overrode and it would&apos;ve <i>lost</i> (good call) ·{" "}
              <b className="text-ink">Tony missed</b> — overrode and it would&apos;ve <i>won</i> (cost).
              <br />
              <span className="text-dim">
                Net: {a.tony_saved + a.agreed_right} good calls vs {a.tony_missed + a.agreed_wrong} bad —{" "}
                {a.tony_saved >= a.tony_missed
                  ? "his overrides are net-helpful so far."
                  : "his overrides have cost more than they saved so far (small sample)."}
              </span>
            </p>
          </>
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
