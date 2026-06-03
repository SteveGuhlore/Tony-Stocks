export const EM_DASH = "—"

export function formatPrice(n: number | null | undefined): string {
  return n == null ? EM_DASH : n.toFixed(2)
}

export function formatSignedPct(n: number | null | undefined): string {
  if (n == null) return EM_DASH
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`
}

export function plPercent(
  entry: number | null | undefined,
  price: number | null | undefined,
): number | null {
  if (entry == null || price == null) return null
  return ((price - entry) / entry) * 100
}

export function scanAgeLabel(seconds: number | null | undefined): string {
  if (seconds == null) return "no scan yet"
  if (seconds < 60) return "just now"
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`
  return `${Math.round(seconds / 3600)}h ago`
}
