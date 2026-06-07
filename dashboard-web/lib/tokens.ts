/**
 * Kinetic Tape design tokens — single source of truth (ported from
 * .superpowers/brainstorm/.../08-kinetic-system.html).
 * Components must reference these / the CSS vars in globals.css — no ad-hoc hex.
 */

export const colors = {
  bg: "#0a0c0b",
  bg2: "#0f1311",
  panel: "#0f1311",
  ink: "#eaf2e9",
  mut: "#7e8a82",
  dim: "#586059",
  lime: "#c4f042", // accent / live score
  cyan: "#37e0ff", // bot / 1st pass
  amber: "#ff9e2c", // Tony / 2nd pass
  pos: "#46d39a", // gain / hit
  neg: "#ff5d73", // loss / stop
  warn: "#ffce4a", // near-entry
  line: "rgba(255,255,255,.08)",
} as const

export type ColorToken = keyof typeof colors

/** Sub-score keys in canonical T M V R S order. */
export const SUB_SCORE_KEYS = ["trend", "momentum", "volume", "risk", "setup"] as const
export type SubScoreKey = (typeof SUB_SCORE_KEYS)[number]

export const SUB_SCORE_LABELS: Record<SubScoreKey, string> = {
  trend: "Trend",
  momentum: "Momentum",
  volume: "Volume",
  risk: "Risk",
  setup: "Setup",
}

/** Compact T M V R S labels for the tape header. */
export const SUB_SCORE_SHORT = ["T", "M", "V", "R", "S"] as const

export const fonts = {
  display: "'Space Grotesk', sans-serif",
  mono: "'Space Mono', monospace",
} as const
