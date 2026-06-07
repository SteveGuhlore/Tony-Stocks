"use client"

import { useEffect, useRef, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { api } from "./api"
import type { StreamEvent } from "./types"

export type StreamState = "connecting" | "open" | "reconnecting" | "closed"

/**
 * SSE hook — best-effort live signal layered over polling (the source of truth).
 * On open / reconnect we rehydrate by invalidating the cockpit + related queries
 * (a GET re-fetch), so we never trust the stream alone. Reconnect uses capped
 * exponential backoff. Disabled entirely if EventSource is unavailable.
 */
export function useEventStream(onEvent?: (e: StreamEvent) => void) {
  const qc = useQueryClient()
  const [state, setState] = useState<StreamState>("connecting")
  const [lastEvent, setLastEvent] = useState<StreamEvent | null>(null)
  const esRef = useRef<EventSource | null>(null)
  const attemptRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  useEffect(() => {
    if (typeof window === "undefined" || typeof EventSource === "undefined") {
      setState("closed")
      return
    }

    let cancelled = false

    const rehydrate = () => {
      // polling is truth — force a GET refresh of the read models
      qc.invalidateQueries({ queryKey: ["cockpit"] })
      qc.invalidateQueries({ queryKey: ["paper"] })
      qc.invalidateQueries({ queryKey: ["system-health"] })
    }

    const connect = () => {
      if (cancelled) return
      setState(attemptRef.current === 0 ? "connecting" : "reconnecting")
      const es = new EventSource(api.streamUrl())
      esRef.current = es

      es.onopen = () => {
        if (cancelled) return
        attemptRef.current = 0
        setState("open")
        rehydrate()
      }

      es.onmessage = (msg) => {
        if (cancelled) return
        let parsed: StreamEvent
        try {
          parsed = JSON.parse(msg.data) as StreamEvent
        } catch {
          parsed = { type: "raw", message: String(msg.data) }
        }
        setLastEvent(parsed)
        onEventRef.current?.(parsed)
        // any push is a hint to re-poll the relevant read model
        qc.invalidateQueries({ queryKey: ["cockpit"] })
      }

      es.onerror = () => {
        es.close()
        if (cancelled) return
        setState("reconnecting")
        attemptRef.current += 1
        const delay = Math.min(1000 * 2 ** Math.min(attemptRef.current, 5), 30000)
        timerRef.current = setTimeout(connect, delay)
      }
    }

    connect()

    return () => {
      cancelled = true
      if (timerRef.current) clearTimeout(timerRef.current)
      esRef.current?.close()
      setState("closed")
    }
  }, [qc])

  return { state, lastEvent }
}
