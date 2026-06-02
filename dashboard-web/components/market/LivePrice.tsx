"use client"
import type { LiveQuote } from "@/lib/types"

interface Props {
  quote: LiveQuote | undefined
  className?: string
}

export function LivePrice({ quote, className = "" }: Props) {
  if (!quote)
    return (
      <span
        className={`font-mono ${className}`}
        style={{ color: "var(--text-tertiary)" }}
      >
        ·
      </span>
    )

  const pct = quote.change_pct * 100
  const sign = pct >= 0 ? "+" : ""
  const color = pct >= 0 ? "var(--green)" : "var(--red)"

  return (
    <span
      className={`font-mono ${className}`}
      style={{ fontVariantNumeric: "tabular-nums" }}
    >
      <span style={{ color: "var(--text-primary)" }}>${quote.price.toFixed(2)}</span>
      {" "}
      <span className="text-xs" style={{ color }}>
        {sign}{pct.toFixed(2)}%
      </span>
    </span>
  )
}
