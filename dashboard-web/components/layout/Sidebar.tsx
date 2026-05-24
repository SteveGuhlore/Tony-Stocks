"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"

const NAV = [
  { href: "/today",     icon: "⚡", label: "Today"     },
  { href: "/watchlist", icon: "👁", label: "Watchlist" },
  { href: "/outcomes",  icon: "📊", label: "Outcomes"  },
  { href: "/scan",      icon: "🔍", label: "Scan"      },
  { href: "/analytics", icon: "📈", label: "Analytics" },
  { href: "/system",    icon: "⚙", label: "System"    },
]

export function Sidebar() {
  const pathname = usePathname()
  return (
    <nav style={{
      position: "fixed", left: 0, top: 0, bottom: 0, width: 52,
      background: "var(--bg-surface)", borderRight: "1px solid var(--border)",
      display: "flex", flexDirection: "column", alignItems: "center",
      paddingTop: 12, gap: 4, zIndex: 100,
    }}>
      <div style={{ fontSize: 16, fontWeight: 700, color: "var(--cyan)", fontFamily: "JetBrains Mono, monospace", marginBottom: 12 }}>T</div>
      {NAV.map(({ href, icon, label }) => {
        const active = pathname.startsWith(href)
        return (
          <Link key={href} href={href} title={label} style={{
            display: "flex", alignItems: "center", justifyContent: "center",
            width: 40, height: 40, borderRadius: 4, textDecoration: "none", fontSize: 18,
            background: active ? "var(--bg-elevated)" : "transparent",
            borderLeft: active ? "2px solid var(--cyan)" : "2px solid transparent",
            transition: "all 0.15s",
          }}>
            {icon}
          </Link>
        )
      })}
    </nav>
  )
}
