export interface Bar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

/**
 * Price bounds for a chart: spans the bars' highs/lows plus any plan levels,
 * with a small padding so nothing sits flush against an edge. Returns null if empty.
 */
export function priceBounds(
  bars: Bar[],
  levels: (number | null | undefined)[] = [],
  padPct = 0.04,
): { min: number; max: number } | null {
  const lows = bars.map((b) => b.low)
  const highs = bars.map((b) => b.high)
  const extra = levels.filter((v): v is number => v != null)
  const all = [...lows, ...highs, ...extra]
  if (all.length === 0) return null
  let min = Math.min(...all)
  let max = Math.max(...all)
  if (min === max) {
    // degenerate: give it a tiny symmetric band so scaleY stays finite
    const pad = Math.abs(min) * padPct || 1
    return { min: min - pad, max: max + pad }
  }
  const pad = (max - min) * padPct
  min -= pad
  max += pad
  return { min, max }
}

/** Map a price to a Y pixel (0 = top). Higher price → smaller Y. */
export function scaleY(value: number, min: number, max: number, height: number): number {
  if (max === min) return height / 2
  return ((max - value) / (max - min)) * height
}

/** Evenly spaced, rounded tick values across [min, max] inclusive. */
export function priceTicks(min: number, max: number, count = 4): number[] {
  if (count < 2 || max <= min) return [min]
  const step = (max - min) / (count - 1)
  return Array.from({ length: count }, (_, i) => min + step * i)
}
