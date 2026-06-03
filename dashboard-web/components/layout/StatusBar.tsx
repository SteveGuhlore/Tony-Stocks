"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import { useMarketStatus } from "@/lib/hooks/useMarketStatus"
import { scanAgeLabel } from "@/lib/format"

const NAV = [
  { href: "/", label: "Board" },
  { href: "/record", label: "Track Record" },
]

export function StatusBar() {
  const pathname = usePathname()
  const { data } = useQuery({ queryKey: ["today"], queryFn: api.today, refetchInterval: 30_000 })
  const market = useMarketStatus()

  const scanning = data?.watch.status === "running"
  const wr = data?.kpis.win_rate

  return (
    <header style={{
      position: "fixed", top: 0, left: 0, right: 0, height: 48, zIndex: 100,
      display: "flex", alignItems: "center", gap: 18, padding: "0 16px",
      background: "var(--bg-surface)", borderBottom: "1px solid var(--border)",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{
          width: 7, height: 7, borderRadius: "50%",
          background: scanning ? "var(--green)" : "var(--text-tertiary)",
          boxShadow: scanning ? "0 0 8px var(--green)" : "none",
        }} />
        <span style={{ fontWeight: 800, letterSpacing: "0.04em", color: "var(--text-primary)" }}>TONY</span>
        <span style={{ fontSize: 11, color: "var(--text-secondary)" }}>
          {scanning ? "scanning" : "idle"} · {scanAgeLabel(data?.watch.last_scan_age_seconds ?? null)}
        </span>
      </div>

      <span className="mono" style={{ fontSize: 12, color: "var(--brass)" }}>
        ● {market?.open ? "MARKET OPEN" : "MARKET CLOSED"}
      </span>

      <nav style={{ display: "flex", gap: 4, marginLeft: 8 }}>
        {NAV.map(({ href, label }) => {
          const active = href === "/" ? pathname === "/" : pathname.startsWith(href)
          return (
            <Link key={href} href={href} aria-current={active ? "page" : undefined} style={{
              fontSize: 12, padding: "4px 10px", borderRadius: 6, textDecoration: "none",
              color: active ? "var(--text-primary)" : "var(--text-secondary)",
              background: active ? "var(--bg-elevated)" : "transparent",
            }}>{label}</Link>
          )
        })}
      </nav>

      <div style={{ display: "flex", gap: 14, fontSize: 11, color: "var(--text-secondary)", marginLeft: "auto" }}>
        <span>Watching <b style={{ color: "var(--text-primary)" }}>{data?.kpis.watching ?? "—"}</b></span>
        <span>Triggered <b style={{ color: "var(--text-primary)" }}>{data?.kpis.triggered ?? "—"}</b></span>
        <span>Win <b style={{ color: "var(--green)" }}>{wr != null ? `${Math.round(wr * 100)}%` : "—"}</b></span>
      </div>
    </header>
  )
}
