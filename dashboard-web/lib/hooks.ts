"use client"

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { api, type ControlBody, type ControlResult } from "./api"

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

/* ── personalize reads ─────────────────────────────────────────────────────── */

export function usePins() {
  return useQuery({ queryKey: ["pins"], queryFn: api.personalize.pins })
}

export function useNotes(symbol: string | null) {
  return useQuery({
    queryKey: ["notes", symbol],
    queryFn: () => api.personalize.notes(symbol as string),
    enabled: !!symbol,
  })
}

/* ── mutations ─────────────────────────────────────────────────────────────── */

const errMsg = (e: unknown) => (e instanceof Error && e.message ? e.message : "request failed")

/** Control mutation factory — success/error toasts + invalidate the read models. */
function useControlMutation<B extends ControlBody>(
  mutationFn: (body: B) => Promise<ControlResult>,
  successMsg: string,
) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => {
      toast.success(successMsg)
      for (const key of ["paper", "cockpit", "system-health", "paper-equity"]) {
        qc.invalidateQueries({ queryKey: [key] })
      }
    },
    onError: (e) => toast.error(errMsg(e)),
  })
}

export function useStopWatch() {
  return useControlMutation(api.control.stopWatch, "Watch loop stop requested")
}

export function usePausePaper() {
  return useControlMutation(api.control.pausePaper, "Paper trading paused")
}

export function useResumePaper() {
  return useControlMutation(api.control.resumePaper, "Paper trading resumed")
}

export function useFlattenAll() {
  return useControlMutation(api.control.flattenAll, "Flatten-all requested")
}

export function useFlattenOne() {
  return useControlMutation(api.control.flattenOne, "Flatten requested")
}

export function useTriggerScan() {
  return useControlMutation(api.control.triggerScan, "Manual scan triggered")
}

export function useAckAlert() {
  return useControlMutation(api.control.ackAlert, "Alert acknowledged")
}

export function useSetPin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.personalize.setPin,
    onSuccess: (res) => {
      toast.success(res.pinned ? `Pinned ${res.symbol}` : `Unpinned ${res.symbol}`)
      qc.invalidateQueries({ queryKey: ["pins"] })
    },
    onError: (e) => toast.error(errMsg(e)),
  })
}

export function useAddNote() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.personalize.addNote,
    onSuccess: (_res, vars) => {
      toast.success(`Note saved on ${vars.symbol}`)
      qc.invalidateQueries({ queryKey: ["notes"] })
    },
    onError: (e) => toast.error(errMsg(e)),
  })
}

export function useAddPriceAlert() {
  return useMutation({
    mutationFn: api.personalize.addPriceAlert,
    onSuccess: (_res, vars) =>
      toast.success(`Alert set — ${vars.symbol} ${vars.direction} ${vars.target_price}`),
    onError: (e) => toast.error(errMsg(e)),
  })
}
