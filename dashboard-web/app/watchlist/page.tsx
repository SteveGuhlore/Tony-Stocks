"use client"

import { useState } from "react"
import { useQuery, useQueryClient, useMutation } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { FilterChips } from "@/components/terminal/FilterChips"
import { TickerSymbol } from "@/components/terminal/TickerSymbol"
import { StatusBadge } from "@/components/terminal/StatusBadge"
import { useDrawer } from "@/components/overlays/DrawerContext"
import type { CandidateSnapshot, ManualPick, LiveQuote } from "@/lib/types"

const FILTERS = ["ALL", "ACTIVE", "WATCHING", "PENDING"]

function matchFilter(s: CandidateSnapshot, f: string) {
  if (f === "ALL")      return true
  if (f === "ACTIVE")   return ["active", "triggered", "open/watch"].includes(s.status)
  if (f === "WATCHING") return s.status === "watching"
  if (f === "PENDING")  return s.status === "pending"
  return true
}

function DistCell({ entry, quote, triggered }: {
  entry: number | null
  quote: LiveQuote | undefined
  triggered: boolean
}) {
  const price = quote?.price
  if (!entry || !price) return <span style={{ color: "var(--text-secondary)" }}>—</span>
  const pct = ((price - entry) / entry) * 100
  const positive = pct >= 0
  if (triggered) {
    return (
      <span style={{
        fontFamily: "JetBrains Mono, monospace", fontWeight: 600,
        color: positive ? "var(--green)" : "var(--red)",
      }}>
        {positive ? "+" : ""}{pct.toFixed(2)}%
      </span>
    )
  }
  const nearEntry = Math.abs(pct) <= 2
  return (
    <span style={{
      fontFamily: "JetBrains Mono, monospace",
      color: nearEntry ? "var(--amber)" : "var(--text-secondary)",
    }}>
      {pct > 0 ? "+" : ""}{pct.toFixed(2)}%
    </span>
  )
}

