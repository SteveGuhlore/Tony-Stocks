"use client"
import { useEffect, useId, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { AnimatePresence, motion } from "motion/react"
import { api } from "@/lib/api"
import { useDrawer } from "./DrawerContext"
import { StatusBadge } from "@/components/terminal/StatusBadge"
import { PriceValue } from "@/components/terminal/PriceValue"
import { ScoreBreakdown } from "@/components/charts/ScoreBreakdown"
import { LivePrice } from "@/components/market/LivePrice"
import { DistanceToBar } from "@/components/market/DistanceToBar"
import { useLivePrices } from "@/lib/hooks/useLivePrices"

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
      if (e.key === "Escape") {
        e.preventDefault()
        closeSymbol()
        return
      }
      if (e.key !== "Tab") return
      const focusables = panel.querySelectorAll<HTMLElement>(
        '[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
      if (focusables.length === 0) return
      const first = focusables[0]
      const last = focusables[focusables.length - 1]
      const active = document.activeElement as HTMLElement | null
      if (e.shiftKey && (active === first || !panel.contains(active))) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
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

  return (
    <AnimatePresence>
      {symbolDrawer && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={closeSymbol}
            tabIndex={-1}
            aria-hidden="true"
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 200 }} />
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby={headingId}
            className="drawer-panel"
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
            style={{
              position: "fixed", top: 0, right: 0, bottom: 0, width: "min(480px, 100vw)",
              background: "var(--bg-surface)", borderLeft: "1px solid var(--border)",
              zIndex: 201, overflowY: "auto", padding: 20,
            }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <button
                  ref={closeButtonRef}
                  onClick={closeSymbol}
                  aria-label="Close symbol details"
                  style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 16 }}
                >←</button>
                <span id={headingId} style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 20, fontWeight: 700, color: "var(--cyan)" }}>{symbolDrawer}</span>
                {data?.latest_snapshot && <StatusBadge status={data.latest_snapshot.status} />}
                <LivePrice quote={liveQuotes[symbolDrawer!]} />
              </div>
              {data?.latest_snapshot?.total_score !== null && (
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 18, color: "var(--cyan)" }}>
                  {data?.latest_snapshot?.total_score?.toFixed(1)}
                </span>
              )}
            </div>

            {data?.latest_scan_result && (
              <div className="card" style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>Score Breakdown</div>
                <ScoreBreakdown scores={{
                  trend: data.latest_scan_result.trend_score,
                  momentum: data.latest_scan_result.momentum_score,
                  volume: data.latest_scan_result.volume_score,
                  risk: data.latest_scan_result.risk_score,
                  setup_quality: data.latest_scan_result.setup_quality_score,
                }} />
              </div>
            )}

            {data?.latest_snapshot && (
              <div className="card" style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>Trade Plan</div>
                <div style={{ display: "flex", gap: 16, fontFamily: "JetBrains Mono, monospace", fontSize: 12 }}>
                  <span>Entry <PriceValue value={data.latest_snapshot.entry} /></span>
                  <span style={{ color: "var(--red)" }}>Stop <PriceValue value={data.latest_snapshot.stop} /></span>
                  <span style={{ color: "var(--green)" }}>Target <PriceValue value={data.latest_snapshot.target} /></span>
                  {data.latest_snapshot.risk_reward !== null && (
                    <span style={{ color: "var(--text-secondary)" }}>R:R {data.latest_snapshot.risk_reward?.toFixed(1)}:1</span>
                  )}
                </div>
                <DistanceToBar
                  quote={liveQuotes[symbolDrawer!]}
                  entry={data.latest_snapshot.entry}
                  stop={data.latest_snapshot.stop}
                  target={data.latest_snapshot.target}
                />
              </div>
            )}

            {data?.latest_snapshot?.tony_hypothesis && (
              <div className="card" style={{ marginBottom: 12 }}>
                <div style={{ fontSize: 10, color: "var(--cyan)", textTransform: "uppercase", letterSpacing: "0.08em", marginBottom: 6, fontFamily: "JetBrains Mono, monospace" }}>
                  {["TONY", data.latest_snapshot.tony_priority_label, data.latest_snapshot.tony_recommended_action].filter(Boolean).join(" · ")}
                </div>
                {data.latest_snapshot.tony_setup_read && (
                  <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: "0 0 6px" }}>{data.latest_snapshot.tony_setup_read}</p>
                )}
                <p style={{ fontSize: 11, color: "var(--text-primary)", margin: 0, fontStyle: "italic" }}>{data.latest_snapshot.tony_hypothesis}</p>
              </div>
            )}

            {(data?.recent_snapshots?.length ?? 0) > 1 && (
              <div className="card">
                <div style={{ fontSize: 10, textTransform: "uppercase", color: "var(--text-secondary)", letterSpacing: "0.08em", marginBottom: 8 }}>Snapshot History</div>
                {data?.recent_snapshots?.slice(1, 6).map(s => (
                  <div key={s.id} style={{ display: "flex", justifyContent: "space-between", padding: "4px 0", borderBottom: "1px solid var(--border)", fontSize: 11, fontFamily: "JetBrains Mono, monospace" }}>
                    <span style={{ color: "var(--text-secondary)" }}>{s.snapshot_time.slice(0, 10)}</span>
                    <StatusBadge status={s.outcome_label ?? s.status} />
                    <span>{s.total_score?.toFixed(1) ?? "—"}</span>
                  </div>
                ))}
              </div>
            )}

            {!data && (
              <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>Loading {symbolDrawer}...</p>
            )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
