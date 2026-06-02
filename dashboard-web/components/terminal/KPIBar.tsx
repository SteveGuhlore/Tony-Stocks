export function KPIBar({ items }: { items: { label: string; value: string | number | null }[] }) {
  return (
    <div style={{
      display: "flex", flexWrap: "wrap", alignItems: "baseline",
      columnGap: 24, rowGap: 8, marginBottom: 14,
    }}>
      {items.map(({ label, value }) => (
        <span key={label} style={{ display: "inline-flex", alignItems: "baseline", gap: 6 }}>
          <span style={{
            fontSize: 10, color: "var(--text-tertiary, var(--text-secondary))",
            textTransform: "uppercase", letterSpacing: "0.08em",
          }}>
            {label}
          </span>
          <span style={{
            fontFamily: "JetBrains Mono, monospace", fontSize: 13,
            color: "var(--text-primary)",
          }}>
            {value ?? "·"}
          </span>
        </span>
      ))}
    </div>
  )
}
