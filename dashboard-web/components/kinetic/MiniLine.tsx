"use client"

import { useRef, useState } from "react"
import type { EquityPoint } from "@/lib/types"

/** Lightweight SVG equity line(s) with a labeled y-axis, an optional indexed baseline
 *  (dashed reference, e.g. 100), and a hover/tap crosshair that reads each series'
 *  value at the cursor (like a stock chart). `yUnit="return"` labels y as % vs the
 *  baseline. Y is 1:1 with pixels (viewBox height == height) so HTML overlays line up
 *  with the SVG even though x is stretched. Degrades to a placeholder under 2 points. */
export function MiniLine({
  series,
  height = 120,
  baseline = null,
  yUnit = "value",
}: {
  series: { points: EquityPoint[]; color: string; label: string }[]
  height?: number
  baseline?: number | null
  yUnit?: "value" | "return"
}) {
  const wrapRef = useRef<HTMLDivElement>(null)
  const [frac, setFrac] = useState<number | null>(null)

  const all = series.flatMap((s) => s.points.map((p) => p.equity))
  if (all.length < 2) {
    return (
      <div className="grid place-items-center text-dim" style={{ height, fontSize: 11 }}>
        Awaiting equity history.
      </div>
    )
  }

  const W = 600
  const GUT = 40 // left gutter (y-axis), px
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
  const labelOf = (v: number) =>
    yUnit === "return" && baseline != null
      ? `${v - baseline > 0 ? "+" : ""}${(v - baseline).toFixed(1)}%`
      : fmt(v)

  const ticks: { v: number; base: boolean }[] = [{ v: max, base: false }]
  if (baseline != null && baseline > min && baseline < max) ticks.push({ v: baseline, base: true })
  ticks.push({ v: min, base: false })

  // linear-interpolated value of a series at fraction f (0..1) of its span
  const valueAt = (pts: EquityPoint[], f: number): number | null => {
    if (!pts.length) return null
    if (pts.length === 1) return pts[0].equity
    const x = f * (pts.length - 1)
    const i0 = Math.floor(x)
    const i1 = Math.min(pts.length - 1, i0 + 1)
    const t = x - i0
    return pts[i0].equity * (1 - t) + pts[i1].equity * t
  }

  const onMove = (clientX: number) => {
    const el = wrapRef.current
    if (!el) return
    const rect = el.getBoundingClientRect()
    const plotW = rect.width - GUT
    if (plotW <= 0) return
    setFrac(Math.max(0, Math.min(1, (clientX - rect.left - GUT) / plotW)))
  }
  const leftCalc = (f: number) => `calc(${GUT}px + (100% - ${GUT}px) * ${f})`

  return (
    <div>
      <div
        ref={wrapRef}
        style={{ position: "relative", paddingLeft: GUT, touchAction: "none", cursor: "crosshair" }}
        onPointerMove={(e) => onMove(e.clientX)}
        onPointerDown={(e) => onMove(e.clientX)}
        onPointerLeave={() => setFrac(null)}
        onPointerUp={() => setFrac(null)}
      >
        {/* y-axis labels — crisp HTML overlay */}
        <div style={{ position: "absolute", left: 0, top: 0, width: GUT - 4, height }}>
          {ticks.map((t, i) => (
            <span
              key={i}
              style={{ position: "absolute", right: 4, top: yOf(t.v) - 6, fontSize: 9, color: t.base ? "var(--mut)" : "var(--dim)" }}
            >
              {labelOf(t.v)}
            </span>
          ))}
        </div>
        <svg width="100%" height={height} viewBox={`0 0 ${W} ${height}`} preserveAspectRatio="none">
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
          {series.map((s) => {
            if (s.points.length < 2) return null
            const pts = s.points
              .map((p, i) => `${((i / (s.points.length - 1)) * W).toFixed(1)},${yOf(p.equity).toFixed(1)}`)
              .join(" ")
            return <polyline key={s.label} fill="none" stroke={s.color} strokeWidth={2.5} points={pts} />
          })}
        </svg>

        {/* hover crosshair + per-series dots (x via calc %, y in px) */}
        {frac != null && (
          <>
            <div
              style={{ position: "absolute", left: leftCalc(frac), top: padT, width: 1, height: plotH, background: "var(--mut)", opacity: 0.55, pointerEvents: "none" }}
            />
            {series.map((s) => {
              const v = valueAt(s.points, frac)
              if (v == null) return null
              return (
                <div
                  key={s.label}
                  style={{ position: "absolute", left: leftCalc(frac), top: yOf(v), width: 7, height: 7, marginLeft: -3.5, marginTop: -3.5, borderRadius: "50%", background: s.color, pointerEvents: "none" }}
                />
              )
            })}
          </>
        )}
      </div>

      {/* legend — updates with the hovered value(s) */}
      <div className="flex gap-3" style={{ fontSize: 10, marginTop: 6, minHeight: 14 }}>
        {series.map((s) => {
          const v = frac != null ? valueAt(s.points, frac) : null
          return (
            <span key={s.label} className="flex items-center gap-1">
              <span style={{ display: "inline-block", width: 10, height: 2, background: s.color }} />
              {s.label}
              {v != null && (
                <b className="text-ink" style={{ marginLeft: 3 }}>
                  {labelOf(v)}
                </b>
              )}
            </span>
          )
        })}
      </div>
    </div>
  )
}
