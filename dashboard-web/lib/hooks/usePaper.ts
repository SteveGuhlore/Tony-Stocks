"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { PaperEquityCurve, PaperResponse } from "@/lib/types"

const EMPTY_PAPER: PaperResponse = {
  enabled: false,
  disabled_reason: null,
  account_label: "Trading Bot",
  open: [],
  closed: [],
  summary: { open_count: 0, closed_count: 0, target_hits: 0, stop_hits: 0, realized_pl: 0, win_rate: null },
}

/** The bot's paper book (open/closed positions + summary). Fails quietly to EMPTY
 *  so the dashboard degrades cleanly when paper trading is off or the API is down. */
export function usePaper(): PaperResponse {
  const { data } = useQuery({
    queryKey: ["paper"],
    queryFn: api.paper,
    retry: false,
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
  return data ?? EMPTY_PAPER
}

const EMPTY_CURVE: PaperEquityCurve = {
  enabled: false,
  label: "bot",
  base_equity: 100_000,
  return_pct: 0,
  points: [],
  research_only: true,
}

/** The bot's realized paper-equity series, indexed to 100, for the head-to-head overlay. */
export function usePaperEquityCurve(): PaperEquityCurve {
  const { data } = useQuery({
    queryKey: ["paperEquity"],
    queryFn: () => api.paperEquityCurve(),
    retry: false,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  return data ?? EMPTY_CURVE
}
