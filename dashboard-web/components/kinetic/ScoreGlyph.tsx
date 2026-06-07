"use client"

import { fmtScore } from "@/lib/format"
import { subScoreArray } from "@/lib/rows"
import type { SubScores } from "@/lib/types"
import { SUB_SCORE_LABELS, SUB_SCORE_KEYS } from "@/lib/tokens"

/**
 * Score glyph — big number + 5 glowing sub-bars (T M V R S), ported from
 * 08-kinetic-system.html §04. Risk bar dims (warn color) when weak.
 * Bars rise on render (staggered), CSS-only so it is cheap across many rows.
 */
export function ScoreGlyph({
  score,
  sub,
  size = "md",
  animate = true,
}: {
  score: number | null
  sub: SubScores | null
  size?: "sm" | "md"
  animate?: boolean
}) {
  const vals = subScoreArray(sub)
  const maxH = size === "sm" ? 18 : 24
  const numSize = size === "sm" ? 15 : 20
  const label = `Score ${fmtScore(score)} of 100. Sub-scores: ` +
    SUB_SCORE_KEYS.map((k, i) => `${SUB_SCORE_LABELS[k]} ${vals[i]}`).join(", ")
  return (
    <span className="inline-flex items-center gap-[9px]" role="img" aria-label={label}>
      <span
        className="font-display font-bold text-lime"
        style={{ fontSize: numSize, lineHeight: 1 }}
      >
        {fmtScore(score)}
      </span>
      <span className="kt-bars" style={{ height: maxH }} aria-hidden>
        {vals.map((v, i) => {
          const h = Math.max(2, Math.round((Math.min(100, Math.max(0, v)) / 100) * maxH))
          const weak = SUB_SCORE_KEYS[i] === "risk" && v < 50
          return (
            <i
              key={i}
              style={{
                height: h,
                background: weak ? "var(--warn)" : "var(--cyan)",
                boxShadow: weak
                  ? "0 0 6px rgba(255,206,74,.55)"
                  : "0 0 6px rgba(55,224,255,.6)",
                animationDelay: animate ? `${i * 60}ms` : "0ms",
                animation: animate ? undefined : "none",
              }}
            />
          )
        })}
      </span>
    </span>
  )
}
