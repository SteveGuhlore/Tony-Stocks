"use client"

export type RailView = "cockpit" | "record" | "paper" | "xray" | "system"

const ITEMS: { id: RailView; icon: string; label: string }[] = [
  { id: "cockpit", icon: "▦", label: "Cockpit" },
  { id: "record", icon: "✦", label: "Track Record" },
  { id: "paper", icon: "▤", label: "Paper Book" },
  { id: "xray", icon: "◎", label: "Scanner X-ray" },
  { id: "system", icon: "⚙", label: "System" },
]

/** Slim left rail (desktop) → bottom bar (mobile, via .rail-reflow). */
export function Rail({ view, onView }: { view: RailView; onView: (v: RailView) => void }) {
  return (
    <nav
      aria-label="Primary views"
      className="kt-rail"
      style={{ borderRight: "1px solid var(--line)", background: "var(--panel)" }}
    >
      {ITEMS.map((it) => {
        const on = it.id === view
        return (
          <button
            key={it.id}
            onClick={() => onView(it.id)}
            aria-label={it.label}
            aria-current={on ? "page" : undefined}
            title={it.label}
            style={{
              width: 36,
              height: 36,
              borderRadius: 8,
              display: "grid",
              placeItems: "center",
              fontSize: 15,
              cursor: "pointer",
              border: "none",
              background: on ? "rgba(55,224,255,.14)" : "transparent",
              color: on ? "var(--cyan)" : "var(--dim)",
            }}
          >
            {it.icon}
          </button>
        )
      })}
    </nav>
  )
}
