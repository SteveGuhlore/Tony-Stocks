/** Build an SVG polyline points string for a sparkline (ported from 09 `spark()`). */
export function sparklinePoints(
  pts: number[] | null | undefined,
  w = 64,
  h = 22,
): { points: string; up: boolean; empty: boolean } {
  if (!pts || pts.length < 2) return { points: "", up: true, empty: true }
  const max = Math.max(...pts)
  const min = Math.min(...pts)
  const rg = max - min || 1
  const points = pts
    .map((p, i) => {
      const x = (i / (pts.length - 1)) * w
      const y = h - ((p - min) / rg) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(" ")
  const up = pts[pts.length - 1] >= pts[0]
  return { points, up, empty: false }
}
