"use client"
import { TickerSymbol } from "./TickerSymbol"
import type { ScanResultRow } from "@/lib/types"

function rr(r: ScanResultRow): string {
  if (!r.entry || !r.stop || !r.target) return "—"
  const risk = r.entry - r.stop
  const reward = r.target - r.entry
  if (risk <= 0) return "—"
  return `${(reward / risk).toFixed(1)}:1`
}

function entryDelta(r: ScanResultRow): string {
  if (!r.close || !r.entry || r.close === 0) return ""
  const pct = ((r.entry - r.close) / r.close) * 100
  if (Math.abs(pct) < 0.01) return "at mkt"
  return pct > 0 ? `+${pct.toFixed(1)}%` : `${pct.toFixed(1)}%`
}

export function ScanTable({ results }: { results: ScanResultRow[] }) {
  if (!results.length) return <p style={{ color: "var(--text-secondary)", padding: 16 }}>No results</p>
  return (
    <div style={{ overflowX: "auto" }}>
      <table className="dense-table">
        <thead>
          <tr>
            {["SYM","SCORE","SETUP","CLOSE","ENTRY","STOP","TARGET","R:R","PLAN"].map(h => <th key={h}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {results.map(r => (
            <tr key={r.symbol}>
              <td><TickerSymbol symbol={r.symbol} /></td>
              <td style={{ color: r.score >= 80 ? "var(--green)" : r.score >= 65 ? "var(--amber)" : "var(--text-primary)" }}>
                {r.score.toFixed(1)}
              </td>
              <td style={{ color: "var(--text-secondary)", maxWidth: 140, overflow: "hidden", textOverflow: "ellipsis" }}>{r.setup_category}</td>
              <td style={{ fontFamily: "JetBrains Mono, monospace" }}>${r.close.toFixed(2)}</td>
              <td style={{ fontFamily: "JetBrains Mono, monospace" }}>
                ${r.entry.toFixed(2)}
                {entryDelta(r) && (
                  <span style={{ fontSize: 9, color: "var(--text-secondary)", marginLeft: 4 }}>{entryDelta(r)}</span>
                )}
              </td>
              <td style={{ color: "var(--red)", fontFamily: "JetBrains Mono, monospace" }}>${r.stop.toFixed(2)}</td>
              <td style={{ color: "var(--green)", fontFamily: "JetBrains Mono, monospace" }}>${r.target.toFixed(2)}</td>
              <td style={{ fontFamily: "JetBrains Mono, monospace" }}>{rr(r)}</td>
              <td style={{ color: r.trade_plan_valid ? "var(--green)" : "var(--red)" }}>
                {r.trade_plan_valid ? "✓" : "✗"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
