"use client"

import { AnimatePresence, motion } from "motion/react"
import { useEffect, useMemo, useRef, useState } from "react"
import type { CockpitRow } from "@/lib/types"
import { duration, easing } from "@/lib/motion-tokens"

export interface PaletteCommand {
  id: string
  label: string
  kind: "view" | "action" | "symbol"
  danger?: boolean
  run: () => void
}

/** ⌘K palette — jump to a symbol, view, or action (ported from 06-prototype). */
export function CommandPalette({
  open,
  onClose,
  rows,
  commands,
  onSymbol,
}: {
  open: boolean
  onClose: () => void
  rows: CockpitRow[]
  commands: PaletteCommand[]
  onSymbol: (s: string) => void
}) {
  const [q, setQ] = useState("")
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  useEffect(() => {
    if (open) {
      setQ("")
      setActive(0)
      requestAnimationFrame(() => inputRef.current?.focus())
    }
  }, [open])

  const results = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const symCmds: PaletteCommand[] = rows
      .filter((r) => !needle || r.symbol.toLowerCase().includes(needle))
      .slice(0, 6)
      .map((r) => ({
        id: `sym-${r.symbol}`,
        label: `▸ ${r.symbol} · ${r.sector ?? "—"} · score ${r.score ?? "—"}`,
        kind: "symbol" as const,
        run: () => {
          onClose()
          onSymbol(r.symbol)
        },
      }))
    const cmds = commands.filter((c) => !needle || c.label.toLowerCase().includes(needle))
    return [...symCmds, ...cmds].slice(0, 8)
  }, [q, rows, commands, onClose, onSymbol])

  useEffect(() => {
    if (active >= results.length) setActive(0)
  }, [results.length, active])

  return (
    <AnimatePresence>
      {open && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: duration.fast }}
            onClick={onClose}
            className="fixed inset-0 z-[60]"
            style={{ background: "rgba(0,0,0,.45)" }}
          />
          <motion.div
            role="dialog"
            aria-label="Command palette"
            initial={{ opacity: 0, scale: 0.97, y: -8 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.97, y: -8 }}
            transition={{ duration: duration.fast, ease: easing.out }}
            className="fixed left-1/2 z-[61]"
            style={{
              top: 90,
              transform: "translateX(-50%)",
              width: 520,
              maxWidth: "92vw",
              background: "#11150f",
              border: "1px solid rgba(55,224,255,.4)",
              borderRadius: 13,
              boxShadow: "0 24px 70px rgba(0,0,0,.65)",
              overflow: "hidden",
            }}
          >
            <input
              ref={inputRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Jump to a symbol, view, or action…"
              className="num"
              style={{
                width: "100%",
                background: "transparent",
                border: "none",
                borderBottom: "1px solid var(--line)",
                color: "var(--ink)",
                fontSize: 15,
                padding: "14px 16px",
                outline: "none",
              }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") {
                  e.preventDefault()
                  setActive((a) => Math.min(a + 1, results.length - 1))
                } else if (e.key === "ArrowUp") {
                  e.preventDefault()
                  setActive((a) => Math.max(a - 1, 0))
                } else if (e.key === "Enter") {
                  e.preventDefault()
                  results[active]?.run()
                }
              }}
            />
            <div>
              {results.length === 0 ? (
                <div className="text-dim" style={{ padding: "10px 16px", fontSize: 12 }}>
                  no matches
                </div>
              ) : (
                results.map((r, i) => (
                  <div
                    key={r.id}
                    onMouseEnter={() => setActive(i)}
                    onClick={r.run}
                    className="flex items-center gap-[10px]"
                    style={{
                      padding: "10px 16px",
                      fontSize: 12,
                      cursor: "pointer",
                      borderBottom: "1px solid var(--line)",
                      background: i === active ? "rgba(55,224,255,.1)" : "transparent",
                    }}
                  >
                    <span style={{ color: r.danger ? "var(--neg)" : "var(--ink)" }}>{r.label}</span>
                    <span
                      className="ml-auto text-dim"
                      style={{ fontSize: 9, border: "1px solid var(--line)", borderRadius: 4, padding: "1px 5px" }}
                    >
                      {r.kind}
                    </span>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
