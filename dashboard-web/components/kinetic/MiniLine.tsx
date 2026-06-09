"use client"

import type { EquityPoint } from "@/lib/types"

/** Lightweight SVG equity line(s) with a y-axis (min/max labels) and an optional
 *  indexed baseline (dashed reference line, e.g. 100). Degrades to an "awaiting"
 *  placeholder under 2 points. Y is 1:1 with pixels (viewBox height == height), so
 *  the HTML y-labels line up with the SVG gridlines even though x is stretched. */
export function MiniLine({
  series,
  height = 120,
  baseline = null,
}: {
  series: { points: EquityPoint[]; color: string; label: string }[]
  height?: number
  baseline?: number | null
}) {
  const all = series.flatMap((s) => s.points.map((p) => p.equity))
  if (all.length < 2) {
    return (
      <div className="grid place-items-center text-dim" style={{ height, fontSize: 11 }}>
        Awaiting equity history.
      </div>
    )
  }
  const W = 600
  const padT = 8
  const padB = 6
  const plotH = height - padT - padB
  let min = Math.min(...all)
  let max = Math.max(...all)
  if (baseline != null) {
    min = Math.min(min, baseline)
    max = Math.max(max, baseline)
  }
  const rg = max - min || 1
  const yOf = (v: number) => padT + plotH - ((v - min) / rg) * plotH
  const fmt = (v: number) =>
    Math.abs(v) >= 1000 ? v.toFixed(0) : Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2)

  const ticks: { v: number; base: boolean }[] = [{ v: max, base: false }]
  if (baseline != null && baseline > min && baseline < max) ticks.push({ v: baseline, base: true })
  ticks.push({ v: min, base: false })

  return (
    <div style={{ position: "relative", paddingLeft: 38 }}>
      {/* y-axis labels — crisp HTML overlay (SVG text would stretch with x) */}
      <div style={{ position: "absolute", left: 0, top: 0, width: 34, height }}>
        {ticks.map((t, i) => (
          <span
            key={i}
            style={{
              position: "absolute",
              right: 4,
              top: yOf(t.v) - 6,
              fontSize: 9,
              color: t.base ? "var(--mut)" : "var(--dim)",
            }}
          >
            {fmt(t.v)}
          </span>
        ))}
      </div>
      <svg width="100%" height={height} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none">
        {/* gridlines + baseline */}
        {ticks.map((t, i) => (
          <line
            key={i}
            x1={0}
            x2={W}
            y1={yOf(t.v)}
            y2={yOf(t.v)}
            stroke={t.base ? "var(--mut)" : "var(--line)"}
            strokeWidth={t.base ? 1 : 0.5}
            strokeDasharray={t.base ? "5 4" : undefined}
          />
        ))}
        {/* series */}
        {series.map((s) => {
          if (s.points.length < 2) return null
          const pts = s.points
            .map((p, i) => `${((i / (s.points.length - 1)) * W).toFixed(1)},${yOf(p.equity).toFixed(1)}`)
            .join(" ")
          return <polyline key={s.label} fill="none" stroke={s.color} strokeWidth={2.5} points={pts} />
        })}
      </svg>
      <div className="flex gap-3" style={{ fontSize: 10, marginTop: 6 }}>
        {series.map((s) => (
          <span key={s.label} className="flex items-center gap-1">
            <span style={{ display: "inline-block", width: 10, height: 2, background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
    </div>
  )
}
