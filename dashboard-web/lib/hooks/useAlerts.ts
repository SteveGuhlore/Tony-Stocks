"use client"
import { useState, useCallback } from "react"
import type { SSELiveAlert } from "@/lib/types"
import { playBeep } from "@/lib/sound"

export interface LiveAlertToast {
  id: string
  alert: SSELiveAlert
  at: number
}

const MAX_TOASTS = 5

export function useAlerts() {
  const [toasts, setToasts] = useState<LiveAlertToast[]>([])

  const handleAlert = useCallback((alert: SSELiveAlert) => {
    playBeep(alert.alert_type)
    if (typeof window !== "undefined" && Notification.permission === "granted") {
      new Notification(`${alert.alert_type === "near_entry" ? "Near Entry" : "Stop Violation"}: ${alert.symbol}`, {
        body: `Price $${alert.price.toFixed(2)}`,
        tag: `${alert.alert_type}-${alert.symbol}`,
        silent: true,
      })
    }
    setToasts((prev) => {
      const next: LiveAlertToast[] = [
        { id: `${Date.now()}-${Math.random()}`, alert, at: Date.now() },
        ...prev,
      ]
      return next.slice(0, MAX_TOASTS)
    })
  }, [])

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return { toasts, handleAlert, dismiss }
}
