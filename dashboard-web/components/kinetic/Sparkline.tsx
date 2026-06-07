"use client"

import { sparklinePoints } from "@/lib/sparkline"

/** Intraday sparkline — glowing line, green up / red down (ported from 09). */
export function Sparkline({
  data,
  width = 64,
  height = 22,
}: {
  data: number[] | null | undefined
  width?: number
  height?: number
}) {
  const { points, up, empty } = sparklinePoints(data, width, height)
  if (empty) {
    return (
      <svg width={width} height={height} aria-hidden>
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="var(--dim)"
          strokeDasharray="2 3"
          strokeWidth={1}
        />
      </svg>
    )
  }
  return (
    <svg className="kt-spark" width={width} height={height} aria-hidden>
      <polyline
        fill="none"
        stroke={up ? "var(--pos)" : "var(--neg)"}
        strokeWidth={1.5}
        points={points}
      />
    </svg>
  )
}
