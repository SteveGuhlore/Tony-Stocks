/**
 * API contract types for the Kinetic Tape dashboard.
 * Backend: http://localhost:8001, base /api.
 *
 * RESILIENCE: transport `verdict` is kept as a raw STRING here and normalized in
 * exactly one display helper (lib/verdict.ts). Every quote-dependent view honors
 * `price_status`. Fields are nullable/awaiting-safe by design.
 */

export type RowStatus = "watching" | "near" | "triggered"
export type PriceStatus = "live" | "delayed" | "stale" | "unavailable"
export type ChartStatus = "ok" | "stale" | "unavailable"

export interface SubScores {
  trend: number | null
  momentum: number | null
  volume: number | null
  risk: number | null
  setup: number | null
}

/** Tony (2nd-pass) read. `verdict` is a raw string — normalize before display. */
export interface TonyRead {
  score: number | null
  verdict: string
  reasoning: string | null
  returned_at: string | null
}

export interface CockpitRow {
  symbol: string
  name: string | null
  sector: string | null
  universe_role: string | null
  setup_category: string | null
  score: number | null
  sub_scores: SubScores | null
  close: number | null
  entry: number | null
  stop: number | null
  target: number | null
  rr: number | null
  trade_plan_valid: boolean
  last_price: number | null
  day_change_pct: number | null
  price_status: PriceStatus
  rvol: number | null
  sparkline: number[] | null
  status: RowStatus
  entry_triggered: boolean
  distance_to_entry_pct: number | null
  current_price: number | null
  research_unrealized_pl_pct: number | null
  reassessment_label: string | null
  time_active_minutes: number | null
  original_entry: number | null
  original_stop: number | null
  original_target: number | null
  tony: TonyRead | null
}

export interface CockpitCounts {
  total: number
  near: number
  triggered: number
  watching: number
}

export interface CockpitMarket {
  phase?: string
  is_open?: boolean
  clock_et?: string
  session_label?: string
}

export interface CockpitResponse {
  generated_at: string
  market: CockpitMarket
  counts: CockpitCounts
  rows: CockpitRow[]
}

/* ---- chart ---- */
export interface ChartBar {
  t: number | string
  o: number
  h: number
  l: number
  c: number
  v: number
}
export interface ChartPlan {
  entry: number | null
  stop: number | null
  target: number | null
}
export interface ChartResponse {
  symbol: string
  timeframe: string
  status: ChartStatus
  bars: ChartBar[]
  plan: ChartPlan
}

/* ---- paper ---- */
export interface PaperPosition {
  symbol: string
  qty: number
  avg_entry_price: number | null
  fill_price?: number | null
  last_price: number | null
  unrealized_pl: number | null
  unrealized_pl_pct: number | null
  protection_status: string | null
  stop?: number | null
  target?: number | null
  opened_at?: string | null
}
export interface PaperResponse {
  status?: string
  equity: number | null
  cash?: number | null
  open_pl: number | null
  realized_pl: number | null
  positions: PaperPosition[]
}
export interface EquityPoint {
  t: number | string
  equity: number
}
export interface PaperEquityCurve {
  points: EquityPoint[]
  base_equity?: number | null
}

/* ---- command center / agreement ---- */
export interface AgreementStats {
  agreed_right: number
  agreed_wrong: number
  tony_saved: number
  tony_missed: number
}
export interface CommandCenterResponse {
  generated_at?: string
  bot_win_rate?: number | null
  tony_win_rate?: number | null
  bot_avg_r?: number | null
  tony_avg_r?: number | null
  bot_return_pct?: number | null
  tony_return_pct?: number | null
  agreement?: AgreementStats | null
  equity_bot?: EquityPoint[]
  equity_tony?: EquityPoint[]
  by_setup?: { setup: string; trades: number; win_pct: number; avg_r: number }[]
  weights?: Record<string, number> | null
  proposed_weights?: Record<string, number> | null
  rows?: Record<string, TonyRead> | null
}

/* ---- morning prep ---- */
export interface PrepRow {
  symbol: string
  conviction?: string | null
  score: number | null
  setup_category?: string | null
  catalyst?: string | null
  plan?: string | null
}
export interface MorningPrepResponse {
  generated_at?: string
  next_open_label?: string | null
  narrative?: string | null
  plan_for_open?: string | null
  shortlist: PrepRow[]
}

/* ---- system health ---- */
export interface SystemEvent {
  ts: string
  severity: string
  message: string
}
export interface SystemHealthResponse {
  watch_status?: string | null
  heartbeat_seconds?: number | null
  cycle?: number | null
  api_budget_used?: number | null
  api_budget_total?: number | null
  data_source?: string | null
  last_scan_label?: string | null
  events?: SystemEvent[]
}

/* ---- SSE ---- */
export interface StreamEvent {
  type: string
  symbol?: string
  message?: string
  ts?: string
  payload?: unknown
}
