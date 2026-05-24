"use client"
import { useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { api } from "@/lib/api"
import type { LiveQuote } from "@/lib/types"

function usePageVisible(): boolean {
  const [visible, setVisible] = useState(true)
  useEffect(() => {
    const handler = () => setVisible(document.visibilityState === "visible")
    document.addEventListener("visibilitychange", handler)
    return () => document.removeEventListener("visibilitychange", handler)
  }, [])
  return visible
}

export function useLivePrices(): Record<string, LiveQuote> {
  const visible = usePageVisible()
  const { data } = useQuery({
    queryKey: ["live-prices"],
    queryFn: () => api.prices(),
    refetchInterval: visible ? 15_000 : 120_000,
    staleTime: 10_000,
  })
  if (!data) return {}
  return Object.fromEntries(data.symbols.map((q) => [q.symbol, q]))
}
