"use client"
import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { TradeCard } from "@/components/terminal/TradeCard"
import { FilterChips } from "@/components/terminal/FilterChips"
import type { CandidateSnapshot } from "@/lib/types"

const FILTERS = ["ALL", "ACTIVE", "WATCHING", "PENDING", "STALE"]

function matchFilter(s: CandidateSnapshot, f: string) {
  if (f === "ALL") return true
  if (f === "ACTIVE") return ["active","triggered","open/watch"].includes(s.status)
  if (f === "WATCHING") return ["watching"].includes(s.status)
  if (f === "PENDING") return s.status === "pending"
  if (f === "STALE") return s.outcome_label === null && !["active","watching","pending","open/watch","triggered"].includes(s.status)
  return true
}

export default function WatchlistPage() {
  const [filter, setFilter] = useState("ALL")
  const { data: tracking } = useQuery({ queryKey: ["tracking"], queryFn: api.tracking, refetchInterval: 30_000 })
  const { data: picks } = useQuery({ queryKey: ["picks"], queryFn: api.picks, refetchInterval: 60_000 })
  const snapshots = [...(tracking?.active ?? []), ...(tracking?.watching ?? [])]
  const filtered = snapshots.filter(s => matchFilter(s, filter))
  return (
    <div>
      <h1 style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        👁 Watchlist
      </h1>
      <FilterChips options={FILTERS} value={filter} onChange={setFilter} />
      {filtered.length ? filtered.map(s => <TradeCard key={s.id} data={s} />) : (
        <p style={{ color: "var(--text-secondary)" }}>No positions match this filter</p>
      )}
      {picks?.picks.length ? (
        <>
          <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", margin: "16px 0 8px" }}>Manual Picks</div>
          {picks.picks.map(p => <TradeCard key={p.id} data={p} />)}
        </>
      ) : null}
    </div>
  )
}
