export function KPIBar({ items }: { items: { label: string; value: string | number | null }[] }) {
  return (
    <div style={{ display: "flex", gap: 1, marginBottom: 16 }}>
      {items.map(({ label, value }) => (
        <div key={label} style={{
          flex: 1, background: "var(--bg-surface)", border: "1px solid var(--border)",
          padding: "10px 14px",
        }}>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>{label}</div>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 22, fontWeight: 600, marginTop: 4, color: "var(--text-primary)" }}>
            {value ?? "—"}
          </div>
        </div>
      ))}
    </div>
  )
}
