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
    <div className="fixed top-0 inset-x-0 z-50 flex items-center justify-between bg-zinc-800 border-b border-zinc-700 px-4 py-2 text-sm text-zinc-300">
      <span>Enable desktop notifications for trade alerts?</span>
      <div className="flex gap-2">
        <button
          onClick={request}
          className="px-3 py-1 rounded bg-amber-600 hover:bg-amber-500 text-white text-xs font-semibold"
        >
          Enable
        </button>
        <button
          onClick={() => setShow(false)}
          className="px-3 py-1 rounded bg-zinc-700 hover:bg-zinc-600 text-zinc-300 text-xs"
        >
          Dismiss
        </button>
      </div>
    </div>
  )
}
