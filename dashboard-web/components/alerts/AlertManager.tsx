"use client"
import { useSSE } from "@/lib/sse"
import { useAlerts } from "@/lib/hooks/useAlerts"
import { ToastStack } from "./ToastStack"
import { api } from "@/lib/api"
import type { SSELiveAlert } from "@/lib/types"

export function AlertManager() {
  const { toasts, handleAlert, dismiss } = useAlerts()
  const streamUrl = api.streamUrl()

  useSSE(streamUrl, (msg) => {
    if (msg.type === "live_alert") {
      handleAlert(msg as SSELiveAlert)
    }
  })

  return <ToastStack toasts={toasts} onDismiss={dismiss} />
}
