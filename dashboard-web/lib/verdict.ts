/**
 * THE single verdict display helper (Codex-mandated).
 * Transport keeps `verdict` as a raw string; unknown / "pass" / "" all degrade
 * gracefully to "awaiting" — never error, never render a raw unknown token.
 */

export type VerdictKind = "reaff" | "over" | "awaiting"

export interface VerdictDisplay {
  kind: VerdictKind
  label: string
  /** css class suffix used by .kt-pill (reaff | over | awaiting) */
  className: VerdictKind
}

const REAFFIRM = new Set([
  "reaffirm",
  "reaff",
  "confirm",
  "confirmed",
  "agree",
  "buy",
  "long",
  "approve",
  "approved",
  "↑ reaffirm",
])
const OVERRIDE = new Set([
  "override",
  "overridden",
  "reject",
  "rejected",
  "avoid",
  "fade",
  "downgrade",
  "veto",
  "⤳ override",
])

/**
 * Normalize any transport verdict string to a display descriptor.
 * `pass`, ``, null/undefined, and anything unrecognized → "awaiting".
 */
export function normalizeVerdict(raw: string | null | undefined): VerdictDisplay {
  const v = (raw ?? "").trim().toLowerCase()
  if (REAFFIRM.has(v)) return { kind: "reaff", label: "↑ reaffirm", className: "reaff" }
  if (OVERRIDE.has(v)) return { kind: "over", label: "⤳ override", className: "over" }
  // "pass", "", "awaiting", "pending", unknown → awaiting
  return { kind: "awaiting", label: "⋯ awaiting", className: "awaiting" }
}
