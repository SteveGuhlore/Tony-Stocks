"use client"
import { useState, useEffect } from "react"

export function PermissionBanner() {
  const [show, setShow] = useState(false)

  useEffect(() => {
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      setShow(true)
    }
  }, [])

  if (!show) return null

  async function request() {
    const result = await Notification.requestPermission()
    if (result !== "default") setShow(false)
  }

  return (
    <div
      className="fixed top-0 inset-x-0 z-50 flex items-center justify-between border-b px-4 py-2 text-sm"
      style={{
        background: "var(--bg-surface)",
        borderColor: "var(--border)",
        color: "var(--text-primary)",
      }}
    >
      <span>Enable desktop notifications for trade alerts?</span>
      <div className="flex gap-2">
        <button
          onClick={request}
          className="px-3 py-1 rounded text-xs font-semibold"
          style={{ background: "var(--amber)", color: "var(--bg-base)" }}
        >
          Enable
        </button>
        <button
          onClick={() => setShow(false)}
          className="px-3 py-1 rounded text-xs"
          style={{ background: "var(--bg-elevated)", color: "var(--text-secondary)" }}
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
