"use client"
import { useQuery } from "@tanstack/react-query"
import { api } from "@/lib/api"
import type { MorningPrepResponse } from "@/lib/types"

const EMPTY_MORNING_PREP: MorningPrepResponse = {
  generated_at: "",
  et_date: "",
  phase: "",
  shortlist: [],
  what_changed_overnight: "",
  plan_for_open: "",
}

/** Morning prep output from the off-hours engine. Fails quietly to EMPTY
 *  so the dashboard degrades cleanly when no report has been generated yet. */
export function useMorningPrep(): MorningPrepResponse {
  const { data } = useQuery({
    queryKey: ["morningPrep"],
    queryFn: api.morningPrep,
    retry: false,
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
  return data ?? EMPTY_MORNING_PREP
}
