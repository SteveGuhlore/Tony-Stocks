"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { scaleY } from "@/lib/chart"
import { useCommandCenter } from "@/lib/hooks/useCommandCenter"

function pct(wr: number | null | undefined): string {
  return wr != null ? `${Math.round(wr * 100)}%` : "—"
}
function num(v: number | null | undefined, dp = 2): string {
  return v != null ? v.toFixed(dp) : "—"
}

function Stat({ value, label, color = "var(--text-primary)" }: { value: string; label: string; color?: string }) {
  return (
    <div>
      <div className="mono" style={{ fontSize: 20, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>{label}</div>
    </div>
  )
}

function EquityOverlay({ tony, cc }: { tony: number[]; cc: number[] }) {
  if (tony.length < 2) {
    return <p style={{ color: "var(--text-tertiary)", fontSize: 11 }}>Not enough closed trades to chart equity yet.</p>
  }
  const W = 600, H = 120
  const all = [...tony, ...cc]
  const min = Math.min(...all), max = Math.max(...all)
  const line = (arr: number[], stroke: string) =>
    arr.length < 2 ? null : (
      <polyline points={arr.map((v, i) => `${(i / (arr.length - 1)) * W},${scaleY(v, min, max, H)}`).join(" ")} fill="none" stroke={stroke} strokeWidth={1.6} vectorEffect="non-scaling-stroke" />
    )
  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={H} style={{ display: "block", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6 }}>
      {line(cc, "var(--green)")}
      {line(tony, "var(--accent)")}
    </svg>
  )
}

function SetupBreakdown({ rows }: { rows: Record<string, unknown>[] }) {
  const parsed = rows.map((r) => {
    const label = Object.values(r).find((v) => typeof v === "string") as string | undefined
    const wr = (typeof r.win_rate === "number" ? r.win_rate : undefined)
    return { label: label ?? "—", wr }
  }).filter((r) => r.wr != null)
  if (parsed.length === 0) return <p style={{ color: "var(--text-tertiary)", fontSize: 11 }}>No setup breakdown yet.</p>
  return (
    <div className="mono" style={{ fontSize: 11, color: "var(--text-secondary)" }}>
      {parsed.map((r, i) => (
        <div key={i} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
          <span style={{ width: 80, color: "var(--text-tertiary)" }}>{r.label}</span>
          <div style={{ flex: 1, height: 5, background: "var(--bg-elevated)", borderRadius: 3 }}>
            <div style={{ width: `${Math.round((r.wr ?? 0) * 100)}%`, height: 5, background: "var(--accent)", borderRadius: 3 }} />
          </div>
          <span>{pct(r.wr)}</span>
        </div>
      ))}
    </div>
  )
}

function MatrixCell({ value, label, color = "var(--text-secondary)" }: { value: string; label: string; color?: string }) {
  return (
    <div style={{ background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6, padding: 8 }}>
      <div className="mono" style={{ fontSize: 16, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 9, color: "var(--text-tertiary)" }}>{label}</div>
    </div>
  )
}

const label = (t: string) => (
  <div style={{ fontSize: 9, letterSpacing: "0.08em", color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: 10 }}>{t}</div>
)

export default function RecordPage() {
  const outcomes = useQuery({ queryKey: ["outcomes"], queryFn: () => api.outcomes(), refetchInterval: 60_000 })
  const analytics = useQuery({ queryKey: ["analytics"], queryFn: api.analytics, refetchInterval: 60_000 })
  const cc = useCommandCenter()

  const k = outcomes.data?.kpis
  const bt = analytics.data?.backtest
  const equity = bt?.equity_curve ?? []
  const bySetup = (bt?.by_setup_category ?? []) as Record<string, unknown>[]
  const ccRec = cc.record
  const agr = cc.agreement
  const net = agr ? agr.cc_overrode_saved - agr.cc_overrode_missed : null

  return (
    <div style={{ maxWidth: 760 }}>
      {/* two-record header */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
        <div className="card">
          <div style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--accent)", marginBottom: 8 }}>▣ TONY · first pass</div>
          <div style={{ display: "flex", gap: 18 }}>
            <Stat value={pct(bt?.win_rate ?? k?.win_rate)} label="win rate" />
            <Stat value={num(bt?.avg_simulated_pl_per_trade)} label="avg P/L" />
            <Stat value={String(k?.target_hits ?? "—")} label="tgt hits" color="var(--green)" />
            <Stat value={String(k?.stop_hits ?? "—")} label="stop hits" color="var(--red)" />
          </div>
        </div>
        <div className="card">
          <div style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-secondary)", marginBottom: 8 }}>▢ TONY STOCKS · Command Center</div>
          <div style={{ display: "flex", gap: 18 }}>
            <Stat value={pct(ccRec?.win_rate)} label="win rate" color={ccRec ? "var(--green)" : "var(--text-tertiary)"} />
            <Stat value={num(ccRec?.avg_pl_per_trade)} label="avg P/L" color={ccRec ? "var(--text-primary)" : "var(--text-tertiary)"} />
            <Stat value={String(ccRec?.target_hits ?? "—")} label="tgt hits" color={ccRec ? "var(--green)" : "var(--text-tertiary)"} />
            <Stat value={String(ccRec?.stop_hits ?? "—")} label="stop hits" color={ccRec ? "var(--red)" : "var(--text-tertiary)"} />
          </div>
          {!ccRec && <div style={{ fontSize: 9, color: "var(--text-tertiary)", marginTop: 8 }}>⋯ awaiting Command Center record</div>}
        </div>
      </div>

      {/* equity */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
          <span style={{ fontSize: 9, letterSpacing: "0.08em", color: "var(--text-tertiary)" }}>SIMULATED EQUITY · paper</span>
          <span className="mono" style={{ fontSize: 10 }}><span style={{ color: "var(--accent)" }}>▬ Tony</span> <span style={{ color: ccRec ? "var(--green)" : "var(--text-tertiary)" }}>▬ Tony Stocks{ccRec ? "" : " (awaiting)"}</span></span>
        </div>
        <EquityOverlay tony={equity} cc={ccRec?.equity_curve ?? []} />
      </div>

      {/* matrix + breakdown */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
        <div className="card">
          {label("Does the 2nd pass help?")}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            <MatrixCell value={String(agr?.agreed_right ?? "—")} label="agreed & right" color={agr ? "var(--green)" : "var(--text-secondary)"} />
            <MatrixCell value={String(agr?.agreed_wrong ?? "—")} label="agreed & wrong" color={agr ? "var(--red)" : "var(--text-secondary)"} />
            <MatrixCell value={String(agr?.cc_overrode_saved ?? "—")} label="CC overrode & saved" color={agr ? "var(--green)" : "var(--text-secondary)"} />
            <MatrixCell value={String(agr?.cc_overrode_missed ?? "—")} label="CC overrode & missed" color={agr ? "var(--amber)" : "var(--text-secondary)"} />
          </div>
          <p style={{ fontSize: 10, color: "var(--text-tertiary)", marginTop: 8 }}>
            {net != null
              ? <>On disagreements the Command Center is net <b style={{ color: net >= 0 ? "var(--green)" : "var(--red)" }}>{net >= 0 ? "+" : ""}{net}</b>.</>
              : "Populates once the Command Center returns verdicts."}
          </p>
        </div>
        <div className="card">
          {label("Tony · win rate by setup")}
          <SetupBreakdown rows={bySetup} />
        </div>
      </div>

      <p style={{ fontSize: 10, color: "var(--text-tertiary)", borderTop: "1px solid var(--border)", paddingTop: 10 }}>
        ⓘ {bt?.research_disclaimer ?? "Research only · simulated paper outcomes from snapshot history · not investment advice · past results don't imply future returns"}
      </p>
    </div>
  )
}
