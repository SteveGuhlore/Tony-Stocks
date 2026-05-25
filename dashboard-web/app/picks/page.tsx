"use client"

import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { PositionCard } from "@/components/picks/PositionCard"
import type { CandidateSnapshot, ManualPick } from "@/lib/types"

function isSnapshotTriggered(s: CandidateSnapshot) { return s.entry_triggered }
function isManualTriggered(p: ManualPick) { return p.status === "active" || p.status === "triggered" }

function calcPL(entry: number | null, price: number | undefined): number | null {
  if (!entry || !price) return null
  return ((price - entry) / entry) * 100
}

function avgOf(vals: (number | null)[]): number | null {
  const nums = vals.filter((v): v is number => v !== null)
  return nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null
}

function KPIBar({ inTrade, watching, avgPct }: { inTrade: number; watching: number; avgPct: number | null }) {
  const lbl: React.CSSProperties = {
    fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em",
    color: "var(--text-secondary)", marginBottom: 4,
  }
  const val: React.CSSProperties = {
    fontSize: 20, fontFamily: "JetBrains Mono, monospace",
    fontWeight: 700, color: "var(--text-primary)", lineHeight: 1,
  }
  const positive = avgPct !== null && avgPct >= 0
  return (
    <div style={{
      display: "flex", gap: 32, padding: "14px 16px",
      background: "var(--bg-surface)", border: "1px solid var(--border)",
      borderRadius: 6, marginBottom: 20,
    }}>
      <div><div style={lbl}>In Trade</div><div style={val}>{inTrade}</div></div>
      <div><div style={lbl}>Watching</div><div style={val}>{watching}</div></div>
      {avgPct !== null && (
        <div>
          <div style={lbl}>Avg P&amp;L</div>
          <div style={{ ...val, color: positive ? "var(--green)" : "var(--red)" }}>
            {positive ? "+" : ""}{avgPct.toFixed(2)}%
          </div>
        </div>
      )}
    </div>
  )
}

function SectionHeader({ label, count }: { label: string; count: number }) {
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 8,
      fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em",
      color: "var(--text-secondary)", marginBottom: 10, marginTop: 4,
    }}>
      {label}
      <span style={{
        background: "var(--bg-elevated)", borderRadius: 10,
        padding: "1px 7px", fontSize: 10,
      }}>
        {count}
      </span>
    </div>
  )
}

function EmptyState() {
  return (
    <div style={{ textAlign: "center", padding: "60px 16px", color: "var(--text-secondary)" }}>
      <div style={{ fontSize: 36, marginBottom: 12 }}>💼</div>
      <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 6, color: "var(--text-primary)" }}>
        No picks yet
      </div>
      <div style={{ fontSize: 11 }}>
        Add picks from the Watchlist or wait for the bot to generate scan candidates
      </div>
    </div>
  )
}

