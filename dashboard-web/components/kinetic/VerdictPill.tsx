"use client"

import { normalizeVerdict } from "@/lib/verdict"

/** Verdict pill (bot ↔ 2nd pass). Unknown verdicts degrade to "awaiting". */
export function VerdictPill({ verdict, score }: { verdict: string | null | undefined; score?: number | null }) {
  const v = normalizeVerdict(verdict)
  return (
    <span className="inline-flex items-center gap-[6px]">
      <span className={`kt-pill ${v.className}`}>{v.label}</span>
      {score != null && (
        <span className="font-display font-bold text-amber" style={{ fontSize: 12 }}>
          {Math.round(score)}
        </span>
      )}
    </span>
  )
}
