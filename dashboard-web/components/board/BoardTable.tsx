"use client"
import { useDrawer } from "@/components/overlays/DrawerContext"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { formatPrice, formatSignedPct, plPercent } from "@/lib/format"
import { boardStatus, STATUS_DISPLAY } from "@/lib/board"
import { PlanRail, ScorePair, VerdictChip, ToneText, TONE_VAR } from "./cells"
import type { CandidateSnapshot, LiveQuote } from "@/lib/types"
import type { Tone } from "@/lib/signal"

const COLS = "1.4fr .9fr .7fr 2.1fr .45fr .8fr 1.05fr .85fr"

function Cell({ children, align = "left" }: { children: React.ReactNode; align?: "left" | "right" }) {
  return <div style={{ textAlign: align, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis" }}>{children}</div>
}

function Row({ snap, quote }: { snap: CandidateSnapshot; quote: LiveQuote | undefined }) {
  const { openSymbol } = useDrawer()
  const last = quote?.price ?? null
  const status = boardStatus(snap, last)
  const triggered = status === "triggered"
  const pl = triggered ? plPercent(snap.entry, last) : null
  const markerTone: Tone = triggered ? (pl != null && pl >= 0 ? "green" : "red") : status === "armed" ? "brass" : "azure"
  const st = STATUS_DISPLAY[status]

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => openSymbol(snap.symbol)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openSymbol(snap.symbol) } }}
      className="board-row"
      style={{
        display: "grid", gridTemplateColumns: COLS, gap: 10, alignItems: "center",
        padding: "10px 16px", borderBottom: "1px solid var(--border-soft)",
        cursor: "pointer", borderLeft: `2px solid ${triggered ? "var(--accent)" : "transparent"}`,
      }}
    >
      <Cell>
        <span style={{ fontWeight: 700, fontSize: 13, color: "var(--text-primary)" }}>{snap.symbol}</span>{" "}
        <span style={{ fontSize: 9, color: "var(--text-tertiary)" }}>{snap.universe_role || snap.setup_category}</span>
      </Cell>
      <Cell align="right">
        <div className="mono" style={{ fontSize: 12 }}>{formatPrice(last)}</div>
        {quote && (
          <div className="mono" style={{ fontSize: 9, color: quote.change_pct >= 0 ? "var(--green)" : "var(--red)" }}>
            {formatSignedPct(quote.change_pct)} day
          </div>
        )}
      </Cell>
      <Cell align="right">
        {pl != null
          ? <span className="mono" style={{ fontSize: 12, fontWeight: 700, color: pl >= 0 ? "var(--green)" : "var(--red)" }}>{formatSignedPct(pl)}</span>
          : status === "armed"
            ? <ToneText tone="brass" size={10}>near entry</ToneText>
            : <span className="mono" style={{ fontSize: 11, color: "var(--text-tertiary)" }}>—</span>}
      </Cell>
      <Cell>
        <PlanRail stop={snap.stop} entry={snap.entry} target={snap.target} live={last} markerTone={markerTone} />
      </Cell>
      <Cell align="right"><span className="mono" style={{ fontSize: 12, color: "var(--text-secondary)" }}>{snap.risk_reward != null ? snap.risk_reward.toFixed(1) : "—"}</span></Cell>
      <Cell align="right"><ScorePair tony={snap.total_score} /></Cell>
      <Cell><VerdictChip verdict={null} /></Cell>
      <Cell><span className="mono" style={{ fontSize: 11, color: TONE_VAR[st.tone as Tone] }}>{st.label}</span></Cell>
    </div>
  )
}

export function BoardTable({ snapshots }: { snapshots: CandidateSnapshot[] }) {
  const quotes = useLivePrices()
  if (snapshots.length === 0) {
    return <p style={{ color: "var(--text-tertiary)", fontSize: 12, padding: "16px" }}>No watches yet — Tony hasn&apos;t flagged anything this session.</p>
  }
  return (
    <div>
      <div className="mono" style={{ display: "grid", gridTemplateColumns: COLS, gap: 10, padding: "8px 16px", fontSize: 9, letterSpacing: "0.06em", color: "var(--text-tertiary)", borderBottom: "1px solid var(--border)" }}>
        <div>TICKER</div>
        <div style={{ textAlign: "right" }}>LAST · DAY</div>
        <div style={{ textAlign: "right" }}>P/L</div>
        <div style={{ textAlign: "center" }}>PLAN · stop · entry · target</div>
        <div style={{ textAlign: "right" }}>R:R</div>
        <div style={{ textAlign: "right" }}>TONY · T.STK</div>
        <div>VERDICT</div>
        <div>STATUS</div>
      </div>
      {snapshots.map((s) => <Row key={s.id} snap={s} quote={quotes[s.symbol]} />)}
    </div>
  )
}
