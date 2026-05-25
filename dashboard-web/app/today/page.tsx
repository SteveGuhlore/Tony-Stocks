"use client"

import Link from "next/link"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { KPIBar } from "@/components/terminal/KPIBar"
import { ActivityFeed } from "@/components/terminal/ActivityFeed"
import { TickerSymbol } from "@/components/terminal/TickerSymbol"
import { StatusBadge } from "@/components/terminal/StatusBadge"
import type { CandidateSnapshot, LiveQuote } from "@/lib/types"

function PLText({ entry, price }: { entry: number | null; price: number | undefined }) {
  if (!entry || !price) {
    return <span style={{ color: "var(--text-secondary)", fontFamily: "JetBrains Mono, monospace" }}>—</span>
  }
  const pct = ((price - entry) / entry) * 100
  const positive = pct >= 0
  return (
    <span style={{
      fontFamily: "JetBrains Mono, monospace", fontSize: 12, fontWeight: 700,
      color: positive ? "var(--green)" : "var(--red)",
    }}>
      {positive ? "+" : ""}{pct.toFixed(2)}% {positive ? "▲" : "▼"}
    </span>
  )
}

function ActivePositionRow({ snapshot, quote }: { snapshot: CandidateSnapshot; quote: LiveQuote | undefined }) {
  const price = quote?.price
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "6px 0", borderBottom: "1px solid var(--border)", minHeight: 32,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <TickerSymbol symbol={snapshot.symbol} />
        <StatusBadge status={snapshot.status} />
        {snapshot.entry !== null && (
          <span style={{
            fontSize: 11, fontFamily: "JetBrains Mono, monospace",
            color: "var(--text-secondary)",
          }}>
            ${snapshot.entry.toFixed(2)}
            {price !== undefined && <> → ${price.toFixed(2)}</>}
          </span>
        )}
      </div>
      <PLText entry={snapshot.entry} price={price} />
    </div>
  )
}

export default function TodayPage() {
  const { data, isLoading } = useQuery({ queryKey: ["today"], queryFn: api.today, refetchInterval: 30_000 })
  const liveQuotes = useLivePrices()

  if (isLoading) return <div style={{ color: "var(--text-secondary)" }}>Loading...</div>
  if (!data) return null

  const wr = data.kpis.win_rate
  const triggered = data.active_snapshots.filter(s => s.entry_triggered)

  return (
    <div>
      <h1 style={{
        fontSize: 13, fontWeight: 600, marginBottom: 16,
        color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em",
      }}>
        ⚡ Today
      </h1>

      <KPIBar items={[
        { label: "Watching",  value: data.kpis.watching },
        { label: "Triggered", value: data.kpis.triggered },
        { label: "Win Rate",  value: wr !== null ? `${(wr * 100).toFixed(0)}%` : "—" },
        { label: "Watch",     value: data.watch.status ?? "—" },
        { label: "Last Scan", value: data.watch.last_scan_age_seconds !== null
            ? `${Math.round(data.watch.last_scan_age_seconds / 60)}m ago` : "—" },
      ]} />

      <div style={{ display: "grid", gridTemplateColumns: "38% 1fr", gap: 16 }}>
        <div>
          <div style={{
            fontSize: 10, textTransform: "uppercase",
            letterSpacing: "0.08em", color: "var(--text-secondary)", marginBottom: 8,
          }}>
            Recent Activity
          </div>
          <ActivityFeed events={data.recent_events} />
        </div>

        <div>
          <div style={{
            display: "flex", alignItems: "center",
            justifyContent: "space-between", marginBottom: 8,
          }}>
            <div style={{
              fontSize: 10, textTransform: "uppercase",
              letterSpacing: "0.08em", color: "var(--text-secondary)",
            }}>
              Active Positions
            </div>
            <Link href="/picks" style={{ fontSize: 10, color: "var(--cyan)", textDecoration: "none" }}>
              View all in Picks →
            </Link>
          </div>

          {triggered.length > 0 ? triggered.map(s => (
            <ActivePositionRow key={s.id} snapshot={s} quote={liveQuotes[s.symbol]} />
          )) : (
            <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>No active positions</p>
          )}
        </div>
      </div>
    </div>
  )
}
