"use client"
import { useEffect, useId, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { AnimatePresence, motion } from "motion/react"
import { api } from "@/lib/api"
import { useDrawer } from "./DrawerContext"
import { ScoreBreakdown } from "@/components/charts/ScoreBreakdown"
import { PlanRail, VerdictChip } from "@/components/board/cells"
import { PlanChart } from "@/components/board/PlanChart"
import { useLivePrices } from "@/lib/hooks/useLivePrices"
import { useCommandCenter } from "@/lib/hooks/useCommandCenter"
import { formatPrice, formatSignedPct, plPercent } from "@/lib/format"

export function SymbolDrawer() {
  const { symbolDrawer, closeSymbol } = useDrawer()
  const liveQuotes = useLivePrices()
  const panelRef = useRef<HTMLDivElement | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const headingId = useId()
  const isOpen = !!symbolDrawer

  const { data } = useQuery({
    queryKey: ["symbolDetail", symbolDrawer],
    queryFn: () => api.symbolDetail(symbolDrawer!),
    enabled: isOpen,
  })

  useEffect(() => {
    if (!isOpen) return
    const panel = panelRef.current
    if (!panel) return
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); closeSymbol(); return }
      if (e.key !== "Tab") return
      const focusables = panel.querySelectorAll<HTMLElement>(
        '[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey && (active === first || !panel.contains(active))) { e.preventDefault(); last.focus() }
      else if (!e.shiftKey && active === last) { e.preventDefault(); first.focus() }
    }
    document.addEventListener("keydown", onKeyDown)
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    const rafId = requestAnimationFrame(() => closeButtonRef.current?.focus())
    return () => {
      document.removeEventListener("keydown", onKeyDown)
      document.body.style.overflow = prevOverflow
      cancelAnimationFrame(rafId)
    }
  }, [isOpen, closeSymbol])

  const cc = useCommandCenter()
  const ccPick = symbolDrawer ? cc.picks[symbolDrawer] : undefined
  const snap = data?.latest_snapshot
  const scan = data?.latest_scan_result
  const quote = symbolDrawer ? liveQuotes[symbolDrawer] : undefined
  const last = quote?.price ?? null
  const pl = snap?.entry_triggered ? plPercent(snap.entry, last) : null

  const label = (t: string) => (
    <div style={{ fontSize: 9, letterSpacing: "0.08em", color: "var(--text-tertiary)", textTransform: "uppercase", marginBottom: 6 }}>{t}</div>
  )

  return (
    <AnimatePresence>
      {symbolDrawer && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={closeSymbol} tabIndex={-1} aria-hidden="true"
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.55)", zIndex: 200 }} />
          <motion.div
            ref={panelRef} role="dialog" aria-modal="true" aria-labelledby={headingId}
            className="drawer-panel"
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
            style={{
              position: "fixed", top: 0, right: 0, bottom: 0, width: "min(560px, 100vw)",
              background: "var(--bg-base)", borderLeft: "1px solid var(--border)",
              zIndex: 201, overflowY: "auto", padding: 18,
            }}>

            {/* header */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 12 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button ref={closeButtonRef} onClick={closeSymbol} aria-label="Close symbol details"
                  style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 16 }}>←</button>
                <div>
                  <span id={headingId} style={{ fontSize: 22, fontWeight: 800, color: "var(--text-primary)" }}>{symbolDrawer}</span>
                  {scan && <span style={{ fontSize: 11, color: "var(--text-tertiary)", marginLeft: 8 }}>{scan.name} · {scan.sector} · {scan.setup_category}</span>}
                </div>
              </div>
              <div className="mono" style={{ textAlign: "right" }}>
                <div style={{ fontSize: 18, fontWeight: 700 }}>{formatPrice(last)}</div>
                <div style={{ fontSize: 10, color: "var(--text-secondary)" }}>
                  {quote && <span style={{ color: quote.change_pct >= 0 ? "var(--green)" : "var(--red)" }}>{formatSignedPct(quote.change_pct)} day</span>}
                  {pl != null && <span style={{ color: pl >= 0 ? "var(--green)" : "var(--red)" }}> · P/L {formatSignedPct(pl)}</span>}
                </div>
              </div>
            </div>

            {/* big rail */}
            {snap && (
              <div style={{ marginBottom: 14 }}>
                <PlanRail stop={snap.stop} entry={snap.entry} target={snap.target} live={last}
                  markerTone={snap.entry_triggered ? (pl != null && pl >= 0 ? "green" : "red") : "azure"} />
                {snap.risk_reward != null && <div className="mono" style={{ fontSize: 9, color: "var(--text-tertiary)", textAlign: "right", marginTop: 2 }}>R:R {snap.risk_reward.toFixed(1)}</div>}
              </div>
            )}

            {/* chart */}
            <div className="card" style={{ marginBottom: 12 }}>
              <PlanChart bars={data?.chart_bars ?? []} stop={snap?.stop ?? null} entry={snap?.entry ?? null} target={snap?.target ?? null} />
            </div>

            {/* dual analysis */}
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
              <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--accent)" }}>▣ TONY</span>
                  <span className="mono" style={{ fontSize: 16, fontWeight: 700, color: "var(--accent)" }}>{snap?.total_score != null ? Math.round(snap.total_score) : "—"}</span>
                </div>
                {scan && (
                  <div style={{ marginTop: 8 }}>
                    <ScoreBreakdown scores={{ trend: scan.trend_score, momentum: scan.momentum_score, volume: scan.volume_score, risk: scan.risk_score, setup_quality: scan.setup_quality_score }} />
                  </div>
                )}
                {snap?.tony_hypothesis && <p style={{ fontSize: 11, color: "var(--text-primary)", margin: "8px 0 0", fontStyle: "italic", lineHeight: 1.5 }}>{snap.tony_hypothesis}</p>}
                {(scan?.reasons?.length ?? 0) > 0 && <div style={{ fontSize: 10.5, color: "var(--green)", marginTop: 8, lineHeight: 1.6 }}>{scan!.reasons.map((r, i) => <div key={i}>✓ {r}</div>)}</div>}
                {(scan?.warnings?.length ?? 0) > 0 && <div style={{ fontSize: 10.5, color: "var(--amber)", marginTop: 4, lineHeight: 1.6 }}>{scan!.warnings.map((w, i) => <div key={i}>⚠ {w}</div>)}</div>}
              </div>

              <div className="card">
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span style={{ fontSize: 10, letterSpacing: "0.08em", color: "var(--text-secondary)" }}>▢ TONY STOCKS</span>
                  <span className="mono" style={{ fontSize: 16, fontWeight: 700, color: ccPick ? "var(--green)" : "var(--text-tertiary)" }}>{ccPick ? Math.round(ccPick.score) : "⋯"}</span>
                </div>
                <div style={{ marginTop: 10 }}><VerdictChip verdict={ccPick?.verdict ?? null} /></div>
                {ccPick
                  ? <>
                      <p style={{ fontSize: 11, color: "var(--text-primary)", marginTop: 10, lineHeight: 1.5 }}>{ccPick.reasoning}</p>
                      <div className="mono" style={{ fontSize: 9, color: "var(--text-tertiary)", marginTop: 8 }}>returned {ccPick.returned_at.slice(0, 16).replace("T", " ")}</div>
                    </>
                  : <p style={{ fontSize: 11, color: "var(--text-tertiary)", marginTop: 10, lineHeight: 1.5 }}>Command Center hasn&apos;t returned analysis for this pick yet. Its score, verdict, and reasoning will appear here once the handoff completes.</p>}
              </div>
            </div>

            {/* timeline */}
            {(data?.recent_snapshots?.length ?? 0) > 0 && (
              <div className="card">
                {label("This pick's life")}
                {data?.recent_snapshots?.slice(0, 6).map((s) => (
                  <div key={s.id} className="mono" style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--border-soft)", fontSize: 10.5 }}>
                    <span style={{ color: "var(--text-tertiary)" }}>{s.snapshot_time.slice(0, 10)}</span>
                    <span style={{ color: "var(--text-secondary)" }}>{s.outcome_label ?? s.status}</span>
                    <span>{s.total_score != null ? Math.round(s.total_score) : "—"}</span>
                  </div>
                ))}
              </div>
            )}

            {!data && <p style={{ color: "var(--text-tertiary)", fontSize: 11 }}>Loading {symbolDrawer}…</p>}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
