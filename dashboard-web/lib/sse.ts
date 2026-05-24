"use client"
import { useEffect, useRef, useCallback } from "react"
import type { SSEHeartbeat, SSEEvent } from "./types"

type SSEMessage = SSEHeartbeat | SSEEvent | { type: "error"; message: string }

export function useSSE(url: string, onMessage: (msg: SSEMessage) => void) {
  const onMessageRef = useRef(onMessage)
  onMessageRef.current = onMessage

  useEffect(() => {
    let es: EventSource
    let retryTimeout: ReturnType<typeof setTimeout>

    function connect() {
      es = new EventSource(url)
      es.onmessage = (e) => {
        try { onMessageRef.current(JSON.parse(e.data)) } catch {}
      }
      es.onerror = () => {
        es.close()
        retryTimeout = setTimeout(connect, 5000)
      }
    }

    connect()
    return () => { es?.close(); clearTimeout(retryTimeout) }
  }, [url])
}
