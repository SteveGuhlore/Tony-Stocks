"use client"
import { railPositionPct, type PlanLevels } from "@/lib/plan"
import { verdictDisplay, type Tone } from "@/lib/signal"
import { formatPrice } from "@/lib/format"

export const TONE_VAR: Record<Tone, string> = {
  green: "var(--green)",
  red: "var(--red)",
  amber: "var(--amber)",
  azure: "var(--accent)",
  brass: "var(--brass)",
  muted: "var(--text-tertiary)",
}

/** Horizontal plan ladder: stop → entry → target with a live-price marker. */
export function PlanRail({
  stop, entry, target, live, markerTone = "azure",
}: {
  stop: number | null
  entry: number | null
  target: number | null
  live: number | null | undefined
  markerTone?: Tone
}) {
  const levels: PlanLevels = { stop, entry, target }
  const entryPos = railPositionPct(entry, levels)
  const livePos = railPositionPct(live ?? null, levels)
  const planned = stop != null && target != null
  const marker = TONE_VAR[markerTone]

  return (
    <div style={{ minWidth: 120 }}>
      <div
        style={{
          position: "relative",
          height: 5,
          borderRadius: 3,
          opacity: planned ? 1 : 0.45,
          background:
            "linear-gradient(90deg, rgba(255,99,99,0.22) 0%, rgba(255,99,99,0.22) 18%, var(--bg-elevated) 18%, var(--bg-elevated) 82%, rgba(54,211,153,0.22) 82%, rgba(54,211,153,0.22) 100%)",
        }}
      >
        {entryPos != null && (
          <span style={{ position: "absolute", left: `${entryPos}%`, top: -3, width: 2, height: 11, background: "var(--text-secondary)" }} />
        )}
        {livePos != null && (
          <span
            style={{
              position: "absolute", left: `${livePos}%`, top: -4,
              width: 9, height: 13, borderRadius: 3, background: marker,
              transform: "translateX(-4px)", boxShadow: `0 0 7px ${marker}`,
            }}
          />
        )}
      </div>
      <div className="mono" style={{ display: "flex", justifyContent: "space-between", fontSize: 8.5, color: "var(--text-tertiary)", marginTop: 4 }}>
        <span style={{ color: "var(--red)" }}>{formatPrice(stop)}</span>
        <span style={{ color: "var(--text-secondary)" }}>{formatPrice(entry)}</span>
        <span style={{ color: "var(--green)" }}>{formatPrice(target)}</span>
      </div>
    </div>
  )
}

/** Command-Center verdict chip; degrades to "⋯ awaiting" when no verdict exists yet. */
export function VerdictChip({ verdict }: { verdict: string | null | undefined }) {
  const { label, tone } = verdictDisplay(verdict)
  return <span className="mono" style={{ fontSize: 11, color: TONE_VAR[tone] }}>{label}</span>
}

/** Tony score + Tony Stocks score side by side. T.STK shows "⋯" until the second layer exists. */
export function ScorePair({ tony, tonyStocks }: { tony: number | null; tonyStocks?: number | null }) {
  return (
    <span className="mono" style={{ fontSize: 12 }}>
      <span style={{ color: "var(--accent)", fontWeight: 700 }}>{tony != null ? Math.round(tony) : "—"}</span>
      <span style={{ color: "var(--text-tertiary)" }}> · </span>
      <span style={{ color: tonyStocks != null ? "var(--green)" : "var(--text-tertiary)", fontWeight: tonyStocks != null ? 700 : 400 }}>
        {tonyStocks != null ? Math.round(tonyStocks) : "⋯"}
      </span>
    </span>
  )
}

export function ToneText({ tone, children, mono = true, size = 11 }: { tone: Tone; children: React.ReactNode; mono?: boolean; size?: number }) {
  return <span className={mono ? "mono" : undefined} style={{ fontSize: size, color: TONE_VAR[tone] }}>{children}</span>
}
