export function PriceValue({ value, prefix = "$", decimals = 2 }: { value: number | null; prefix?: string; decimals?: number }) {
  if (value === null || value === undefined) return <span style={{ color: "var(--text-secondary)" }}>·</span>
  return (
    <span style={{ fontFamily: "JetBrains Mono, monospace" }}>
      {prefix}{value.toFixed(decimals)}
    </span>
  )
}

export function PctValue({ value, decimals = 1 }: { value: number | null; decimals?: number }) {
  if (value === null || value === undefined) return <span style={{ color: "var(--text-secondary)" }}>·</span>
  const color = value > 0 ? "var(--green)" : value < 0 ? "var(--red)" : "var(--text-secondary)"
  return (
    <span style={{ fontFamily: "JetBrains Mono, monospace", color }}>
      {value > 0 ? "+" : ""}{(value * 100).toFixed(decimals)}%
    </span>
  )
}
