"use client"

import { useEffect, useState } from "react"
import { motion } from "motion/react"
import type { Phase } from "@/lib/phase"
import { PHASE_LABEL } from "@/lib/phase"
import { fmtMoney, fmtPct } from "@/lib/format"
import { duration } from "@/lib/motion-tokens"
import type { StreamState } from "@/lib/useEventStream"

const PHASES: Phase[] = ["prep", "live", "review"]

export function TopBar({
  phase,
  onPhase,
  sessionLabel,
  equity,
  equityPct,
  streamState,
  onOpenPalette,
}: {
  phase: Phase
  onPhase: (p: Phase) => void
  sessionLabel: string
  equity: number | null
  equityPct: number | null
  streamState: StreamState
  onOpenPalette: () => void
}) {
  const [clock, setClock] = useState("")
  useEffect(() => {
    const tick = () =>
      setClock(
        new Intl.DateTimeFormat("en-US", {
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false,
          timeZone: "America/New_York",
        }).format(new Date()) + " ET",
      )
    tick()
    const id = setInterval(tick, 1000)
    return () => clearInterval(id)
  }, [])

  const live = streamState === "open"

  return (
    <header
      className="flex flex-wrap items-center gap-3"
      style={{ padding: "10px 14px", borderBottom: "1px solid var(--line)", background: "var(--panel)" }}
    >
      <div className="font-display font-bold" style={{ fontSize: 18, letterSpacing: "-.02em" }}>
        TONY
        <small className="block" style={{ fontSize: 8, letterSpacing: ".2em", color: "var(--lime)", fontWeight: 400 }}>
          FIRST-PASS SCANNER
        </small>
      </div>

      <div className="flex items-center gap-[7px] text-mut" style={{ fontSize: 11 }} aria-live="polite">
        <span
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: live ? "var(--pos)" : "var(--warn)",
            boxShadow: live ? "0 0 8px var(--pos)" : "none",
          }}
          aria-label={live ? "stream live" : "stream reconnecting"}
        />
        <span className="num">{clock}</span>
        <span className="text-dim">· {sessionLabel}</span>
      </div>

      {/* phase morph */}
      <div
        className="flex desktop-only"
        role="tablist"
        aria-label="Session phase"
        style={{ border: "1px solid var(--line)", borderRadius: 8, overflow: "hidden" }}
      >
        {PHASES.map((p) => {
          const on = p === phase
          return (
            <button
              key={p}
              role="tab"
              aria-selected={on}
              onClick={() => onPhase(p)}
              style={{ position: "relative", padding: "5px 12px", fontSize: 11, color: on ? "var(--cyan)" : "var(--mut)", background: "transparent", border: "none", borderRight: "1px solid var(--line)", cursor: "pointer" }}
            >
              {on && (
                <motion.span
                  layoutId="phasePill"
                  transition={{ duration: duration.normal }}
                  className="absolute inset-0"
                  style={{ background: "rgba(55,224,255,.15)", zIndex: 0 }}
                />
              )}
              <span style={{ position: "relative", zIndex: 1 }}>{PHASE_LABEL[p]}</span>
            </button>
          )
        })}
      </div>

      <button
        onClick={onOpenPalette}
        aria-label="Open command palette"
        className="kt-btn"
        style={{ padding: "4px 9px", fontSize: 11 }}
      >
        ⌘K
      </button>

      <div className="flex flex-col items-end ml-auto text-mut" style={{ fontSize: 10 }}>
        <span>paper equity</span>
        <b className="num" style={{ fontSize: 12, color: (equityPct ?? 0) >= 0 ? "var(--pos)" : "var(--neg)" }}>
          {fmtMoney(equity)} {equityPct != null ? `${(equityPct ?? 0) >= 0 ? "▲" : "▼"}${fmtPct(equityPct)}` : ""}
        </b>
      </div>
    </header>
  )
}