function SnapshotTable({ snapshots }: { snapshots: CandidateSnapshot[] }) {
  const liveQuotes = useLivePrices()
  const { openSymbol } = useDrawer()
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dense-table">
        <thead>
          <tr>
            {["SYM", "STATUS", "SETUP", "LIVE", "ENTRY", "DIST / P&L", "SCORE"].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {snapshots.map(s => {
            const quote = liveQuotes[s.symbol]
            const triggered = s.entry_triggered
            return (
              <tr
                key={s.id}
                onClick={() => openSymbol(s.symbol)}
                style={{ cursor: "pointer", ...(triggered ? { borderLeft: "2px solid var(--green)" } : {}) }}
              >
                <td><TickerSymbol symbol={s.symbol} /></td>
                <td><StatusBadge status={s.status} /></td>
                <td style={{
                  color: "var(--text-secondary)",
                  maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis",
                }}>
                  {s.setup_category ?? "—"}
                </td>
                <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {quote ? `$${quote.price.toFixed(2)}` : "—"}
                </td>
                <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {s.entry ? `$${s.entry.toFixed(2)}` : "—"}
                </td>
                <td>
                  <DistCell entry={s.entry} quote={quote} triggered={triggered} />
                </td>
                <td style={{
                  fontFamily: "JetBrains Mono, monospace",
                  color: (s.total_score ?? 0) >= 80 ? "var(--green)"
                       : (s.total_score ?? 0) >= 65 ? "var(--amber)"
                       : "var(--text-secondary)",
                }}>
                  {s.total_score?.toFixed(1) ?? "—"}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ManualTable({ picks }: { picks: ManualPick[] }) {
  const liveQuotes = useLivePrices()
  const { openSymbol } = useDrawer()
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dense-table">
        <thead>
          <tr>
            {["SYM", "STATUS", "LIVE", "ENTRY", "DIST / P&L"].map(h => (
              <th key={h}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {picks.map(p => {
            const quote = liveQuotes[p.symbol]
            const triggered = p.status === "active" || p.status === "triggered"
            return (
              <tr key={p.id} onClick={() => openSymbol(p.symbol)} style={{ cursor: "pointer" }}>
                <td><TickerSymbol symbol={p.symbol} /></td>
                <td><StatusBadge status={p.status} /></td>
                <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {quote ? `$${quote.price.toFixed(2)}` : "—"}
                </td>
                <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                  {p.planned_entry ? `$${p.planned_entry.toFixed(2)}` : "—"}
                </td>
                <td>
                  <DistCell entry={p.planned_entry} quote={quote} triggered={triggered} />
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function AddPickForm({ onDone }: { onDone: () => void }) {
  const [sym, setSym]       = useState("")
  const [entry, setEntry]   = useState("")
  const [stop, setStop]     = useState("")
  const [target, setTarget] = useState("")
  const [notes, setNotes]   = useState("")
  const qc  = useQueryClient()
  const mut = useMutation({
    mutationFn: () => api.addPick({
      symbol: sym.toUpperCase(),
      entry:  entry  ? parseFloat(entry)  : undefined,
      stop:   stop   ? parseFloat(stop)   : undefined,
      target: target ? parseFloat(target) : undefined,
      notes,
    }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["picks"] }); onDone() },
  })
  const inp: React.CSSProperties = {
    background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 3,
    color: "var(--text-primary)", padding: "4px 8px", fontSize: 11,
    fontFamily: "JetBrains Mono, monospace", width: "100%", outline: "none",
  }
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--cyan)", letterSpacing: "0.08em", marginBottom: 10 }}>
        Add Manual Pick
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr 1fr 1fr", gap: 8, marginBottom: 8 }}>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Symbol *</div>
          <input style={inp} placeholder="AAPL" value={sym} onChange={e => setSym(e.target.value.toUpperCase())} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Entry</div>
          <input style={inp} placeholder="0.00" type="number" step="0.01" value={entry} onChange={e => setEntry(e.target.value)} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Stop</div>
          <input style={inp} placeholder="0.00" type="number" step="0.01" value={stop} onChange={e => setStop(e.target.value)} />
        </div>
        <div>
          <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Target</div>
          <input style={inp} placeholder="0.00" type="number" step="0.01" value={target} onChange={e => setTarget(e.target.value)} />
        </div>
      </div>
      <div style={{ marginBottom: 10 }}>
        <div style={{ fontSize: 10, color: "var(--text-secondary)", marginBottom: 3 }}>Notes</div>
        <input style={inp} placeholder="Optional notes..." value={notes} onChange={e => setNotes(e.target.value)} />
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <button
          onClick={() => mut.mutate()}
          disabled={!sym || mut.isPending}
          style={{
            background: "var(--cyan)", color: "#000", border: "none", borderRadius: 3,
            padding: "5px 14px", fontSize: 11, fontWeight: 600, cursor: "pointer",
            opacity: (!sym || mut.isPending) ? 0.5 : 1,
          }}
        >
          {mut.isPending ? "Adding..." : "Add Pick"}
        </button>
        <button
          onClick={onDone}
          style={{
            background: "transparent", color: "var(--text-secondary)",
            border: "1px solid var(--border)", borderRadius: 3,
            padding: "5px 14px", fontSize: 11, cursor: "pointer",
          }}
        >
          Cancel
        </button>
        {mut.isError && (
          <span style={{ fontSize: 10, color: "var(--red)", alignSelf: "center" }}>
            Failed — check symbol
          </span>
        )}
      </div>
    </div>
  )
}

export default function WatchlistPage() {
  const [filter, setFilter]     = useState("ALL")
  const [showForm, setShowForm] = useState(false)
  const { data: tracking } = useQuery({ queryKey: ["tracking"], queryFn: api.tracking, refetchInterval: 30_000 })
  const { data: picks }    = useQuery({ queryKey: ["picks"],    queryFn: api.picks,    refetchInterval: 60_000 })

  const snapshots   = [...(tracking?.active ?? []), ...(tracking?.watching ?? [])]
  const filtered    = snapshots.filter(s => matchFilter(s, filter))
  const manualPicks = picks?.picks ?? []

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h1 style={{
          fontSize: 13, fontWeight: 600, color: "var(--text-secondary)",
          textTransform: "uppercase", letterSpacing: "0.08em", margin: 0,
        }}>
          👁 Watchlist
        </h1>
        <button
          onClick={() => setShowForm(v => !v)}
          style={{
            background: showForm ? "var(--bg-elevated)" : "var(--cyan)",
            color: showForm ? "var(--text-secondary)" : "#000",
            border: "1px solid var(--border)", borderRadius: 3,
            padding: "4px 12px", fontSize: 11, fontWeight: 600, cursor: "pointer",
          }}
        >
          {showForm ? "✕ Cancel" : "+ Add Pick"}
        </button>
      </div>

      {showForm && <AddPickForm onDone={() => setShowForm(false)} />}

      <FilterChips options={FILTERS} value={filter} onChange={setFilter} />

      {filtered.length > 0 ? (
        <SnapshotTable snapshots={filtered} />
      ) : (
        <p style={{ color: "var(--text-secondary)", fontSize: 11, padding: "8px 0" }}>
          No positions match this filter
        </p>
      )}

      {manualPicks.length > 0 && (
        <div style={{ marginTop: 20 }}>
          <div style={{
            fontSize: 10, textTransform: "uppercase", letterSpacing: "0.08em",
            color: "var(--text-secondary)", marginBottom: 8,
          }}>
            Manual Picks ({manualPicks.length})
          </div>
          <ManualTable picks={manualPicks} />
        </div>
      )}
    </div>
  )
}
