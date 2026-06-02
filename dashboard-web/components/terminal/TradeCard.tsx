"use client"
import { StatusBadge } from "./StatusBadge"
import { TickerSymbol } from "./TickerSymbol"
import { PriceValue } from "./PriceValue"
import { LivePrice } from "@/components/market/LivePrice"
import { DistanceToBar } from "@/components/market/DistanceToBar"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import type { CandidateSnapshot, ManualPick } from "@/lib/types"

const STATE_BORDER: Record<string, string> = {
  "open/watch": "rgba(255,171,0,0.4)", watching: "rgba(255,171,0,0.4)",
  active: "rgba(0,230,118,0.4)", triggered: "rgba(0,230,118,0.4)",
  pending: "rgba(124,77,255,0.4)",
  target_hit: "rgba(0,230,118,0.4)", target_before_stop: "rgba(0,230,118,0.4)",
  stop_hit: "rgba(255,61,61,0.4)", stop_before_target: "rgba(255,61,61,0.4)", failed_setup: "rgba(255,61,61,0.4)",
}

type CardData = Pick<CandidateSnapshot, "symbol"|"status"|"setup_category"|"entry"|"stop"|"target"|"risk_reward"|"total_score"> | ManualPick

export function TradeCard({ data }: { data: CardData }) {
  const liveQuotes = useLivePrices()
  const sym = data.symbol
  const status = data.status
  const borderColor = STATE_BORDER[status] ?? "var(--border)"
  const isSnap = "total_score" in data
  const entry = isSnap ? (data as CandidateSnapshot).entry : (data as ManualPick).planned_entry
  const stop  = isSnap ? (data as CandidateSnapshot).stop  : (data as ManualPick).planned_stop
  const target = isSnap ? (data as CandidateSnapshot).target : (data as ManualPick).planned_target
  const rr = isSnap ? (data as CandidateSnapshot).risk_reward : null
  const score = isSnap ? (data as CandidateSnapshot).total_score : null
  const quote = liveQuotes[sym]

  return (
    <div style={{
      background: "var(--bg-surface)", border: `1px solid ${borderColor}`,
      borderRadius: 4,
      padding: "10px 14px", marginBottom: 8,
    }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <TickerSymbol symbol={sym} />
          <StatusBadge status={status} />
          {"setup_category" in data && (
            <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>{(data as CandidateSnapshot).setup_category}</span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {quote && <LivePrice quote={quote} />}
          {score !== null && (
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 13, color: "var(--cyan)", fontWeight: 600 }}>
              {score?.toFixed(1)}
            </span>
          )}
        </div>
      </div>
      <div style={{ display: "flex", gap: 16, fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}>
        <span style={{ color: "var(--text-secondary)" }}>Entry <PriceValue value={entry} /></span>
        <span style={{ color: "var(--red)" }}>Stop <PriceValue value={stop} /></span>
        <span style={{ color: "var(--green)" }}>Target <PriceValue value={target} /></span>
        {rr !== null && <span style={{ color: "var(--text-secondary)" }}>R:R {rr?.toFixed(1)}:1</span>}
      </div>
      <DistanceToBar quote={quote} entry={entry} stop={stop} target={target} />
    </div>
  )
}
