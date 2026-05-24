"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { KPIBar } from "@/components/terminal/KPIBar"
import { TradeCard } from "@/components/terminal/TradeCard"
import { ActivityFeed } from "@/components/terminal/ActivityFeed"

export default function TodayPage() {
  const { data, isLoading } = useQuery({ queryKey: ["today"], queryFn: api.today, refetchInterval: 30_000 })
  if (isLoading) return <div style={{ color: "var(--text-secondary)" }}>Loading...</div>
  if (!data) return null
  const wr = data.kpis.win_rate
  return (
    <div>
      <h1 style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        ⚡ Today
      </h1>
      <KPIBar items={[
        { label: "Watching",   value: data.kpis.watching },
        { label: "Triggered",  value: data.kpis.triggered },
        { label: "Win Rate",   value: wr !== null ? `${(wr * 100).toFixed(0)}%` : "—" },
        { label: "Watch",      value: data.watch.status ?? "—" },
        { label: "Last Scan",  value: data.watch.last_scan_age_seconds !== null
            ? `${Math.round(data.watch.last_scan_age_seconds / 60)}m ago` : "—" },
      ]} />
      <div style={{ display: "grid", gridTemplateColumns: "38% 1fr", gap: 16 }}>
        <div>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-secondary)", marginBottom: 8 }}>Recent Activity</div>
          <ActivityFeed events={data.recent_events} />
        </div>
        <div>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-secondary)", marginBottom: 8 }}>Live Setups</div>
          {data.active_snapshots.length ? data.active_snapshots.map(s => <TradeCard key={s.id} data={s} />) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>No active setups</p>
          )}
        </div>
      </div>
    </div>
  )
}
