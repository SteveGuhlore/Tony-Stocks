"use client"
import type { LiveAlertToast } from "@/lib/hooks/useAlerts"

interface Props {
  toasts: LiveAlertToast[]
  onDismiss: (id: string) => void
}

const LABELS: Record<string, string> = {
  near_entry: "Near Entry",
  stop_violation: "Stop Violation",
}

const COLORS: Record<string, string> = {
  near_entry: "border-amber-500/60 bg-amber-950/80",
  stop_violation: "border-red-500/60 bg-red-950/80",
}

const TEXT_COLORS: Record<string, string> = {
  near_entry: "text-amber-400",
  stop_violation: "text-red-400",
}

export function ToastStack({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-72">
      {toasts.map((t) => {
        const { alert } = t
        const label = LABELS[alert.alert_type] ?? alert.alert_type
        const border = COLORS[alert.alert_type] ?? "border-zinc-700 bg-zinc-900/80"
        const textColor = TEXT_COLORS[alert.alert_type] ?? "text-zinc-300"
        return (
          <div
            key={t.id}
            className={`flex items-start justify-between gap-2 rounded border px-3 py-2 backdrop-blur text-sm ${border}`}
          >
            <div>
              <div className={`font-semibold ${textColor}`}>{label}: {alert.symbol}</div>
              <div className="text-zinc-300 font-mono tabular-nums text-xs mt-0.5">
                ${alert.price.toFixed(2)}
                {alert.entry && <span className="text-zinc-500"> · entry ${alert.entry.toFixed(2)}</span>}
                {alert.stop && <span className="text-zinc-500"> · stop ${alert.stop.toFixed(2)}</span>}
              </div>
            </div>
            <button
              onClick={() => onDismiss(t.id)}
              className="text-zinc-500 hover:text-zinc-200 shrink-0 mt-0.5"
              aria-label="Dismiss"
            >
              ✕
            </button>
          </div>
        )
      })}
    </div>
  )
}
