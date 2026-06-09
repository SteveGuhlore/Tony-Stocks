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
            <p className="text-mut" style={{ fontSize: 11, lineHeight: 1.6, marginTop: 12 }}>
              Tony is the 2nd pass — he reviews each bot pick and either <b className="text-ink">backs</b> it or{" "}
              <b className="text-ink">overrides</b> (skip / close). Each is graded once the pick resolves.
            </p>
            <div style={{ display: "grid", gap: 5, marginTop: 8 }}>
              <Def color="var(--pos)" term="agreed · right" desc="backed the bot — it won" />
              <Def color="var(--neg)" term="agreed · wrong" desc="backed it — it lost" />
              <Def color="var(--amber)" term="Tony saved" desc="overrode, and it would've lost (good call)" />
              <Def color="var(--mut)" term="Tony missed" desc="overrode, and it would've won (cost)" />
            </div>
            <div
              className="text-mut"
              style={{ fontSize: 11, marginTop: 10, paddingTop: 8, borderTop: "1px solid var(--line)" }}
            >
              <b className="text-ink">Net so far:</b> {a.tony_saved + a.agreed_right} good vs{" "}
              {a.tony_missed + a.agreed_wrong} bad —{" "}
              {a.tony_saved >= a.tony_missed
                ? "his overrides are net-helpful."
                : "his overrides have cost more than they saved (small sample)."}
            </div>
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

function Def({ color, term, desc }: { color: string; term: string; desc: string }) {
  return (
    <div className="flex" style={{ gap: 8, alignItems: "baseline", fontSize: 11 }}>
      <b style={{ color, minWidth: 84, flexShrink: 0 }}>{term}</b>
      <span className="text-mut">{desc}</span>
    </div>
  )
}
