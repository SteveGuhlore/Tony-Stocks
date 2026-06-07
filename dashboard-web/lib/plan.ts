/**
 * Plan-rail geometry — ported from 09-enriched-row.html `rail()`.
 * Maps stop · entry · target · current onto a 0–100% track.
 */

export interface RailInput {
  stop: number | null
  entry: number | null
  target: number | null
  current: number | null
}

export interface RailGeometry {
  ok: boolean
  /** percent positions 0..100 */
  stopPct: number
  entryPct: number
  targetPct: number
  curPct: number
  /** entry→target gain zone */
  zoneLeftPct: number
  zoneRightPct: number // distance from right edge
  /** current marker is at/above entry */
  curAboveEntry: boolean
}

const EMPTY: RailGeometry = {
  ok: false,
  stopPct: 0,
  entryPct: 0,
  targetPct: 0,
  curPct: 0,
  zoneLeftPct: 0,
  zoneRightPct: 100,
  curAboveEntry: false,
}

export function computeRail(input: RailInput): RailGeometry {
  const { stop, entry, target, current } = input
  if (
    stop === null ||
    entry === null ||
    target === null ||
    [stop, entry, target].some((n) => Number.isNaN(n))
  ) {
    return EMPTY
  }
  const cur = current ?? entry
  const lo = Math.min(stop, cur) * 0.998
  const hi = Math.max(target, cur) * 1.002
  const span = hi - lo || 1
  const pct = (v: number) => ((v - lo) / span) * 100
  const entryPct = pct(entry)
  const targetPct = pct(target)
  return {
    ok: true,
    stopPct: pct(stop),
    entryPct,
    targetPct,
    curPct: pct(cur),
    zoneLeftPct: entryPct,
    zoneRightPct: 100 - targetPct,
    curAboveEntry: cur >= entry,
  }
}
