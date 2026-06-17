"use client"

import type { EquityPoint } from "@/lib/types"

/** Lightweight SVG line for equity curves (head-to-head). Degrades to empty. */
export function MiniLine({
  series,
  height = 120,
}: {
  series: { points: EquityPoint[]; color: string; label: string }[]
  height?: number
}) {
  // Only series with >= 2 points can be drawn. Treat the chart as empty unless at
  // least one such series exists — otherwise two 1-point series slip past a naive
  // total-count guard and render a blank SVG with only legends.
  const drawable = series.filter((s) => s.points.length >= 2)
  const all = drawable.flatMap((s) => s.points.map((p) => p.equity))
  if (drawable.length === 0 || all.length < 2) {
    return (
      <div className="grid place-items-center text-dim" style={{ height, fontSize: 11 }}>
        Awaiting equity history.
      </div>
    )
  }
  const W = 600
  const min = Math.min(...all)
  const max = Math.max(...all)
  const rg = max - min || 1
  return (
    <div>
      <svg width="100%" height={height} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none">
        {drawable.map((s) => {
          if (s.points.length < 2) return null
          const pts = s.points
            .map((p, i) => {
              const x = (i / (s.points.length - 1)) * W
              const y = height - ((p.equity - min) / rg) * (height - 8) - 4
              return `${x.toFixed(1)},${y.toFixed(1)}`
            })
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
