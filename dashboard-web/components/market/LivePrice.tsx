"use client"
import type { LiveQuote } from "@/lib/types"

interface Props {
  quote: LiveQuote | undefined
  className?: string
}

export function LivePrice({ quote, className = "" }: Props) {
  if (!quote) return <span className={`font-mono text-zinc-500 ${className}`}>—</span>

  const pct = quote.change_pct * 100
  const sign = pct >= 0 ? "+" : ""
  const color = pct >= 0 ? "text-emerald-400" : "text-red-400"

  return (
    <span className={`font-mono tabular-nums ${className}`}>
      <span className="text-zinc-100">${quote.price.toFixed(2)}</span>
      {" "}
      <span className={`text-xs ${color}`}>
        {sign}{pct.toFixed(2)}%
      </span>
    </span>
  )
}
