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

  // Sub-score SPREAD (min · median · max per dimension) — averages alone hide which
  // dimension is the bottleneck vs which is broadly strong.
  const spread = useMemo(() => {
    const cols: number[][] = [[], [], [], [], []]
    for (const r of rows) {
      if (!r.sub_scores) continue
      subScoreArray(r.sub_scores).forEach((v, i) => cols[i].push(v))
    }
    if (!cols[0].length) return null
    return cols.map((arr) => {
      const s = [...arr].sort((a, b) => a - b)
      return { min: s[0], med: s[Math.floor(s.length / 2)], max: s[s.length - 1] }
    })
  }, [rows])

  // PRICE BANDS — where the picks concentrate (more meaningful now the universe spans $4–$1000).
  const priceBands = useMemo(() => {
    const edges = [0, 10, 25, 50, 100, 250, Infinity]
    const labels = ["<$10", "$10–25", "$25–50", "$50–100", "$100–250", "$250+"]
    const counts = new Array(labels.length).fill(0)
    for (const r of rows) {
      const p = r.close
      if (p == null) continue
      for (let i = 0; i < edges.length - 1; i++) {
        if (p >= edges[i] && p < edges[i + 1]) { counts[i]++; break }
      }
    }
    return { labels, counts, max: Math.max(1, ...counts) }
  }, [rows])

  const weights = cc.data?.weights
  const proposed = cc.data?.proposed_weights

  // SCORE DRIVERS — each dimension's share of the composite = avg sub-score × its live weight.
  // Shows what actually moves the score, not just the raw sub-scores. Weight keys are e.g.
  // "trend_weight" / "setup_quality_weight", so match by sub-score-key prefix.
  const drivers = useMemo(() => {
    if (!avgSub || !weights) return null
    const parts = SUB_SCORE_KEYS.map((k, i) => {
      const w = Object.entries(weights).find(([wk]) => wk.toLowerCase().startsWith(k))?.[1] ?? 0
      return { key: k, contrib: avgSub[i] * w }
    })
    const total = parts.reduce((a, p) => a + p.contrib, 0) || 1
    return parts.map((p) => ({ ...p, pct: Math.round((p.contrib / total) * 100) }))
  }, [avgSub, weights])

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

      <Panel title="Sub-score range · min · median · max">
        {spread ? (
          SUB_SCORE_KEYS.map((k, i) => {
            const s = spread[i]
            return (
              <div key={k} className="flex items-center gap-2" style={{ margin: "5px 0", fontSize: 11 }}>
                <span className="text-mut" style={{ width: 90 }}>{SUB_SCORE_LABELS[k]}</span>
                <div style={{ flex: 1, height: 7, background: "rgba(255,255,255,.06)", borderRadius: 4, position: "relative" }}>
                  <div style={{ position: "absolute", left: `${s.min}%`, width: `${Math.max(0, s.max - s.min)}%`, top: 0, bottom: 0, background: "rgba(55,224,255,.35)", borderRadius: 4 }} />
                  <div style={{ position: "absolute", left: `${s.med}%`, top: -1, bottom: -1, width: 2, background: "var(--cyan)" }} />
                </div>
                <span className="num text-dim" style={{ width: 76, textAlign: "right" }}>{s.min}·{s.med}·{s.max}</span>
              </div>
            )
          })
        ) : (
          <Awaiting what="sub-score data" />
        )}
      </Panel>

      <Panel title="Score drivers · avg × live weight">
        {drivers ? (
          drivers.map((d) => (
            <div key={d.key} className="flex items-center gap-2" style={{ margin: "5px 0", fontSize: 11 }}>
              <span className="text-mut" style={{ width: 90 }}>{SUB_SCORE_LABELS[d.key]}</span>
              <div style={{ flex: 1, height: 7, background: "rgba(255,255,255,.06)", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${d.pct}%`, background: "var(--lime)" }} />
              </div>
              <span className="num" style={{ width: 36, textAlign: "right" }}>{d.pct}%</span>
            </div>
          ))
        ) : (
          <Awaiting what="weight configuration" />
        )}
      </Panel>

      <Panel title="Price bands">
        {rows.length ? (
          priceBands.labels.map((l, i) => (
            <div key={l} className="flex items-center gap-2" style={{ margin: "5px 0", fontSize: 11 }}>
              <span className="text-mut" style={{ width: 90 }}>{l}</span>
              <div style={{ flex: 1, height: 7, background: "rgba(255,255,255,.06)", borderRadius: 4, overflow: "hidden" }}>
                <div style={{ height: "100%", width: `${(priceBands.counts[i] / priceBands.max) * 100}%`, background: "var(--cyan)" }} />
              </div>
              <span className="num" style={{ width: 36, textAlign: "right" }}>{priceBands.counts[i]}</span>
            </div>
          ))
        ) : (
          <Awaiting what="picks" />
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
