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
  xTime = false,
}: {
  series: { points: EquityPoint[]; color: string; label: string }[]
  height?: number
  baseline?: number | null
  yUnit?: "value" | "return"
  xTime?: boolean
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

  // x-axis time labels: pull timestamps from the first series whose points carry a
  // parseable date `t`. Intraday (avg gap < 20h) shows a clock (M/D HH:MM); daily shows M/D.
  const refPts = series.find((s) => s.points.length >= 2 && !Number.isNaN(Date.parse(String(s.points[0].t))))?.points
  const spanMs =
    refPts && refPts.length >= 2 ? Date.parse(String(refPts[refPts.length - 1].t)) - Date.parse(String(refPts[0].t)) : 0
  const intraday = refPts && refPts.length >= 2 ? spanMs / (refPts.length - 1) < 20 * 3600_000 : false
  const clock = (d: Date) => `${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`
  const fmtTime = (t: EquityPoint["t"]) => {
    const d = new Date(t)
    if (Number.isNaN(d.getTime())) return ""
    const md = `${d.getMonth() + 1}/${d.getDate()}`
    return intraday ? `${md} ${clock(d)}` : md
  }
  const hoverTime = xTime && refPts && frac != null ? fmtTime(refPts[Math.round(frac * (refPts.length - 1))].t) : null

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

      {/* x-axis time labels (start / mid / end) when the points carry timestamps */}
      {xTime && refPts && refPts.length >= 2 && (
        <div
          style={{ display: "flex", justifyContent: "space-between", paddingLeft: GUT, marginTop: 2, fontSize: 9, color: "var(--dim)" }}
        >
          <span>{fmtTime(refPts[0].t)}</span>
          <span>{fmtTime(refPts[Math.floor(refPts.length / 2)].t)}</span>
          <span>{fmtTime(refPts[refPts.length - 1].t)}</span>
        </div>
      )}

      {/* legend — idle: static overall return per series; scrubbing: the time + each
          series' value at the cursor (so you never see two numbers for the same line). */}
      <div className="flex gap-3 items-center" style={{ fontSize: 10, marginTop: 6, minHeight: 14 }}>
        {frac != null ? (
          <>
            {hoverTime && <span className="text-mut">{hoverTime}</span>}
            {series.map((s) => {
              const v = valueAt(s.points, frac)
              return (
                <span key={s.label} className="flex items-center gap-1">
                  <span style={{ display: "inline-block", width: 10, height: 2, background: s.color }} />
                  <b style={{ color: s.color }}>{v != null ? labelOf(v) : "—"}</b>
                </span>
              )
            })}
          </>
        ) : (
          series.map((s) => (
            <span key={s.label} className="flex items-center gap-1">
              <span style={{ display: "inline-block", width: 10, height: 2, background: s.color }} />
              {s.label}
            </span>
          ))
        )}
      </div>
    </div>
  )
}
