"use client"
import { useState, useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { BoardTable } from "@/components/board/BoardTable"
import { UniverseTable } from "@/components/board/UniverseTable"

type View = "watches" | "universe"

export default function BoardPage() {
  const [view, setView] = useState<View>("watches")

  const tracking = useQuery({ queryKey: ["tracking"], queryFn: api.tracking, refetchInterval: 30_000 })
  const universe = useQuery({ queryKey: ["scanLatest"], queryFn: () => api.scanLatest(), enabled: view === "universe" })

  const watches = useMemo(() => {
    const t = tracking.data
    if (!t) return []
    return [...t.active, ...t.watching].sort((a, b) => (b.total_score ?? 0) - (a.total_score ?? 0))
  }, [tracking.data])

  const universeRows = universe.data?.results ?? []
  const loading = view === "watches" ? tracking.isLoading : universe.isLoading

  return (
    <div>
      {/* sub-header: toggle */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12, flexWrap: "wrap" }}>
        <div style={{ display: "inline-flex", background: "var(--bg-surface)", border: "1px solid var(--border)", borderRadius: 7, overflow: "hidden" }}>
          {(["watches", "universe"] as const).map((v) => {
            const active = view === v
            const count = v === "watches" ? watches.length : universe.data?.total ?? null
            return (
              <button
                key={v}
                onClick={() => setView(v)}
                aria-pressed={active}
                style={{
                  padding: "5px 14px", fontSize: 12, fontWeight: active ? 600 : 400, cursor: "pointer",
                  border: "none", textTransform: "capitalize",
                  background: active ? "var(--bg-elevated)" : "transparent",
                  color: active ? "var(--text-primary)" : "var(--text-secondary)",
                }}
              >
                {v}{count != null ? ` · ${count}` : ""}
              </button>
            )
          })}
        </div>
        <span className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>
          {view === "watches" ? "sorted by Tony score" : "full scanned universe"}
        </span>
      </div>

      {loading
        ? <p style={{ color: "var(--text-tertiary)", fontSize: 12, padding: 16 }}>Loading…</p>
        : view === "watches"
          ? <BoardTable snapshots={watches} />
          : <UniverseTable rows={universeRows} />}
    </div>
  )
}
