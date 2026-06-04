"use client"
import { scaleY } from "@/lib/chart"
import { useCommandCenter } from "@/lib/hooks/useCommandCenter"
import { usePaperEquityCurve } from "@/lib/hooks/usePaper"

/**
 * Normalized head-to-head equity: the bot's paper book (orange) vs the Command
 * Center's Tony book (cyan), each indexed to 100 so unequal capital ($100k bot vs
 * $1M Tony) compares as a pure % return. Dashed baseline at 100. Both series come
 * pre-normalized from their own publishers (bot: /api/paper/equity-curve index;
 * Tony: command-center record.equity_curve). Research only.
 */
export function HeadToHeadEquity() {
  const bot = usePaperEquityCurve()
  const cc = useCommandCenter()

  const botSeries = bot.points.map((p) => p.index)
  const tonySeries = cc.record?.equity_curve ?? []

  if (botSeries.length < 2 && tonySeries.length < 2) {
    return (
      <p style={{ color: "var(--text-tertiary)", fontSize: 11 }}>
        Collecting… need ≥2 closed trades on either book to chart the head-to-head.
      </p>
    )
  }

  const W = 600, H = 140
  const all = [...botSeries, ...tonySeries, 100]
  const min = Math.min(...all), max = Math.max(...all)

  const line = (arr: number[], stroke: string) =>
    arr.length < 2 ? null : (
      <polyline
        points={arr.map((v, i) => `${(i / (arr.length - 1)) * W},${scaleY(v, min, max, H)}`).join(" ")}
        fill="none" stroke={stroke} strokeWidth={1.8} vectorEffect="non-scaling-stroke"
      />
    )

  const ret = (arr: number[]) => (arr.length ? arr[arr.length - 1] - 100 : 0)
  const fmt = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(2)}%`
  const botRet = ret(botSeries), tonyRet = ret(tonySeries)

  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={H}
        style={{ display: "block", background: "var(--bg-elevated)", border: "1px solid var(--border)", borderRadius: 6 }}>
        <line x1={0} x2={W} y1={scaleY(100, min, max, H)} y2={scaleY(100, min, max, H)}
          stroke="var(--border)" strokeWidth={1} strokeDasharray="4 4" vectorEffect="non-scaling-stroke" />
        {line(tonySeries, "var(--cyan)")}
        {line(botSeries, "var(--amber)")}
      </svg>
      <div style={{ display: "flex", gap: 16, marginTop: 6, fontSize: 11 }}>
        <span style={{ color: "var(--amber)" }}>
          ● Bot (paper) <b>{fmt(botRet)}</b>
        </span>
        <span style={{ color: "var(--cyan)" }}>
          ● Tony <b>{fmt(tonyRet)}</b>
        </span>
        <span style={{ color: "var(--text-tertiary)", marginLeft: "auto" }}>indexed to 100 · research only</span>
      </div>
    </div>
  )
}
