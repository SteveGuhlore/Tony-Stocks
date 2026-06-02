"use client"
export function FilterChips({ options, value, onChange }: {
  options: string[]; value: string; onChange: (v: string) => void
}) {
  return (
    <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
      {options.map(opt => (
        <button key={opt} className="filter-chip" onClick={() => onChange(opt)} style={{
          padding: "4px 12px", borderRadius: 2, border: "1px solid",
          borderColor: value === opt ? "var(--cyan)" : "var(--border)",
          background: value === opt ? "rgba(0,229,255,0.08)" : "var(--bg-surface)",
          color: value === opt ? "var(--cyan)" : "var(--text-secondary)",
          fontSize: 11, fontFamily: "JetBrains Mono, monospace",
          cursor: "pointer", textTransform: "uppercase", letterSpacing: "0.06em",
          transition: "all 0.12s",
        }}>
          {opt}
        </button>
      ))}
    </div>
  )
}
