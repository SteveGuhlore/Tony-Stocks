"use client"
import { useDrawer } from "@/components/overlays/DrawerContext"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { formatPrice, formatSignedPct } from "@/lib/format"
import type { ScanResultRow } from "@/lib/types"

const COLS = "1.2fr .9fr .55fr 1fr .45fr 2.2fr"

export function UniverseTable({ rows }: { rows: ScanResultRow[] }) {
  const { openSymbol } = useDrawer()
  const quotes = useLivePrices()

  if (rows.length === 0) {
    return <p style={{ color: "var(--text-tertiary)", fontSize: 12, padding: "16px" }}>No scan results yet.</p>
  }

  return (
    <div>
      <div className="mono" style={{ display: "grid", gridTemplateColumns: COLS, gap: 10, padding: "8px 16px", fontSize: 9, letterSpacing: "0.06em", color: "var(--text-tertiary)", borderBottom: "1px solid var(--border)" }}>
        <div>TICKER</div>
        <div style={{ textAlign: "right" }}>LAST · DAY</div>
        <div style={{ textAlign: "right" }}>TONY</div>
        <div>SETUP</div>
        <div style={{ textAlign: "right" }}>R:R</div>
        <div>WHY · reasons / tags</div>
      </div>
      {rows.map((r) => {
        const q = quotes[r.symbol]
        const last = q?.price ?? r.close
        const why = [...(r.reasons ?? []).slice(0, 2), ...(r.tags ?? []).slice(0, 2)].join(" · ")
        return (
          <div
            key={r.symbol}
            role="button"
            tabIndex={0}
            onClick={() => openSymbol(r.symbol)}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openSymbol(r.symbol) } }}
            className="board-row"
            style={{ display: "grid", gridTemplateColumns: COLS, gap: 10, alignItems: "center", padding: "9px 16px", borderBottom: "1px solid var(--border-soft)", cursor: "pointer" }}
          >
            <div>
              <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>{r.symbol}</span>{" "}
              <span style={{ fontSize: 9, color: "var(--text-tertiary)" }}>{r.sector}</span>
            </div>
            <div style={{ textAlign: "right" }}>
              <div className="mono" style={{ fontSize: 12 }}>{formatPrice(last)}</div>
              {q && <div className="mono" style={{ fontSize: 9, color: q.change_pct >= 0 ? "var(--green)" : "var(--red)" }}>{formatSignedPct(q.change_pct)} day</div>}
            </div>
            <div className="mono" style={{ textAlign: "right", fontSize: 12, color: "var(--accent)", fontWeight: 700 }}>{Math.round(r.score)}</div>
            <div style={{ fontSize: 11, color: "var(--text-secondary)" }}>{r.setup_category}</div>
            <div className="mono" style={{ textAlign: "right", fontSize: 12, color: "var(--text-secondary)" }}>{r.rr != null ? r.rr.toFixed(1) : "—"}</div>
            <div style={{ fontSize: 10.5, color: "var(--text-tertiary)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{why || "—"}</div>
          </div>
        )
      })}
    </div>
  )
}
