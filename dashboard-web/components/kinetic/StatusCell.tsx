"use client"

import type { CockpitRow } from "@/lib/types"
import { statusBadge } from "@/lib/rows"

/** Status cell — NEAR pulse badge / TRIGGERED / watching (ported from 09). */
export function StatusCell({ row }: { row: CockpitRow }) {
  const s = statusBadge(row)
  if (s.kind === "near") return <span className="kt-near">{s.label}</span>
  if (s.kind === "triggered")
    return (
      <span className="font-bold text-pos" style={{ fontSize: 10 }}>
        {s.label}
      </span>
    )
  return (
    <span className="text-dim" style={{ fontSize: 10 }}>
      {s.label}
    </span>
  )
}
