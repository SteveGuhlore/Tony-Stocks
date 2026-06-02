"use client"
import { useEffect, useId, useRef } from "react"
import { useQuery } from "@tanstack/react-query"
import { AnimatePresence, motion } from "motion/react"
import { api } from "@/lib/api"
import { useDrawer } from "./DrawerContext"

const SEV_COLOR: Record<string, string> = {
  error: "var(--red)", warning: "var(--amber)", info: "var(--blue)", high: "var(--red)"
}

export function NotificationDrawer() {
  const { notifDrawerOpen, closeNotif } = useDrawer()
  const panelRef = useRef<HTMLDivElement | null>(null)
  const closeButtonRef = useRef<HTMLButtonElement | null>(null)
  const headingId = useId()

  const { data } = useQuery({
    queryKey: ["events", "notif"],
    queryFn: () => api.events({ limit: 50 }),
    enabled: notifDrawerOpen,
  })

  useEffect(() => {
    if (!notifDrawerOpen) return
    const panel = panelRef.current
    if (!panel) return

    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault()
        closeNotif()
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
  }, [notifDrawerOpen, closeNotif])

  return (
    <AnimatePresence>
      {notifDrawerOpen && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={closeNotif}
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
              position: "fixed", top: 0, right: 0, bottom: 0, width: "min(420px, 100vw)",
              background: "var(--bg-surface)", borderLeft: "1px solid var(--border)",
              zIndex: 201, overflowY: "auto", padding: 20,
            }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <span id={headingId} style={{ fontSize: 13, fontWeight: 600 }}>Notifications</span>
              <button
                ref={closeButtonRef}
                onClick={closeNotif}
                aria-label="Close notifications"
                style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 18 }}
              >×</button>
            </div>
            {data?.events.map(e => (
              <div key={e.id} style={{
                padding: "8px 10px", marginBottom: 6, borderRadius: 3,
                background: "var(--bg-elevated)",
              }}>
                <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
                  <span style={{ width: 6, height: 6, borderRadius: "50%", background: SEV_COLOR[e.severity] ?? "var(--text-tertiary)", display: "inline-block", flexShrink: 0 }} />
                  <span style={{ fontSize: 11, fontWeight: 600, flex: 1 }}>
                    {e.symbol && <span style={{ color: "var(--cyan)", marginRight: 6 }}>{e.symbol}</span>}
                    {e.title}
                  </span>
                  <span style={{ fontSize: 10, color: "var(--text-secondary)", fontFamily: "JetBrains Mono, monospace" }}>{e.created_at.slice(11, 19)}</span>
                </div>
                <p style={{ fontSize: 10, color: "var(--text-secondary)", margin: "4px 0 0 20px" }}>{e.message}</p>
              </div>
            ))}
            {!data && <p style={{ color: "var(--text-secondary)", fontSize: 11 }}>Loading...</p>}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  )
}
