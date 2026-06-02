"use client"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { ScanTable } from "@/components/terminal/ScanTable"
import { TonyHypothesisCard } from "@/components/terminal/TonyHypothesisCard"
import { KPIBar } from "@/components/terminal/KPIBar"

export default function ScanPage() {
  const [minScore, setMinScore] = useState(0)
  const { data: scan } = useQuery({
    queryKey: ["scan", minScore],
    queryFn: () => api.scanLatest({ min_score: minScore }),
    refetchInterval: 60_000,
  })
  const { data: overview } = useQuery({ queryKey: ["scanOverview"], queryFn: api.scanOverview })
  const tonySnaps = (scan?.results ?? []).filter(r => r.score >= 75).slice(0, 10)

  return (
    <div>
      <h1 style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        🔍 Scan
      </h1>
      {overview && (
        <KPIBar items={[
          { label: "Scanned",    value: overview.scanned },
          { label: "Candidates", value: overview.candidates },
          { label: "Manual Picks", value: overview.picks },
          { label: "Last Scan",  value: overview.last_scan_at?.slice(0, 10) ?? "no scan yet" },
        ]} />
      )}
      <div style={{ marginBottom: 12, display: "flex", alignItems: "center", gap: 12 }}>
        <label style={{ fontSize: 11, color: "var(--text-secondary)" }}>Min Score</label>
        <input type="range" min={0} max={90} step={5} value={minScore}
          onChange={e => setMinScore(Number(e.target.value))}
          style={{ accentColor: "var(--cyan)" }} />
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "var(--cyan)" }}>{minScore}</span>
      </div>
      <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>
        Candidates ({scan?.total ?? 0})
      </div>
      <ScanTable results={scan?.results ?? []} />
    </div>
  )
}

