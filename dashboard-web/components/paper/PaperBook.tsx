"use client"
import { useDrawer } from "@/components/overlays/DrawerContext"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { formatPrice, formatSignedPct, plPercent } from "@/lib/format"
import type { LiveQuote, PaperPosition } from "@/lib/types"

const OPEN_COLS = "1.2fr .6fr .9fr .9fr .9fr .9fr 1.2fr"
const CLOSED_COLS = "1.2fr .6fr .9fr .9fr 1fr 1.1fr 1fr"

function Cell({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return <div style={{ textAlign: align, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{children}</div>
}

function HeaderRow({ cols, children }: { cols: string; children: React.ReactNode }) {
  return (
    <div className="mono" style={{
      display: "grid", gridTemplateColumns: cols, gap: 10, padding: "8px 16px",
      fontSize: 9, letterSpacing: "0.06em", color: "var(--text-tertiary)",
      borderBottom: "1px solid var(--border)",
    }}>{children}</div>
  )
}

/** Live dollar + percent P/L for an open paper position, marked against the live quote. */
function openPl(pos: PaperPosition, last: number | null): { dollars: number | null; pct: number | null } {
  const pct = plPercent(pos.entry_price, last)
  const dollars = pos.entry_price != null && last != null ? (last - pos.entry_price) * pos.qty : null
  return { dollars, pct }
}

function fmtDollars(n: number | null): string {
  if (n == null) return "—"
  return `${n >= 0 ? "+" : "−"}$${Math.abs(n).toFixed(2)}`
}

function OpenRow({ pos, quote }: { pos: PaperPosition; quote: LiveQuote | undefined }) {
  const { openSymbol } = useDrawer()
  const last = quote?.price ?? null
  const { dollars, pct } = openPl(pos, last)
  const up = (pct ?? 0) >= 0
  const plColor = pct == null ? "var(--text-tertiary)" : up ? "var(--green)" : "var(--red)"

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => openSymbol(pos.symbol)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openSymbol(pos.symbol) } }}
      className="board-row"
      style={{
        display: "grid", gridTemplateColumns: OPEN_COLS, gap: 10, alignItems: "center",
        padding: "10px 16px", borderBottom: "1px solid var(--border-soft)", cursor: "pointer",
        borderLeft: `2px solid ${pct == null ? "transparent" : up ? "var(--green)" : "var(--red)"}`,
      }}
    >
      <Cell>
        <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>{pos.symbol}</span>{" "}
        <span style={{
          fontSize: 8, fontWeight: 800, letterSpacing: "0.06em", padding: "1px 4px", borderRadius: 3,
          background: "var(--amber)", color: "var(--bg-base)", verticalAlign: "middle",
        }}>PAPER</span>
      </Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{pos.qty}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{formatPrice(pos.entry_price)}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--text-primary)" }}>{formatPrice(last)}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--green)" }}>{formatPrice(pos.target)}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--red)" }}>{formatPrice(pos.stop)}</span></Cell>
      <Cell align="right">
        <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: plColor }}>{fmtDollars(dollars)}</span>{" "}
        <span className="mono" style={{ fontSize: 10, color: plColor }}>({formatSignedPct(pct)})</span>
      </Cell>
    </div>
  )
}

const RESULT_TONE: Record<string, string> = {
  target_hit: "var(--green)",
  stop_hit: "var(--red)",
  closed: "var(--text-secondary)",
  expired: "var(--text-tertiary)",
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? "—" : d.toLocaleDateString(undefined, { month: "short", day: "numeric" })
}

function ClosedRow({ pos }: { pos: PaperPosition }) {
  const { openSymbol } = useDrawer()
  const pl = pos.realized_pl
  const plColor = pl == null ? "var(--text-tertiary)" : pl >= 0 ? "var(--green)" : "var(--red)"
  const result = pos.result ?? "closed"

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => openSymbol(pos.symbol)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openSymbol(pos.symbol) } }}
      className="board-row"
      style={{
        display: "grid", gridTemplateColumns: CLOSED_COLS, gap: 10, alignItems: "center",
        padding: "10px 16px", borderBottom: "1px solid var(--border-soft)", cursor: "pointer",
      }}
    >
      <Cell><span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>{pos.symbol}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{pos.qty}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{formatPrice(pos.entry_price)}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--text-primary)" }}>{formatPrice(pos.exit_price)}</span></Cell>
      <Cell><span className="mono" style={{ fontSize: 11, color: RESULT_TONE[result] ?? "var(--text-secondary)" }}>{result.replace("_", " ")}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, fontWeight: 700, color: plColor }}>{fmtDollars(pl)}</span></Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>{fmtDate(pos.closed_at)}</span></Cell>
    </div>
  )
}

const sectionLabel = (t: string) => (
  <div style={{ fontSize: 9, letterSpacing: "0.08em", color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: 4, padding: "0 16px" }}>{t}</div>
)

export function OpenBook({ positions }: { positions: PaperPosition[] }) {
  const quotes = useLivePrices()
  if (positions.length === 0) {
    return <p style={{ color: "var(--text-tertiary)", fontSize: 12, padding: "16px" }}>No open paper positions — the bot isn&apos;t holding anything right now.</p>
  }
  return (
    <div>
      <HeaderRow cols={OPEN_COLS}>
        <div>SYMBOL</div>
        <div style={{ textAlign: "right" }}>QTY</div>
        <div style={{ textAlign: "right" }}>ENTRY</div>
        <div style={{ textAlign: "right" }}>LAST</div>
        <div style={{ textAlign: "right" }}>TARGET</div>
        <div style={{ textAlign: "right" }}>STOP</div>
        <div style={{ textAlign: "right" }}>P/L · live</div>
      </HeaderRow>
      {positions.map((p) => <OpenRow key={p.symbol} pos={p} quote={quotes[p.symbol]} />)}
    </div>
  )
}

export function ClosedBook({ positions }: { positions: PaperPosition[] }) {
  if (positions.length === 0) {
    return <p style={{ color: "var(--text-tertiary)", fontSize: 12, padding: "16px" }}>No closed paper trades yet — history fills in as positions exit.</p>
  }
  return (
    <div>
      <HeaderRow cols={CLOSED_COLS}>
        <div>SYMBOL</div>
        <div style={{ textAlign: "right" }}>QTY</div>
        <div style={{ textAlign: "right" }}>ENTRY</div>
        <div style={{ textAlign: "right" }}>EXIT</div>
        <div>RESULT</div>
        <div style={{ textAlign: "right" }}>REALIZED</div>
        <div style={{ textAlign: "right" }}>CLOSED</div>
      </HeaderRow>
      {positions.map((p, i) => <ClosedRow key={`${p.symbol}-${p.closed_at ?? i}`} pos={p} />)}
    </div>
  )
}

export { sectionLabel }
