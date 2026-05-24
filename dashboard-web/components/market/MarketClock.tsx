"use client"
import { useMarketStatus } from "@/lib/hooks/useMarketStatus"

export function MarketClock() {
  const status = useMarketStatus()

  if (!status) {
    return (
      <div className="flex items-center gap-1.5 text-xs text-zinc-500">
        <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" />
        Market
      </div>
    )
  }

  const label = status.open ? "OPEN" : "CLOSED"
  const color = status.open ? "bg-emerald-400" : "bg-zinc-500"
  const textColor = status.open ? "text-emerald-400" : "text-zinc-400"

  let subtext: string | null = null
  if (!status.open && status.next_open) {
    try {
      const next = new Date(status.next_open)
      subtext = `Opens ${next.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
    } catch {
      subtext = null
    }
  } else if (status.open && status.next_close) {
    try {
      const close = new Date(status.next_close)
      subtext = `Closes ${close.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
    } catch {
      subtext = null
    }
  }

  return (
    <div className="flex flex-col gap-0.5">
      <div className={`flex items-center gap-1.5 text-xs font-semibold ${textColor}`}>
        <span className={`w-1.5 h-1.5 rounded-full ${color} ${status.open ? "animate-pulse" : ""}`} />
        NYSE {label}
      </div>
      {subtext && <div className="text-xs text-zinc-500 pl-3">{subtext}</div>}
    </div>
  )
}
