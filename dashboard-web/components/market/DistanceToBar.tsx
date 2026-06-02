"use client"
import type { LiveQuote } from "@/lib/types"

interface Props {
  quote: LiveQuote | undefined
  entry: number | null
  stop: number | null
  target?: number | null
}

function pct(a: number, b: number): string {
  return `${((a - b) / b * 100).toFixed(2)}%`
}

export function DistanceToBar({ quote, entry, stop, target }: Props) {
  if (!quote || !entry || !stop) return null
  const price = quote.price
  const distToEntry = pct(price, entry)
  const distToStop = pct(price, stop)
  const distToTarget = target ? pct(price, target) : null
  const nearEntry = Math.abs(price - entry) / entry < 0.005

  return (
    <div
      className="flex gap-3 text-xs font-mono mt-1"
      style={{
        color: "var(--text-secondary)",
        fontVariantNumeric: "tabular-nums",
      }}
    >
      <span
        className={nearEntry ? "font-semibold" : ""}
        style={nearEntry ? { color: "var(--amber)" } : undefined}
      >
        Entry {distToEntry}
      </span>
      <span style={{ color: "rgba(255,61,61,0.7)" }}>Stop {distToStop}</span>
      {distToTarget && (
        <span style={{ color: "rgba(0,230,118,0.7)" }}>Target {distToTarget}</span>
      )}
    </div>
  )
}
