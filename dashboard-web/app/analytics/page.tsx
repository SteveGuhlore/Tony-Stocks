"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { KPIBar } from "@/components/terminal/KPIBar"
import { EquityCurve } from "@/components/charts/EquityCurve"

export default function AnalyticsPage() {
  const { data, isLoading } = useQuery({ queryKey: ["analytics"], queryFn: api.analytics, refetchInterval: 120_000 })
  const { data: vault } = useQuery({ queryKey: ["vault"], queryFn: api.vaultBridge })
  if (isLoading) return <div style={{ color: "var(--text-secondary)" }}>Loading...</div>
  if (!data) return null
  const bt = data.backtest
  const wr = bt.win_rate

  return (
    <div>
      <h1 style={{ fontSize: 13, fontWeight: 600, marginBottom: 16, color: "var(--text-secondary)", textTransform: "uppercase", letterSpacing: "0.08em" }}>
        📈 Analytics
      </h1>
      <KPIBar items={[
        { label: "Reviewed",    value: bt.snapshots_reviewed },
        { label: "Conclusive",  value: bt.conclusive_outcomes },
        { label: "Win Rate",    value: wr !== null ? `${(wr * 100).toFixed(0)}%` : "no data" },
        { label: "Max DD",      value: bt.max_drawdown !== null ? `${(bt.max_drawdown * 100).toFixed(1)}%` : "no data" },
      ]} />
      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>
          Simulated Equity Curve
        </div>
        <EquityCurve curve={bt.equity_curve} />
        <p style={{ fontSize: 10, color: "var(--text-secondary)", marginTop: 8, fontStyle: "italic" }}>{bt.research_disclaimer}</p>
      </div>
      {bt.by_setup_category.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>By Setup Category</div>
          <table className="dense-table">
            <thead><tr><th>Category</th><th>Snapshots</th><th>Triggered</th><th>Target Hit</th><th>Hit Rate</th></tr></thead>
            <tbody>
              {bt.by_setup_category.map((row: any, i: number) => (
                <tr key={i}>
                  <td style={{ color: "var(--text-primary)" }}>{String(row.setup_category ?? "n/a")}</td>
                  <td>{row.total_snapshots ?? "·"}</td>
                  <td>{row.entry_triggered_count ?? "·"}</td>
                  <td>{row.target_hit_count ?? "·"}</td>
                  <td style={{ color: row.target_hit_rate > 0.5 ? "var(--green)" : "var(--text-secondary)" }}>
                    {row.target_hit_rate != null ? `${(row.target_hit_rate * 100).toFixed(0)}%` : "·"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {bt.by_universe_role.length > 0 && (
        <div className="card" style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>By Universe Role</div>
          <table className="dense-table">
            <thead><tr><th>Role</th><th>Snapshots</th><th>Triggered</th><th>Hit Rate</th></tr></thead>
            <tbody>
              {bt.by_universe_role.map((row: any, i: number) => (
                <tr key={i}>
                  <td style={{ color: "var(--text-primary)" }}>{String(row.universe_role ?? "n/a")}</td>
                  <td>{row.total_snapshots ?? "·"}</td>
                  <td>{row.entry_triggered_count ?? "·"}</td>
                  <td style={{ color: row.target_hit_rate > 0.5 ? "var(--green)" : "var(--text-secondary)" }}>
                    {row.target_hit_rate != null ? `${(row.target_hit_rate * 100).toFixed(0)}%` : "·"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {vault?.available && (
        <div className="card">
          <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--cyan)", letterSpacing: "0.08em", marginBottom: 8 }}>
            Vault Bridge · {vault.latest_date}
          </div>
          <pre style={{ fontSize: 10, color: "var(--text-secondary)", whiteSpace: "pre-wrap", maxHeight: 300, overflow: "auto", margin: 0 }}>
            {vault.content}
          </pre>
        </div>
      )}
    </div>
  )
}
