"use client"

import { useMemo, useRef, useState } from "react"
import { useVirtualizer } from "@tanstack/react-virtual"
import type { CockpitRow, RowStatus } from "@/lib/types"
import { TapeRow, TAPE_GRID } from "./TapeRow"

type SortKey = "score" | "symbol" | "change" | "rvol"
type StatusFilter = "all" | RowStatus

const HEADERS = ["Symbol", "Last", "Trend", "Score · TMVRS", "Stop · Entry · Target", "2nd", "Status"]

/**
 * The Tape — virtualized/windowed rows from /api/cockpit. Sort/filter/search.
 * Only visible rows mount, so live ticks + glyph animation stay cheap at 1,000+.
 */
export function Tape({ rows, onOpen }: { rows: CockpitRow[]; onOpen: (s: string) => void }) {
  const [q, setQ] = useState("")
  const [status, setStatus] = useState<StatusFilter>("all")
  const [sort, setSort] = useState<SortKey>("score")
  const parentRef = useRef<HTMLDivElement | null>(null)

  const filtered = useMemo(() => {
    const needle = q.trim().toUpperCase()
    let r = rows.filter((row) => {
      if (status !== "all" && row.status !== status) return false
      if (needle && !row.symbol.toUpperCase().includes(needle) && !(row.sector ?? "").toUpperCase().includes(needle))
        return false
      return true
    })
    r = [...r].sort((a, b) => {
      switch (sort) {
        case "symbol":
          return a.symbol.localeCompare(b.symbol)
        case "change":
          return (b.day_change_pct ?? -Infinity) - (a.day_change_pct ?? -Infinity)
        case "rvol":
          return (b.rvol ?? -Infinity) - (a.rvol ?? -Infinity)
        case "score":
        default:
          return (b.score ?? -Infinity) - (a.score ?? -Infinity)
      }
    })
    return r
  }, [rows, q, status, sort])

  const virt = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 56,
    overscan: 8,
  })

  return (
    <div className="kt-panel" style={{ overflow: "hidden", boxShadow: "0 0 60px rgba(55,224,255,.05)" }}>
      {/* toolbar */}
      <div
        className="flex flex-wrap items-center gap-2"
        style={{ padding: "10px 14px", borderBottom: "1px solid var(--line)" }}
      >
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search symbol / sector…"
          aria-label="Search the tape"
          className="num"
          style={{
            background: "rgba(255,255,255,.04)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            color: "var(--ink)",
            padding: "6px 10px",
            fontSize: 12,
            outline: "none",
          }}
        />
        <SegFilter value={status} onChange={setStatus} />
        <div className="ml-auto flex items-center gap-2 text-mut" style={{ fontSize: 10 }}>
          <span>sort</span>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            aria-label="Sort the tape"
            style={{
              background: "rgba(255,255,255,.04)",
              border: "1px solid var(--line)",
              borderRadius: 8,
              color: "var(--ink)",
              padding: "5px 8px",
              fontSize: 11,
            }}
          >
            <option value="score">Score</option>
            <option value="change">Change</option>
            <option value="rvol">RVOL</option>
            <option value="symbol">Symbol</option>
          </select>
        </div>
      </div>

      {/* header */}
      <div
        role="row"
        className="grid"
        style={{
          gridTemplateColumns: TAPE_GRID,
          padding: "6px 14px",
          fontSize: 8,
          letterSpacing: ".06em",
          textTransform: "uppercase",
          color: "var(--dim)",
        }}
      >
        {HEADERS.map((h) => (
          <div key={h}>{h}</div>
        ))}
      </div>

      {/* virtualized body */}
      {filtered.length === 0 ? (
        <div className="text-dim" style={{ padding: 24, textAlign: "center", fontSize: 12 }}>
          No symbols match — the scanner may be between cycles.
        </div>
      ) : (
        <div ref={parentRef} role="rowgroup" style={{ maxHeight: "62vh", overflowY: "auto" }}>
          <div style={{ height: virt.getTotalSize(), position: "relative" }}>
            {virt.getVirtualItems().map((vi) => {
              const row = filtered[vi.index]
              return (
                <div
                  key={row.symbol}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${vi.start}px)`,
                  }}
                  ref={virt.measureElement}
                  data-index={vi.index}
                >
                  <TapeRow row={row} onOpen={onOpen} />
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function SegFilter({ value, onChange }: { value: StatusFilter; onChange: (v: StatusFilter) => void }) {
  const opts: { k: StatusFilter; l: string }[] = [
    { k: "all", l: "All" },
    { k: "near", l: "Near" },
    { k: "triggered", l: "Triggered" },
    { k: "watching", l: "Watching" },
  ]
  return (
    <div className="flex" style={{ border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden" }}>
      {opts.map((o) => (
        <button
          key={o.k}
          onClick={() => onChange(o.k)}
          style={{
            padding: "5px 11px",
            fontSize: 11,
            background: value === o.k ? "rgba(55,224,255,.14)" : "transparent",
            color: value === o.k ? "var(--cyan)" : "var(--mut)",
            border: "none",
            borderRight: "1px solid var(--line)",
            cursor: "pointer",
          }}
        >
          {o.l}
        </button>
      ))}
    </div>
  )
}