export default function PicksPage() {
  const { data: tracking } = useQuery({ queryKey: ["tracking"], queryFn: api.tracking, refetchInterval: 30_000 })
  const { data: picks }    = useQuery({ queryKey: ["picks"],    queryFn: api.picks,    refetchInterval: 60_000 })
  const liveQuotes = useLivePrices()

  const allSnaps       = [...(tracking?.active ?? []), ...(tracking?.watching ?? [])]
  const triggeredSnaps = allSnaps.filter(isSnapshotTriggered)
  const watchingSnaps  = allSnaps.filter(s => !isSnapshotTriggered(s))

  const allManual       = picks?.picks ?? []
  const triggeredManual = allManual.filter(isManualTriggered)
  const watchingManual  = allManual.filter(p => !isManualTriggered(p))

  const plValues = triggeredSnaps.map(s => calcPL(s.entry, liveQuotes[s.symbol]?.price))
  const avgPL    = avgOf(plValues)

  const totalInTrade  = triggeredSnaps.length + triggeredManual.length
  const totalWatching = watchingSnaps.length  + watchingManual.length
  const isEmpty       = totalInTrade === 0 && totalWatching === 0

  const sortedTriggered = triggeredSnaps.slice().sort((a, b) => {
    const pa = calcPL(a.entry, liveQuotes[a.symbol]?.price) ?? -999
    const pb = calcPL(b.entry, liveQuotes[b.symbol]?.price) ?? -999
    return pb - pa
  })

  const sortedWatching = watchingSnaps.slice().sort((a, b) =>
    (b.total_score ?? 0) - (a.total_score ?? 0)
  )

  return (
    <div>
      <h1 style={{
        fontSize: 13, fontWeight: 600, marginBottom: 16,
        color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em",
      }}>
        💼 Picks
      </h1>

      {isEmpty ? <EmptyState /> : (
        <>
          <KPIBar inTrade={totalInTrade} watching={totalWatching} avgPct={avgPL} />

          {sortedTriggered.length > 0 && (
            <>
              <SectionHeader label="In Trade" count={sortedTriggered.length} />
              {sortedTriggered.map(s => (
                <PositionCard
                  key={s.id}
                  symbol={s.symbol}
                  status={s.status}
                  setupCategory={s.setup_category}
                  entry={s.entry}
                  stop={s.stop}
                  target={s.target}
                  rr={s.risk_reward}
                  score={s.total_score}
                  triggeredAt={s.entry_triggered_at}
                  watchingSince={s.snapshot_time}
                  triggered={true}
                  thesis={s.tony_hypothesis}
                  thesisLabel={s.tony_priority_label}
                  thesisAction={s.tony_recommended_action}
                  quote={liveQuotes[s.symbol]}
                />
              ))}
            </>
          )}

          {triggeredManual.length > 0 && (
            <>
              <SectionHeader label="Manual — In Trade" count={triggeredManual.length} />
              {triggeredManual.map(p => (
                <PositionCard
                  key={`m-${p.id}`}
                  symbol={p.symbol}
                  status={p.status}
                  setupCategory={null}
                  entry={p.planned_entry}
                  stop={p.planned_stop}
                  target={p.planned_target}
                  rr={null}
                  score={null}
                  triggeredAt={p.picked_at}
                  watchingSince={p.picked_at}
                  triggered={true}
                  thesis={p.notes}
                  thesisLabel={null}
                  thesisAction={null}
                  quote={liveQuotes[p.symbol]}
                />
              ))}
            </>
          )}

          {sortedWatching.length > 0 && (
            <>
              <SectionHeader label="Watching for Entry" count={sortedWatching.length} />
              {sortedWatching.map(s => (
                <PositionCard
                  key={s.id}
                  symbol={s.symbol}
                  status={s.status}
                  setupCategory={s.setup_category}
                  entry={s.entry}
                  stop={s.stop}
                  target={s.target}
                  rr={s.risk_reward}
                  score={s.total_score}
                  triggeredAt={s.entry_triggered_at}
                  watchingSince={s.snapshot_time}
                  triggered={false}
                  thesis={s.tony_hypothesis}
                  thesisLabel={s.tony_priority_label}
                  thesisAction={s.tony_recommended_action}
                  quote={liveQuotes[s.symbol]}
                />
              ))}
            </>
          )}

          {watchingManual.length > 0 && (
            <>
              <SectionHeader label="Manual — Watching" count={watchingManual.length} />
              {watchingManual.map(p => (
                <PositionCard
                  key={`mw-${p.id}`}
                  symbol={p.symbol}
                  status={p.status}
                  setupCategory={null}
                  entry={p.planned_entry}
                  stop={p.planned_stop}
                  target={p.planned_target}
                  rr={null}
                  score={null}
                  triggeredAt={null}
                  watchingSince={p.picked_at}
                  triggered={false}
                  thesis={p.notes}
                  thesisLabel={null}
                  thesisAction={null}
                  quote={liveQuotes[p.symbol]}
                />
              ))}
            </>
          )}
        </>
      )}
    </div>
  )
}
