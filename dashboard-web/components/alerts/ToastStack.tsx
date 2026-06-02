"use client"
import type { CSSProperties } from "react"
import type { LiveAlertToast } from "@/lib/hooks/useAlerts"

interface Props {
  toasts: LiveAlertToast[]
  onDismiss: (id: string) => void
}

const LABELS: Record<string, string> = {
  near_entry: "Near Entry",
  stop_violation: "Stop Violation",
}

const CONTAINER_STYLES: Record<string, CSSProperties> = {
  near_entry: {
    borderColor: "rgba(255,171,0,0.6)",
    background: "rgba(255,171,0,0.10)",
  },
  stop_violation: {
    borderColor: "rgba(255,61,61,0.6)",
    background: "rgba(255,61,61,0.10)",
  },
}

const DEFAULT_CONTAINER_STYLE: CSSProperties = {
  borderColor: "var(--border)",
  background: "rgba(15,15,15,0.85)",
}

const TEXT_COLORS: Record<string, string> = {
  near_entry: "var(--amber)",
  stop_violation: "var(--red)",
}

export function ToastStack({ toasts, onDismiss }: Props) {
  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 w-72">
      {toasts.map((t) => {
        const { alert } = t
        const label = LABELS[alert.alert_type] ?? alert.alert_type
        const containerStyle = CONTAINER_STYLES[alert.alert_type] ?? DEFAULT_CONTAINER_STYLE
        const textColor = TEXT_COLORS[alert.alert_type] ?? "var(--text-primary)"
        return (
          <div
            key={t.id}
            className="flex items-start justify-between gap-2 rounded border px-3 py-2 backdrop-blur text-sm"
            style={containerStyle}
          >
            <div>
              <div className="font-semibold" style={{ color: textColor }}>
                {label}: {alert.symbol}
              </div>
              <div
                className="font-mono text-xs mt-0.5"
                style={{
                  color: "var(--text-primary)",
                  fontFamily: "JetBrains Mono, monospace",
                  fontVariantNumeric: "tabular-nums",
                }}
              >
                ${alert.price.toFixed(2)}
                {alert.entry && (
                  <span style={{ color: "var(--text-tertiary)" }}>
                    {" "}· entry ${alert.entry.toFixed(2)}
                  </span>
                )}
                {alert.stop && (
                  <span style={{ color: "var(--text-tertiary)" }}>
                    {" "}· stop ${alert.stop.toFixed(2)}
                  </span>
                )}
              </div>
            </div>
            <button
              onClick={() => onDismiss(t.id)}
              className="shrink-0 mt-0.5"
              style={{ color: "var(--text-tertiary)" }}
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
