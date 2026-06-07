"use client"

import { computeRail } from "@/lib/plan"
import { fmtPrice } from "@/lib/format"

/**
 * Plan-rail — live price marker between stop · entry · target (ported from 09).
 * Shows how close to triggering / how far to target with no math.
 */
export function PlanRail({
  stop,
  entry,
  target,
  current,
  width = 128,
}: {
  stop: number | null
  entry: number | null
  target: number | null
  current: number | null
  width?: number
}) {
  const g = computeRail({ stop, entry, target, current })
  if (!g.ok) {
    return (
      <div style={{ width }} className="text-dim" aria-label="No valid trade plan">
        <div style={{ height: 6, borderRadius: 3, background: "rgba(255,255,255,.06)" }} />
        <div style={{ fontSize: 7.5, marginTop: 5 }}>no plan</div>
      </div>
    )
  }
  const col = g.curAboveEntry ? "var(--pos)" : "var(--warn)"
  return (
    <div
      style={{ width }}
      aria-label={`Plan: stop ${fmtPrice(stop)}, entry ${fmtPrice(entry)}, target ${fmtPrice(target)}`}
    >
      <div style={{ position: "relative", height: 6, background: "rgba(255,255,255,.06)", borderRadius: 3 }}>
        <div
          style={{
            position: "absolute",
            top: 0,
            bottom: 0,
            left: `${g.zoneLeftPct}%`,
            right: `${g.zoneRightPct}%`,
            background: "rgba(70,211,154,.12)",
            borderRadius: 3,
          }}
        />
        <Tick pct={g.stopPct} color="var(--neg)" />
        <Tick pct={g.entryPct} color="var(--cyan)" />
        <Tick pct={g.targetPct} color="var(--pos)" />
        <div
          style={{
            position: "absolute",
            top: "50%",
            left: `${g.curPct}%`,
            width: 9,
            height: 9,
            borderRadius: "50%",
            transform: "translate(-50%,-50%)",
            background: col,
            color: col,
            boxShadow: "0 0 8px currentColor",
            transition: "left var(--d-normal) var(--e-smooth)",
          }}
        />
      </div>
      <div className="flex justify-between" style={{ fontSize: 7.5, color: "var(--dim)", marginTop: 5 }}>
        <span>{fmtPrice(stop)}</span>
        <span style={{ color: "var(--cyan)" }}>{fmtPrice(entry)}</span>
        <span style={{ color: "var(--pos)" }}>{fmtPrice(target)}</span>
      </div>
    </div>
  )
}

function Tick({ pct, color }: { pct: number; color: string }) {
  return (
    <div
      style={{
        position: "absolute",
        top: -3,
        left: `${pct}%`,
        width: 2,
        height: 12,
        borderRadius: 1,
        background: color,
      }}
    />
  )
}
