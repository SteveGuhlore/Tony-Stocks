"use client"

import type { ReactNode } from "react"

export function ViewHeader({ title, sub }: { title: string; sub?: string }) {
  return (
    <div className="flex flex-wrap items-center gap-[10px]" style={{ marginBottom: 12 }}>
      <h2 style={{ fontSize: 18 }}>{title}</h2>
      {sub && (
        <span className="text-mut" style={{ fontSize: 11 }}>
          {sub}
        </span>
      )}
    </div>
  )
}

export function Kpis({ items }: { items: { label: string; value: ReactNode; tone?: "pos" | "neg" }[] }) {
  return (
    <div className="grid gap-[10px]" style={{ gridTemplateColumns: "repeat(auto-fit,minmax(120px,1fr))", marginBottom: 14 }}>
      {items.map((k) => (
        <div key={k.label} className="kt-panel" style={{ padding: "11px 13px" }}>
          <div className="text-dim" style={{ fontSize: 9, textTransform: "uppercase", letterSpacing: ".08em" }}>
            {k.label}
          </div>
          <div
            className="font-display"
            style={{ fontSize: 20, marginTop: 3, color: k.tone === "pos" ? "var(--pos)" : k.tone === "neg" ? "var(--neg)" : "var(--ink)" }}
          >
            {k.value}
          </div>
        </div>
      ))}
    </div>
  )
}

export function Panel({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <div className="kt-panel" style={{ padding: "13px 15px", marginBottom: 12 }}>
      {title && (
        <h3 style={{ fontSize: 15, marginBottom: 10 }}>{title}</h3>
      )}
      {children}
    </div>
  )
}

export function ResearchFooter() {
  return (
    <div className="text-dim" style={{ fontSize: 11, marginTop: 6 }}>
      ⚑ Research simulation only — not investment advice. Small sample; not evidence of edge.
    </div>
  )
}

export function Awaiting({ what }: { what: string }) {
  return (
    <div className="text-dim" style={{ fontSize: 11, padding: "8px 0" }}>
      Awaiting {what}.
    </div>
  )
}
