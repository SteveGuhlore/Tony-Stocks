import type { CockpitRow, SubScores } from "./types"
import { SUB_SCORE_KEYS } from "./tokens"

/** Status badge text for a row (NEAR · 0.3% / TRIGGERED / watching). */
export function statusBadge(row: CockpitRow): { kind: CockpitRow["status"]; label: string } {
  if (row.status === "triggered" || row.entry_triggered) {
    return { kind: "triggered", label: "TRIGGERED" }
  }
  if (row.status === "near") {
    const d = row.distance_to_entry_pct
    return { kind: "near", label: d != null ? `NEAR · ${Math.abs(d).toFixed(1)}%` : "NEAR" }
  }
  return { kind: "watching", label: "watching" }
}

/** Ordered [trend, momentum, volume, risk, setup] with nulls → 0. */
export function subScoreArray(sub: SubScores | null | undefined): number[] {
  if (!sub) return [0, 0, 0, 0, 0]
  return SUB_SCORE_KEYS.map((k) => sub[k] ?? 0)
}

/** Effective display price prefers live current_price, then last_price, then close. */
export function effectivePrice(row: CockpitRow): number | null {
  return row.current_price ?? row.last_price ?? row.close ?? null
}

/** Agreement: do bot and Tony point the same way? (best-effort, awaiting-safe) */
export function scoreDelta(row: CockpitRow): number | null {
  if (row.score == null || row.tony?.score == null) return null
  return Math.round(row.score - row.tony.score)
}
