"use client"

/**
 * In-app JavaScript error console. Mounted once at the app root behind the
 * debug gate (see lib/debug.ts). It registers window "error" and
 * "unhandledrejection" listeners and renders captured errors — plus any React
 * render errors fed in by ErrorBoundary — in a fixed, copyable crash panel so
 * the production dashboard surfaces failures instead of going blank.
 *
 * Deliberately plain React (no motion/* or app data hooks): this is the safety
 * net, so it must not depend on the layers that might be crashing.
 */

import { useCallback, useEffect, useState } from "react"
import { escapeHtml, fmtTime, formatErrorsAsText } from "@/lib/debug"
import { clearErrors, describeThrown, getErrors, pushError, subscribe, type CapturedError } from "./store"

function kindColor(kind: CapturedError["kind"]): string {
  switch (kind) {
    case "react":
      return "var(--amber)"
    case "unhandledrejection":
      return "var(--warn)"
    default:
      return "var(--neg)"
  }
}

export function ErrorConsole() {
  const [errors, setErrors] = useState<CapturedError[]>(() => getErrors())
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  // Subscribe to the shared store. Seed once in case errors were captured
  // (e.g. by the boundary) before this component mounted.
  useEffect(() => {
    setErrors(getErrors())
    return subscribe((next) => {
      setErrors(next)
      // Auto-open on the first captured error so a blank page never hides it.
      if (next.length > 0) setOpen(true)
    })
  }, [])

  // Window-level capture: runtime errors and unhandled promise rejections.
  useEffect(() => {
    const onError = (ev: ErrorEvent) => {
      pushError({
        kind: "error",
        message: ev.message || (ev.error instanceof Error ? ev.error.message : "Unknown error"),
        source: ev.filename || undefined,
        line: ev.lineno || undefined,
        column: ev.colno || undefined,
        stack: ev.error instanceof Error ? ev.error.stack : undefined,
      })
    }
    const onRejection = (ev: PromiseRejectionEvent) => {
      pushError(describeThrown(ev.reason, "unhandledrejection"))
    }
    window.addEventListener("error", onError)
    window.addEventListener("unhandledrejection", onRejection)
    return () => {
      window.removeEventListener("error", onError)
      window.removeEventListener("unhandledrejection", onRejection)
    }
  }, [])

  // Escape closes the panel (it stays mounted; reopens on the next error).
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [open])

  const copy = useCallback(async () => {
    const text = formatErrorsAsText(getErrors())
    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text)
      } else {
        // Fallback for non-secure contexts where the Clipboard API is absent.
        const ta = document.createElement("textarea")
        ta.value = text
        ta.style.position = "fixed"
        ta.style.opacity = "0"
        document.body.appendChild(ta)
        ta.select()
        document.execCommand("copy")
        document.body.removeChild(ta)
      }
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1400)
    } catch {
      setCopied(false)
    }
  }, [])

  const count = errors.length

  // Closed with no errors: show nothing at all (gate already passed).
  if (!open && count === 0) return null

  // Closed but errors exist: a small re-open tab so it's never truly hidden.
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={`Open error console (${count} error${count === 1 ? "" : "s"})`}
        style={{
          position: "fixed",
          right: 14,
          bottom: 14,
          zIndex: 2147483000,
          fontFamily: "var(--mono)",
          fontSize: 11,
          padding: "7px 12px",
          borderRadius: 9,
          border: "1px solid var(--neg)",
          background: "rgba(255,93,115,.14)",
          color: "var(--neg)",
          cursor: "pointer",
        }}
      >
        ⚠ {count} error{count === 1 ? "" : "s"}
      </button>
    )
  }

  return (
    <div
      role="dialog"
      aria-label="JavaScript error console"
      style={{
        position: "fixed",
        right: 14,
        bottom: 14,
        zIndex: 2147483000,
        width: 560,
        maxWidth: "calc(100vw - 28px)",
        maxHeight: "min(70vh, 560px)",
        display: "flex",
        flexDirection: "column",
        background: "var(--panel)",
        border: "1px solid var(--neg)",
        borderRadius: 12,
        boxShadow: "0 24px 70px rgba(0,0,0,.7)",
        fontFamily: "var(--mono)",
        color: "var(--ink)",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "10px 12px",
          borderBottom: "1px solid var(--line)",
        }}
      >
        <strong style={{ fontFamily: "var(--mono)", fontSize: 12, color: "var(--neg)" }}>
          ⚠ Error console
        </strong>
        <span className="text-mut" style={{ fontSize: 11 }}>
          {count} captured
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 6 }}>
          <button type="button" className="kt-btn" style={btnSm} onClick={copy} disabled={count === 0}>
            {copied ? "Copied ✓" : "Copy Errors"}
          </button>
          <button type="button" className="kt-btn" style={btnSm} onClick={() => clearErrors()}>
            Clear
          </button>
          <button
            type="button"
            className="kt-btn"
            style={btnSm}
            onClick={() => setOpen(false)}
            aria-label="Close error console"
          >
            Close
          </button>
        </div>
      </header>

      <div style={{ overflow: "auto", padding: "8px 10px" }}>
        {count === 0 ? (
          <div className="text-dim" style={{ fontSize: 12, padding: "10px 4px" }}>
            No errors captured yet. This panel will pop open automatically when the page throws.
          </div>
        ) : (
          errors.map((e) => (
            <article
              key={e.id}
              style={{
                borderBottom: "1px solid var(--line)",
                padding: "8px 4px",
              }}
            >
              <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
                <span
                  style={{
                    fontSize: 9,
                    textTransform: "uppercase",
                    letterSpacing: ".06em",
                    color: kindColor(e.kind),
                    border: `1px solid ${kindColor(e.kind)}`,
                    borderRadius: 4,
                    padding: "1px 5px",
                    flex: "0 0 auto",
                  }}
                >
                  {e.kind}
                </span>
                <span className="text-dim" style={{ fontSize: 10, flex: "0 0 auto" }}>
                  {fmtTime(e.time)}
                </span>
              </div>
              <div
                style={{ fontSize: 12, marginTop: 5, color: "var(--ink)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}
                dangerouslySetInnerHTML={{ __html: escapeHtml(e.message) }}
              />
              {(e.source || e.line != null) && (
                <div
                  className="text-mut"
                  style={{ fontSize: 10, marginTop: 3 }}
                  dangerouslySetInnerHTML={{
                    __html: `at ${escapeHtml(e.source ?? "&lt;unknown&gt;")}:${escapeHtml(
                      e.line ?? "?",
                    )}:${escapeHtml(e.column ?? "?")}`,
                  }}
                />
              )}
              {e.stack && (
                <pre
                  style={{
                    fontSize: 10,
                    lineHeight: 1.45,
                    marginTop: 6,
                    padding: "6px 8px",
                    background: "rgba(255,255,255,.03)",
                    border: "1px solid var(--line)",
                    borderRadius: 6,
                    color: "var(--mut)",
                    overflowX: "auto",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                  }}
                  dangerouslySetInnerHTML={{ __html: escapeHtml(e.stack) }}
                />
              )}
            </article>
          ))
        )}
      </div>
    </div>
  )
}

const btnSm: React.CSSProperties = {
  fontSize: 11,
  padding: "5px 10px",
  borderRadius: 7,
}
