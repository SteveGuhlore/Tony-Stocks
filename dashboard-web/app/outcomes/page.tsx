"use client"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { KPIBar } from "@/components/terminal/KPIBar"
import { TradeCard } from "@/components/terminal/TradeCard"
import { FilterChips } from "@/components/terminal/FilterChips"

const FILTERS = ["all", "open", "targets", "stops"]

export default function OutcomesPage() {
  const [filter, setFilter] = useState("all")
  const { data, isLoading } = useQuery({
    queryKey: ["outcomes", filter], queryFn: () => api.outcomes(filter), refetchInterval: 60_000
  })
  if (isLoading) return <div style={{ color: "var(--text-secondary)" }}>Loading...</div>
  if (!data) return null
  const { kpis, snapshots } = data
  const wr = kpis.win_rate
  return (
    <div>
      <h1 style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        📊 Outcomes
      </h1>
      <KPIBar items={[
        { label: "Active",   value: kpis.active },
        { label: "Closed",   value: kpis.closed },
        { label: "Targets",  value: kpis.target_hits },
        { label: "Stops",    value: kpis.stop_hits },
        { label: "Win Rate", value: wr !== null ? `${(wr * 100).toFixed(0)}%` : "no data" },
      ]} />
      <FilterChips options={FILTERS} value={filter} onChange={setFilter} />
      {snapshots.length ? snapshots.map(s => <TradeCard key={s.id} data={s} />) : (
        <p style={{ color: "var(--text-secondary)" }}>No outcomes match this filter</p>
      )}
    </div>
  )
}
