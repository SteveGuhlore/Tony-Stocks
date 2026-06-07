"use client"

import { memo } from "react"
import type { CockpitRow } from "@/lib/types"
import { ScoreGlyph } from "@/components/kinetic/ScoreGlyph"
import { VerdictPill } from "@/components/kinetic/VerdictPill"
import { Sparkline } from "@/components/kinetic/Sparkline"
import { PlanRail } from "@/components/kinetic/PlanRail"
import { StatusCell } from "@/components/kinetic/StatusCell"
import { fmtPrice, fmtPct, fmtRvol, changeClass, priceStatusDisplay } from "@/lib/format"
import { useLiveTick } from "@/lib/priceStore"

/** Grid template shared by header + rows so columns align. */
export const TAPE_GRID =
  "minmax(96px,1.3fr) minmax(78px,0.9fr) minmax(82px,1fr) minmax(120px,1.1fr) 138px minmax(96px,1fr) minmax(72px,0.8fr)"

/**
 * One enriched tape row (09). Subscribes to its own symbol's live tick so a price
 * update re-renders ONLY this row, not the whole virtualized table.
 */
export const TapeRow = memo(function TapeRow({
  row,
  onOpen,
}: {
  row: CockpitRow
  onOpen: (symbol: string) => void
}) {
  const tick = useLiveTick(row.symbol)
  const price = tick.price ?? row.last_price ?? row.close
  const change = tick.changePct ?? row.day_change_pct
  const ps = priceStatusDisplay(row.price_status)
  const chgCls = changeClass(change)
  const chgColor = chgCls === "pos" ? "var(--pos)" : chgCls === "neg" ? "var(--neg)" : "var(--mut)"

  return (
    <div
      role="row"
      tabIndex={0}
      onClick={() => onOpen(row.symbol)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault()
          onOpen(row.symbol)
        }
      }}
      className="grid items-center cursor-pointer transition-colors"
      style={{
        gridTemplateColumns: TAPE_GRID,
        gap: 0,
        padding: "10px 14px",
        borderTop: "1px solid var(--line)",
        fontSize: 12,
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(55,224,255,.05)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
    >
      {/* symbol + sector */}
      <div className="font-display font-semibold" style={{ fontSize: 14 }}>
        {row.symbol}
        <small className="block text-mut" style={{ fontSize: 8, fontWeight: 400 }}>
          {row.sector ?? row.setup_category ?? "—"}
        </small>
      </div>

      {/* last + change */}
      <div className="num" style={{ color: chgColor }}>
        {fmtPrice(price)}
        <br />
        <span style={{ fontSize: 10 }}>{fmtPct(change)}</span>
        {!ps.fresh && (
          <span className="block text-dim" style={{ fontSize: 7.5 }}>
            {ps.label}
          </span>
        )}
      </div>

      {/* trend sparkline + rvol */}
      <div>
        <Sparkline data={row.sparkline} />
        <div className="text-mut" style={{ fontSize: 8 }}>
          RVOL <b style={{ color: "var(--cyan)" }}>{fmtRvol(row.rvol)}</b>
        </div>
      </div>

      {/* score glyph */}
      <div>
        <ScoreGlyph score={row.score} sub={row.sub_scores} size="sm" />
      </div>

      {/* plan rail */}
      <div>
        <PlanRail stop={row.stop} entry={row.entry} target={row.target} current={price} />
      </div>

      {/* 2nd pass */}
      <div>
        {row.tony ? (
          <VerdictPill verdict={row.tony.verdict} score={row.tony.score} />
        ) : (
          <VerdictPill verdict="" />
        )}
      </div>

      {/* status */}
      <div>
        <StatusCell row={row} />
      </div>
    </div>
  )
})
