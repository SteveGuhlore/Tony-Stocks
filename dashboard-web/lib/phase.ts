/** Trading session phase — drives the top-bar morph (Prep / Live / Review). */
export type Phase = "prep" | "live" | "review"

/**
 * Derive the auto phase from a market descriptor + local clock.
 * Operator can still override manually in the UI.
 */
export function autoPhase(market: { is_open?: boolean; phase?: string } | undefined, now = new Date()): Phase {
  if (market?.phase === "prep" || market?.phase === "live" || market?.phase === "review") {
    return market.phase
  }
  if (market?.is_open) return "live"
  // ET hour heuristic when market metadata is absent
  const etHour = Number(
    new Intl.DateTimeFormat("en-US", {
      hour: "numeric",
      hour12: false,
      timeZone: "America/New_York",
    }).format(now),
  )
  if (etHour >= 4 && etHour < 9) return "prep"
  if (etHour >= 16 || etHour < 4) return "review"
  return "live"
}

export const PHASE_LABEL: Record<Phase, string> = {
  prep: "Prep",
  live: "Live",
  review: "Review",
}
