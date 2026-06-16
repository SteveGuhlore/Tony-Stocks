"use client"

/**
 * App-root React error boundary. Class component because only class components
 * can catch render/lifecycle errors (componentDidCatch). On catch it feeds the
 * error into the shared store (so the ErrorConsole surfaces it identically to a
 * window error) and renders a fallback so a single bad render does not blank the
 * entire page.
 *
 * Debug detail is gated: only shown when the debug console is enabled. Public
 * visitors get a minimal neutral message and nothing is exfiltrated.
 */

import { Component, type ErrorInfo, type ReactNode } from "react"
import { isDebugEnabled } from "@/lib/debug"
import { pushError } from "./store"

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
  componentStack: string | null
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null, componentStack: null }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    this.setState({ componentStack: info.componentStack ?? null })
    pushError({
      kind: "react",
      message: error.message || error.name || "React render error",
      stack: (error.stack ?? "") + (info.componentStack ? `\n\nComponent stack:${info.componentStack}` : ""),
    })
  }

  private reset = () => this.setState({ error: null, componentStack: null })

  render() {
    if (!this.state.error) return this.props.children

    const debug = isDebugEnabled()

    return (
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
        <h3 style={{ fontSize: 16, color: "var(--neg)", marginBottom: 8 }}>
          Something broke while rendering this view.
        </h3>
        {debug ? (
          <p className="text-mut" style={{ fontSize: 12, marginBottom: 12 }}>
            Captured below in the error console — use “Copy Errors” to grab the full stack.
          </p>
        ) : (
          <p className="text-mut" style={{ fontSize: 12, marginBottom: 12 }}>
            The dashboard hit an unexpected error. Try reloading the page.
          </p>
        )}
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="kt-btn primary" style={{ fontSize: 12 }} onClick={this.reset}>
            Retry
          </button>
          <button
            type="button"
            className="kt-btn"
            style={{ fontSize: 12 }}
            onClick={() => typeof window !== "undefined" && window.location.reload()}
          >
            Reload
          </button>
        </div>
      </div>
    )
  }
}
