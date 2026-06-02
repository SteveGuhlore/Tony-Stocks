"use client"
import { useDrawer } from "@/components/overlays/DrawerContext"

export function TickerSymbol({ symbol }: { symbol: string }) {
  const { openSymbol } = useDrawer()
  return (
    <button className="ticker-button" onClick={() => openSymbol(symbol)} style={{
      background: "none", border: "none", cursor: "pointer", padding: "1px 4px",
      color: "var(--cyan)", fontFamily: "JetBrains Mono, monospace",
      fontSize: "inherit", fontWeight: 600, borderRadius: 2,
      transition: "background 0.1s",
    }}
    onMouseEnter={e => (e.currentTarget.style.background = "var(--bg-elevated)")}
    onMouseLeave={e => (e.currentTarget.style.background = "none")}>
      {symbol}
    </button>
  )
}
