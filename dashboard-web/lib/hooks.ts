"use client"

import { useQuery } from "@tanstack/react-query"
import { api } from "./api"

/** PRIMARY hook — every read view derives from /api/cockpit. */
export function useCockpit() {
  return useQuery({ queryKey: ["cockpit"], queryFn: api.cockpit })
}

export function useCommandCenter() {
  return useQuery({ queryKey: ["command-center"], queryFn: api.commandCenter })
}

export function useAnalytics() {
  return useQuery({ queryKey: ["analytics"], queryFn: api.analytics })
}

export function useScanSkipReasons() {
  return useQuery({ queryKey: ["scan-skip-reasons"], queryFn: api.scanSkipReasons })
}

export function usePaper() {
  return useQuery({ queryKey: ["paper"], queryFn: api.paper })
}

export function usePaperEquityCurve(baseEquity?: number) {
  return useQuery({
    queryKey: ["paper-equity", baseEquity ?? null],
    queryFn: () => api.paperEquityCurve(baseEquity),
  })
}

export function useEquityCompare(period?: string, timeframe?: string) {
  return useQuery({
    queryKey: ["equity-compare", period ?? null, timeframe ?? null],
    queryFn: () => api.equityCompare(period, timeframe),
  })
}

export function useSymbolChart(symbol: string | null, timeframe?: string) {
  return useQuery({
    queryKey: ["chart", symbol, timeframe ?? null],
    queryFn: () => api.symbolChart(symbol as string, timeframe),
    enabled: !!symbol,
    refetchInterval: 30000,
  })
}

export function useMorningPrep() {
  return useQuery({ queryKey: ["morning-prep"], queryFn: api.morningPrep })
}

export function useSystemHealth() {
  return useQuery({ queryKey: ["system-health"], queryFn: api.systemHealth })
}
