"use client"
import { TickerSymbol } from "./TickerSymbol"
import type { ScanResultRow } from "@/lib/types"

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
              <td>${r.close.toFixed(2)}</td>
              <td>${r.entry.toFixed(2)}</td>
              <td style={{ color: "var(--red)" }}>${r.stop.toFixed(2)}</td>
              <td style={{ color: "var(--green)" }}>${r.target.toFixed(2)}</td>
              <td>{r.rr.toFixed(1)}:1</td>
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
