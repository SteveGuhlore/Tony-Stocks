"use client" // Error boundaries must be Client Components

/**
 * Root-level error boundary. Next's in-tree boundary (our ErrorBoundary in the
 * layout) does NOT catch errors thrown by the root layout itself; those route
 * here. global-error replaces the root layout, so it must render its own
 * <html>/<body> and pull in global styles. We surface the crash and, when the
 * debug gate is on, mount the same copyable error console.
 *
 * See node_modules/next/dist/docs/01-app/.../error.md (global-error section).
 */

import { useEffect } from "react"
import "./globals.css"
import { isDebugEnabled } from "@/lib/debug"
import { pushError } from "@/components/debug/store"
import { DebugConsole } from "@/components/debug/DebugConsole"

export default function GlobalError({
  error,
  unstable_retry,
}: {
  error: Error & { digest?: string }
  unstable_retry?: () => void
}) {
  useEffect(() => {
    pushError({
      kind: "react",
      message: error.message || error.name || "Root layout error",
      stack: error.stack,
      source: error.digest ? `digest:${error.digest}` : undefined,
    })
  }, [error])

  const debug = isDebugEnabled()

  return (
    <html lang="en">
      <body>
        <div
          role="alert"
          className="kt-panel"
          style={{
            margin: 16,
            padding: 20,
            borderColor: "var(--neg)",
            fontFamily: "var(--mono)",
            color: "var(--ink)",
          }}
        >
          <h2 style={{ fontSize: 18, color: "var(--neg)", marginBottom: 8 }}>
            The dashboard failed to load.
          </h2>
          <p className="text-mut" style={{ fontSize: 12, marginBottom: 12 }}>
            {debug
              ? "Captured below — use “Copy Errors” to grab the full stack."
              : "An unexpected error occurred. Try again, or reload the page."}
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              className="kt-btn primary"
              style={{ fontSize: 12 }}
              onClick={() => (unstable_retry ? unstable_retry() : window.location.reload())}
            >
              Try again
            </button>
            <button
              type="button"
              className="kt-btn"
              style={{ fontSize: 12 }}
              onClick={() => window.location.reload()}
            >
              Reload
            </button>
          </div>
        </div>
        <DebugConsole />
      </body>
    </html>
  )
}
