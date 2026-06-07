"use client"

import { useMemo } from "react"
import { useCockpit, useCommandCenter } from "@/lib/hooks"
import { ViewHeader, Panel, Awaiting } from "./shared"
import { subScoreArray } from "@/lib/rows"
import { SUB_SCORE_LABELS, SUB_SCORE_KEYS } from "@/lib/tokens"

/** Scanner X-ray — score distribution, sub-score attribution, live weights (read-only). */
export function ScannerXrayView() {
  const { data } = useCockpit()
  const cc = useCommandCenter()
  const rows = data?.rows ?? []

  const dist = useMemo(() => {
    const buckets = new Array(10).fill(0)
    for (const r of rows) {
      if (r.score == null) continue
      const b = Math.min(9, Math.max(0, Math.floor(r.score / 10)))
      buckets[b]++
    }
    const max = Math.max(1, ...buckets)
    return { buckets, max }
  }, [rows])

  const avgSub = useMemo(() => {
    const sums = [0, 0, 0, 0, 0]
    let n = 0
    for (const r of rows) {
      if (!r.sub_scores) continue
      const arr = subScoreArray(r.sub_scores)
      arr.forEach((v, i) => (sums[i] += v))
      n++
    }
    return n ? sums.map((s) => Math.round(s / n)) : null
  }, [rows])

  const weights = cc.data?.weights
  const proposed = cc.data?.proposed_weights

  return (
    <div>
      <ViewHeader title="Scanner X-ray" sub="why the bot scores what it scores" />
      <Panel title={`Score distribution · ${rows.length} picks`}>
        <div className="flex items-end gap-[5px]" style={{ height: 90 }}>
          {dist.buckets.map((b, i) => (
            <div
              key={i}
              title={`${i * 10}–${i * 10 + 9}: ${b}`}
              style={{
                flex: 1,
                height: `${(b / dist.max) * 100}%`,
                minHeight: 2,
                background: "linear-gradient(180deg,var(--cyan),rgba(55,224,255,.25))",
                borderRadius: "3px 3px 0 0",
              }}
            />
          ))}
        </div>
        <div className="flex justify-between text-dim" style={{ fontSize: 9, marginTop: 6 }}>
          <span>0</span>
          <span>50</span>
          <span>90+</span>
        </div>
      </Panel>

      <Panel title="Funnel attrition">
        {data?.counts ? (
          <div>
            {[
              { l: "Picks (total)", v: data.counts.total },
              { l: "Watching", v: data.counts.watching },
              { l: "Near entry", v: data.counts.near },
              { l: "Triggered", v: data.counts.triggered },
            ].map((f) => {
              const max = Math.max(1, data.counts.total)
              return (
                <div key={f.l} className="flex items-center gap-2" style={{ margin: "5px 0", fontSize: 11 }}>
                  <span className="text-mut" style={{ width: 110 }}>
                    {f.l}
                  </span>
                  <div style={{ flex: 1, height: 7, background: "rgba(255,255,255,.06)", borderRadius: 4, overflow: "hidden" }}>
                    <div style={{ height: "100%", width: `${(f.v / max) * 100}%`, background: "var(--cyan)" }} />
                  </div>
                  <span className="num" style={{ width: 48, textAlign: "right" }}>
                    {f.v}
                  </span>
                </div>
              )
            })}
          </div>
        ) : (
          <Awaiting what="funnel counts" />
        )}
      </Panel>

      <Panel title="Average sub-score (attribution)">
        {avgSub ? (
          SUB_SCORE_KEYS.map((k, i) => (
            <div key={k} className="flex items-center gap-2" style={{ margin: "5px 0", fontSize: 11 }}>
              <span className="text-mut" style={{ width: 90 }}>
                {SUB_SCORE_LABELS[k]}
              </span>
              <div style={{ flex: 1, height: 7, background: "rgba(255,255,255,.06)", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${avgSub[i]}%`, background: k === "risk" && avgSub[i] < 50 ? "var(--warn)" : "var(--cyan)" }} />
              </div>
              <span className="num" style={{ width: 28, textAlign: "right" }}>
                {avgSub[i]}
              </span>
            </div>
          ))
        ) : (
          <Awaiting what="sub-score data" />
        )}
      </Panel>

      <Panel title="Live weights (read-only)">
        {weights ? (
          <div className="text-mut" style={{ fontSize: 12, lineHeight: 1.8 }}>
            {Object.entries(weights).map(([k, v]) => (
              <span key={k} style={{ marginRight: 12 }}>
                {k} <b className="text-ink">{v}</b>
                {proposed && proposed[k] != null && proposed[k] !== v && (
                  <span className="text-warn"> → {proposed[k]} proposed</span>
                )}
              </span>
            ))}
            <span className="text-dim"> · change via two-key CLI</span>
          </div>
        ) : (
          <Awaiting what="weight configuration" />
        )}
      </Panel>
    </div>
  )
}
