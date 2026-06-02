"use client"
import { useMarketStatus } from "@/lib/hooks/useMarketStatus"

export function MarketClock() {
  const status = useMarketStatus()

  if (!status) {
    return (
      <div
        className="flex items-center gap-1.5 text-xs"
        style={{ color: "var(--text-tertiary)" }}
      >
        <span
          className="w-1.5 h-1.5 rounded-full"
          style={{ background: "var(--border-focus)" }}
        />
        Market
      </div>
    )
  }

  const label = status.open ? "OPEN" : "CLOSED"
  const dotColor = status.open ? "var(--green)" : "var(--text-tertiary)"
  const textColor = status.open ? "var(--green)" : "var(--text-secondary)"

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
      <div
        className="flex items-center gap-1.5 text-xs font-semibold"
        style={{ color: textColor }}
      >
        <span
          className={`w-1.5 h-1.5 rounded-full ${status.open ? "animate-pulse" : ""}`}
          style={{ background: dotColor }}
        />
        NYSE {label}
      </div>
      {subtext && (
        <div
          className="text-xs pl-3"
          style={{ color: "var(--text-tertiary)" }}
        >
          {subtext}
        </div>
      )}
    </div>
  )
}
