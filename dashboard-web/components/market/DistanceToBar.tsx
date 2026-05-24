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
    <div className="flex gap-3 text-xs font-mono tabular-nums text-zinc-400 mt-1">
      <span className={nearEntry ? "text-amber-400 font-semibold" : ""}>
        Entry {distToEntry}
      </span>
      <span className="text-red-400/70">Stop {distToStop}</span>
      {distToTarget && <span className="text-emerald-400/70">Target {distToTarget}</span>}
    </div>
  )
}
