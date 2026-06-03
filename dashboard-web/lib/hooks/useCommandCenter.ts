"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { CommandCenterResponse } from "@/lib/types"

const EMPTY: CommandCenterResponse = { picks: {}, record: null, agreement: null }

/**
 * Second-layer (Tony Stocks / Command Center) data. Resilient by design: until the
 * `/api/command-center` endpoint exists the query fails quietly and this returns EMPTY,
 * so every consumer degrades to "⋯ awaiting" without errors. See docs/CONTRACTS/command-center-bridge.md.
 */
export function useCommandCenter(): CommandCenterResponse {
  const { data } = useQuery({
    queryKey: ["commandCenter"],
    queryFn: api.commandCenter,
    retry: false,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  return data ?? EMPTY
}
