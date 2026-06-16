/**
 * Debug-console plumbing — pure, framework-free helpers so they stay
 * unit-testable and usable from both the capture engine and the error
 * boundary. The UI lives in components/debug/.
 *
 * Gate: the in-app error console is OFF for normal/public visitors. It turns
 * on only when `?debug=1` (or `#debug`) is in the URL, or once the persisted
 * flag `localStorage.tonyDebug === "1"` is set. Visiting `?debug=1` persists
 * the flag so it survives client navigation.
 */

export const DEBUG_STORAGE_KEY = "tonyDebug"

export type ErrorKind = "error" | "unhandledrejection" | "react"

export interface CapturedError {
  id: number
  kind: ErrorKind
  message: string
  source?: string
  line?: number
  column?: number
  stack?: string
  /** epoch millis */
  time: number
}

/** Escape the five HTML-significant characters so error text is XSS-safe. */
export function escapeHtml(input: unknown): string {
  return String(input ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
}

/** ISO-ish wall-clock stamp (HH:MM:SS.mmm) for compact log lines. */
export function fmtTime(ms: number): string {
  const d = new Date(ms)
  const pad = (n: number, w = 2) => String(n).padStart(w, "0")
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${pad(
    d.getMilliseconds(),
    3,
  )}`
}

/** One captured error rendered as plain text (used by "Copy Errors"). */
export function formatErrorAsText(e: CapturedError): string {
  const head = `[${fmtTime(e.time)}] ${e.kind.toUpperCase()}: ${e.message}`
  const loc =
    e.source || e.line != null || e.column != null
      ? `\n  at ${e.source ?? "<unknown>"}:${e.line ?? "?"}:${e.column ?? "?"}`
      : ""
  const stack = e.stack ? `\n${e.stack}` : ""
  return head + loc + stack
}

/** All captured errors as one copy-pasteable plain-text block. */
export function formatErrorsAsText(errors: CapturedError[]): string {
  if (errors.length === 0) return "(no errors captured)"
  const header = `Tony dashboard — ${errors.length} captured error${
    errors.length === 1 ? "" : "s"
  }\n${typeof location !== "undefined" ? location.href : ""}\n`
  return header + "\n" + errors.map(formatErrorAsText).join("\n\n")
}

/**
 * Resolve whether the debug console should be active for this visitor.
 * Reads (and, for `?debug=1`/`#debug`, persists) the gate. Safe to call on the
 * server — returns false when there is no `window`.
 */
export function isDebugEnabled(): boolean {
  if (typeof window === "undefined") return false
  try {
    const url = new URL(window.location.href)
    const wantsOn =
      url.searchParams.get("debug") === "1" || /(^|[#&])debug(=1)?($|&)/.test(url.hash)
    if (wantsOn) {
      try {
        window.localStorage.setItem(DEBUG_STORAGE_KEY, "1")
      } catch {
        // private mode / disabled storage — URL flag still enables this session
      }
      return true
    }
    if (url.searchParams.get("debug") === "0") {
      try {
        window.localStorage.removeItem(DEBUG_STORAGE_KEY)
      } catch {
        // ignore
      }
      return false
    }
    try {
      return window.localStorage.getItem(DEBUG_STORAGE_KEY) === "1"
    } catch {
      return false
    }
  } catch {
    return false
  }
}
