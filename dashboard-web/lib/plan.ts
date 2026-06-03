export interface PlanLevels {
  stop: number | null | undefined
  entry: number | null | undefined
  target: number | null | undefined
}

/**
 * Map a price to its 0–100 position on the Rail, which runs stop (0) → target (100).
 * Clamped to [0,100]. Returns null if any level, the price, or a non-degenerate span is unavailable.
 */
export function railPositionPct(
  price: number | null | undefined,
  { stop, target }: PlanLevels,
): number | null {
  if (price == null || stop == null || target == null) return null
  const lo = Math.min(stop, target)
  const hi = Math.max(stop, target)
  if (hi - lo === 0) return null
  const pct = ((price - lo) / (hi - lo)) * 100
  return Math.max(0, Math.min(100, pct))
}
