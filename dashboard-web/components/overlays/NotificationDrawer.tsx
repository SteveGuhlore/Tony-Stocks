"use client"
import { useQuery } from "@tanstack/react-query"
import { AnimatePresence, motion } from "motion/react"
import { api } from "@/lib/api"
import { useDrawer } from "./DrawerContext"

const SEV_COLOR: Record<string, string> = {
  error: "var(--red)", warning: "var(--amber)", info: "var(--blue)", high: "var(--red)"
}
const SEV_ICON: Record<string, string> = {
  error: "⛔", warning: "⚠", info: "✅", high: "🔴"
}

export function NotificationDrawer() {
  const { notifDrawerOpen, closeNotif } = useDrawer()
  const { data } = useQuery({
    queryKey: ["events", "notif"],
    queryFn: () => api.events({ limit: 50 }),
    enabled: notifDrawerOpen,
  })

  return (
    <AnimatePresence>
      {notifDrawerOpen && (
        <>
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={closeNotif}
            style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.5)", zIndex: 200 }} />
          <motion.div
            initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
            transition={{ type: "tween", duration: 0.2 }}
            style={{
              position: "fixed", top: 0, right: 0, bottom: 0, width: 420,
              background: "var(--bg-surface)", borderLeft: "1px solid var(--border)",
              zIndex: 201, overflowY: "auto", padding: 20,
            }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>🔔 Notifications</span>
              <button onClick={closeNotif} style={{ background: "none", border: "none", color: "var(--text-secondary)", cursor: "pointer", fontSize: 18 }}>×</button>
            </div>
            {data?.events.map(e => (
              <div key={e.id} style={{
                padding: "8px 10px", marginBottom: 6, borderRadius: 3,
                background: "var(--bg-elevated)", borderLeft: `2px solid ${SEV_COLOR[e.severity] ?? "var(--border)"}`,
              }}>
                <div style={{ display: "flex", gap: 8, alignItems: "baseline" }}>
                  <span>{SEV_ICON[e.severity] ?? "•"}</span>
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
