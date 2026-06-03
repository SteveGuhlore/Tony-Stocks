export type Tone = "green" | "red" | "amber" | "azure" | "brass" | "muted"
export type StatusKind = "triggered" | "armed" | "watching" | "closed"
export type VerdictKind = "reaffirm" | "adjust" | "override" | "close"

const VERDICTS: Record<VerdictKind, { label: string; tone: Tone }> = {
  reaffirm: { label: "✓ reaffirm", tone: "green" },
  adjust: { label: "◐ adjust", tone: "amber" },
  override: { label: "⊘ override", tone: "red" },
  close: { label: "✕ close", tone: "red" },
}

export function verdictDisplay(verdict: string | null | undefined): { label: string; tone: Tone } {
  if (verdict && verdict in VERDICTS) return VERDICTS[verdict as VerdictKind]
  return { label: "⋯ awaiting", tone: "muted" }
}

export function statusKind(s: { entry_triggered: boolean; status: string | null }): StatusKind {
  if (s.status === "closed") return "closed"
  if (s.entry_triggered) return "triggered"
  return "watching"
}
