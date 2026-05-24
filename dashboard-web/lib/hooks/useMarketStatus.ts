"use client"
import { useQuery } from "@tanstack/react-query"
import type { MarketStatus } from "@/lib/types"
import { api } from "@/lib/api"

export function useMarketStatus(): MarketStatus | null {
  const { data } = useQuery({
    queryKey: ["market-status"],
    queryFn: async () => {
      const r = await api.prices()
      return r.market
    },
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  return data ?? null
}
