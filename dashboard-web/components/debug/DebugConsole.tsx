"use client"

/**
 * Gate for the in-app error console. Public/normal visitors get nothing
 * (no listeners registered, no DOM rendered). The console activates only when
 * `?debug=1`/`#debug` is in the URL or `localStorage.tonyDebug === "1"`.
 *
 * Enablement is resolved after mount (it touches window/localStorage), so SSR
 * and the first client render agree on `null` and there is no hydration
 * mismatch; the console appears on the subsequent client tick when gated on.
 */

import { useEffect, useState } from "react"
import { isDebugEnabled } from "@/lib/debug"
import { ErrorConsole } from "./ErrorConsole"

export function DebugConsole() {
  const [enabled, setEnabled] = useState(false)

  useEffect(() => {
    setEnabled(isDebugEnabled())
  }, [])

  if (!enabled) return null
  return <ErrorConsole />
}
