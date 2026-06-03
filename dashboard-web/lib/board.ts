import type { StatusKind } from "./signal"

// Terminal outcome labels from the backend (src/trading_bot/api/routes/outcomes.py).
const CLOSED_OUTCOMES = new Set([
  "target_hit",
  "target_before_stop",
  "stop_hit",
  "stop_before_target",
  "failed_setup",
])

export function isClosedOutcome(outcomeLabel: string | null | undefined): boolean {
  return outcomeLabel != null && CLOSED_OUTCOMES.has(outcomeLabel)
}

/** True when live price sits within `thresholdPct` percent of the planned entry. */
export function nearEntry(
  entry: number | null | undefined,
  price: number | null | undefined,
  thresholdPct = 0.75,
): boolean {
  if (entry == null || price == null || entry === 0) return false
  return Math.abs((price - entry) / entry) * 100 <= thresholdPct
}

export interface BoardSnapshotLike {
  entry_triggered: boolean
  outcome_label: string | null
  entry: number | null
}

/**
 * Derive the Board's display status for a tracked snapshot, layering live price on top
 * of snapshot fields: closed > triggered > armed (near entry) > watching.
 */
export function boardStatus(
  snap: BoardSnapshotLike,
  price: number | null | undefined,
): StatusKind {
  if (isClosedOutcome(snap.outcome_label)) return "closed"
  if (snap.entry_triggered) return "triggered"
  if (nearEntry(snap.entry, price)) return "armed"
  return "watching"
}

export const STATUS_DISPLAY: Record<StatusKind, { label: string; tone: string }> = {
  triggered: { label: "▲ triggered", tone: "green" },
  armed: { label: "◉ armed", tone: "brass" },
  watching: { label: "○ watching", tone: "muted" },
  closed: { label: "✕ closed", tone: "red" },
}
