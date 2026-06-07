import type { PriceStatus } from "./types"

/** Format a price; null/undefined → em-dash. */
export function fmtPrice(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  return v.toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

/** Signed percent, e.g. +2.1% / -1.0%. null → em-dash. */
export function fmtPct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(digits)}%`
}

/** Whole-dollar money, signed when requested. */
export function fmtMoney(v: number | null | undefined, signed = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  const sign = signed && v > 0 ? "+" : v < 0 ? "-" : ""
  return `${sign}$${Math.abs(v).toLocaleString("en-US", { maximumFractionDigits: 0 })}`
}

export function fmtScore(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  return String(Math.round(v))
}

export function fmtRvol(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  return `${v.toFixed(1)}×`
}

export function changeClass(v: number | null | undefined): "pos" | "neg" | "mut" {
  if (v === null || v === undefined || Number.isNaN(v)) return "mut"
  return v >= 0 ? "pos" : "neg"
}

/** A label + whether the quote should be trusted as fresh. */
export interface PriceStatusDisplay {
  label: string
  fresh: boolean
  tone: "pos" | "warn" | "neg" | "mut"
}

export function priceStatusDisplay(status: PriceStatus | null | undefined): PriceStatusDisplay {
  switch (status) {
    case "live":
      return { label: "live", fresh: true, tone: "pos" }
    case "delayed":
      return { label: "delayed", fresh: true, tone: "warn" }
    case "stale":
      return { label: "stale", fresh: false, tone: "warn" }
    case "unavailable":
      return { label: "no quote", fresh: false, tone: "mut" }
    default:
      return { label: "—", fresh: false, tone: "mut" }
  }
}
