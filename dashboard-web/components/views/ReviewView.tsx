"use client"

import { useMemo } from "react"
import { useCockpit } from "@/lib/hooks"
import { ViewHeader, Kpis, Panel } from "./shared"

/** After-close review — derived from the cockpit read model. The triggered names split
 *  into profit / loss / flat (the three sum to Triggered); "watching" is a separate
 *  cohort (entry never fired), kept out of that sum to avoid the 10-vs-7 confusion. */
export function ReviewView() {
  const { data } = useCockpit()
  const rows = data?.rows ?? []
  const stats = useMemo(() => {
    const triggered = rows.filter((r) => r.entry_triggered || r.status === "triggered")
    const winners = triggered.filter((r) => (r.research_unrealized_pl_pct ?? 0) > 0).length
    const losers = triggered.filter((r) => (r.research_unrealized_pl_pct ?? 0) < 0).length
    const flat = triggered.length - winners - losers
    const watching = rows.filter((r) => r.status === "watching").length
    return { triggered: triggered.length, winners, losers, flat, watching }
  }, [rows])

  return (
    <div>
      <ViewHeader title="After Close · Review" sub={data?.generated_at ?? "session recap"} />
      <Kpis
        items={[
          { label: "Triggered", value: stats.triggered },
          { label: "In profit", value: stats.winners, tone: "pos" },
          { label: "In loss", value: stats.losers, tone: "neg" },
          { label: "Flat", value: stats.flat },
        ]}
      />
      <div className="text-dim" style={{ fontSize: 10, marginTop: 4 }}>
        in profit + in loss + flat = triggered ({stats.winners} + {stats.losers} + {stats.flat} ={" "}
        {stats.triggered})
      </div>
      <Panel title="What this section means">
        <p className="text-mut" style={{ fontSize: 12, lineHeight: 1.7 }}>
          {stats.triggered === 0 ? (
            "No entries triggered this session — the scanner stayed in watch mode."
          ) : (
            <>
              <b className="text-ink">Triggered ({stats.triggered})</b> — entries that actually fired today. Of
              those, on the live (research) mark: <span style={{ color: "var(--pos)" }}>{stats.winners} in profit</span>,{" "}
              <span style={{ color: "var(--neg)" }}>{stats.losers} in loss</span>, and{" "}
              <b className="text-ink">{stats.flat} flat</b> — exactly breakeven or no live price yet (that's why
              only {stats.winners + stats.losers} show a P/L direction, not all {stats.triggered}).
            </>
          )}
        </p>
        <p className="text-mut" style={{ fontSize: 12, lineHeight: 1.7, marginTop: 8 }}>
          <b className="text-ink">Still watching ({stats.watching})</b> — candidates whose entry trigger has{" "}
          <i>not</i> fired. They aren&apos;t positions and aren&apos;t part of the triggered count above. The full
          EOD recap is produced by the after-market-review pipeline.
        </p>
      </Panel>
    </div>
  )
}
