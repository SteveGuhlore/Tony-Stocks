"use client"

interface Props {
  entry: number
  currentPrice: number
}

export function PLBadge({ entry, currentPrice }: Props) {
  const pct      = ((currentPrice - entry) / entry) * 100
  const positive = pct >= 0
  const color    = positive ? "var(--green)" : "var(--red)"
  const bg       = positive ? "rgba(0,230,118,0.08)" : "rgba(255,61,61,0.08)"
  const border   = positive ? "rgba(0,230,118,0.2)"  : "rgba(255,61,61,0.2)"
  const sign     = positive ? "+" : ""
  const arrow    = positive ? "▲" : "▼"

  return (
    <div style={{
      background: bg,
      border: `1px solid ${border}`,
      borderRadius: 6,
      padding: "6px 14px",
      textAlign: "center",
      minWidth: 100,
    }}>
      <div style={{
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 22,
        fontWeight: 700,
        color,
        lineHeight: 1.1,
      }}>
        {sign}{pct.toFixed(2)}%
      </div>
      <div style={{ fontSize: 10, color, opacity: 0.8, marginTop: 2 }}>
        {arrow} unrealized
      </div>
    </div>
  )
}
