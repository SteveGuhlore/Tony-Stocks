"use client"

import { useMorningPrep } from "@/lib/hooks"
import type { PrepCatalysts } from "@/lib/types"
import { ViewHeader, Awaiting } from "./shared"
import { fmtPrice } from "@/lib/format"

const CONV_COLOR: Record<string, string> = {
  high: "var(--pos)",
  med: "var(--warn)",
  medium: "var(--warn)",
  low: "var(--mut)",
}

/** Normalized 0–1 score → whole-number 0–100 for display. */
function fmtPrepScore(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  return String(Math.round(v * 100))
}

/** entry → stop → target (+ R:R), em-dash when no levels. */
function fmtPlan(entry?: number | null, stop?: number | null, target?: number | null, rr?: number | null): string {
  if (entry == null && stop == null && target == null) return "—"
  const levels = `${fmtPrice(entry)} → ${fmtPrice(stop)} → ${fmtPrice(target)}`
  return rr != null && !Number.isNaN(rr) ? `${levels}  (${rr.toFixed(1)}R)` : levels
}

/** Compact human catalyst summary from the catalyst tags dict. */
function fmtCatalyst(c?: PrepCatalysts | null): string {
  if (!c) return "—"
  const parts: string[] = []
  if (c.earnings_blackout) parts.push("earnings ⚠")
  else if (c.upcoming_earnings_date) parts.push(`ER ${c.upcoming_earnings_date}`)
  if (c.analyst_rec_trend) parts.push(c.analyst_rec_trend)
  if (c.news_sentiment) parts.push(c.news_sentiment)
  return parts.length ? parts.join(" · ") : "—"
}

export function PrepView({ onOpenSymbol }: { onOpenSymbol: (s: string) => void }) {
  const { data, isLoading } = useMorningPrep()
  const list = data?.shortlist ?? []
  const sub = data?.et_date ? `${list.length} on the shortlist · ${data.et_date}` : `${list.length} on the shortlist`

  return (
    <div>
      <ViewHeader title="Morning Prep" sub={sub} />
      {data?.what_changed_overnight && (
        <p className="text-mut" style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 12 }}>
          <b className="text-ink">What changed overnight:</b> {data.what_changed_overnight}
        </p>
      )}
      {isLoading ? (
        <Awaiting what="morning shortlist" />
      ) : list.length === 0 ? (
        <div className="text-dim" style={{ fontSize: 11 }}>
          No shortlist yet — the pre-open engine runs before the next session.
        </div>
      ) : (
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead>
            <tr style={{ color: "var(--dim)", fontSize: 9, textTransform: "uppercase" }}>
              <th style={{ textAlign: "left", padding: "5px 6px" }}>Symbol</th>
              <th style={{ textAlign: "left", padding: "5px 6px" }}>Conv.</th>
              <th style={{ textAlign: "left", padding: "5px 6px" }}>Score</th>
              <th style={{ textAlign: "left", padding: "5px 6px" }} className="desktop-only">
                Setup
              </th>
              <th style={{ textAlign: "left", padding: "5px 6px" }} className="desktop-only">
                Catalyst
              </th>
              <th style={{ textAlign: "left", padding: "5px 6px" }}>Plan (entry → stop → target)</th>
            </tr>
          </thead>
          <tbody>
            {list.map((p) => (
              <tr key={p.symbol} onClick={() => onOpenSymbol(p.symbol)} style={{ borderTop: "1px solid var(--line)", cursor: "pointer" }}>
                <td className="font-display font-semibold" style={{ padding: "7px 6px" }}>
                  {p.symbol}
                </td>
                <td style={{ padding: "7px 6px" }}>
                  <span
                    style={{
                      fontSize: 9,
                      padding: "2px 7px",
                      borderRadius: 5,
                      background: "rgba(255,255,255,.05)",
                      color: CONV_COLOR[(p.conviction ?? "").toLowerCase()] ?? "var(--mut)",
                    }}
                  >
                    {p.conviction ?? "—"}
                  </span>
                </td>
                <td className="num" style={{ padding: "7px 6px" }}>
                  <b>{fmtPrepScore(p.score)}</b>
                </td>
                <td className="text-mut desktop-only" style={{ padding: "7px 6px" }}>
                  {p.setup ?? "—"}
                </td>
                <td className="text-mut desktop-only" style={{ padding: "7px 6px" }}>
                  {fmtCatalyst(p.catalysts)}
                </td>
                <td className="num text-mut" style={{ padding: "7px 6px", whiteSpace: "nowrap" }}>
                  {fmtPlan(p.entry, p.stop, p.target, p.rr)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {data?.plan_for_open && (
        <p className="text-mut" style={{ fontSize: 12, lineHeight: 1.6, marginTop: 12 }}>
          <b className="text-ink">Plan for open:</b> {data.plan_for_open}
        </p>
      )}
    </div>
  )
}
