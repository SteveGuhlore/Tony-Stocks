const COLORS: Record<string, { bg: string; text: string; label: string }> = {
  "open/watch":          { bg: "#1e3a5f", text: "#93c5fd", label: "WATCHING" },
  watching:              { bg: "#1e3a5f", text: "#93c5fd", label: "WATCHING" },
  active:                { bg: "#064e3b", text: "#6ee7b7", label: "ACTIVE"   },
  triggered:             { bg: "#064e3b", text: "#6ee7b7", label: "TRIGGERED"},
  pending:               { bg: "#2e1065", text: "#c4b5fd", label: "PENDING"  },
  target_hit:            { bg: "#052e16", text: "#86efac", label: "TARGET ✓" },
  target_before_stop:    { bg: "#052e16", text: "#86efac", label: "TARGET ✓" },
  stop_hit:              { bg: "#450a0a", text: "#fca5a5", label: "STOP ✗"  },
  stop_before_target:    { bg: "#450a0a", text: "#fca5a5", label: "STOP ✗"  },
  failed_setup:          { bg: "#450a0a", text: "#fca5a5", label: "FAILED"   },
}

export function StatusBadge({ status }: { status: string }) {
  const c = COLORS[status] ?? { bg: "var(--bg-elevated)", text: "var(--text-secondary)", label: status.toUpperCase() }
  return (
    <span style={{
      display: "inline-block", padding: "2px 6px", borderRadius: 2,
      background: c.bg, color: c.text,
      fontSize: 10, fontFamily: "JetBrains Mono, monospace", fontWeight: 600, letterSpacing: "0.06em",
    }}>
      {c.label}
    </span>
  )
}
