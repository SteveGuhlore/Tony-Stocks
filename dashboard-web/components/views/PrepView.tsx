"use client"

import { useMorningPrep } from "@/lib/hooks"
import { ViewHeader, Awaiting } from "./shared"
import { fmtScore } from "@/lib/format"

const CONV_COLOR: Record<string, string> = {
  high: "var(--pos)",
  med: "var(--warn)",
  medium: "var(--warn)",
  low: "var(--mut)",
}

export function PrepView({ onOpenSymbol }: { onOpenSymbol: (s: string) => void }) {
  const { data, isLoading } = useMorningPrep()
  const list = data?.shortlist ?? []

  return (
    <div>
      <ViewHeader title="Morning Prep" sub={data?.next_open_label ?? `${list.length} on the shortlist`} />
      {data?.narrative && (
        <p className="text-mut" style={{ fontSize: 12, lineHeight: 1.6, marginBottom: 12 }}>
          <b className="text-ink">What changed overnight:</b> {data.narrative}
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
              <th style={{ textAlign: "left", padding: "5px 6px" }}>Plan</th>
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
                  <b>{fmtScore(p.score)}</b>
                </td>
                <td className="text-mut desktop-only" style={{ padding: "7px 6px" }}>
                  {p.setup_category ?? "—"}
                </td>
                <td className="text-mut desktop-only" style={{ padding: "7px 6px" }}>
                  {p.catalyst ?? "—"}
                </td>
                <td className="text-mut" style={{ padding: "7px 6px" }}>
                  {p.plan ?? "—"}
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
