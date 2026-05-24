export interface ScanRunInfo { id: number; created_at: string; universe_count: number; provider: string }
export interface ScanResultRow {
  symbol: string; score: number; setup_category: string; tags: string[]
  universe_role: string; name: string; sector: string; close: number
  entry: number; stop: number; target: number; rr: number; trade_plan_valid: boolean
  trend_score: number; momentum_score: number; volume_score: number; risk_score: number
  setup_quality_score: number; reasons: string[]; warnings: string[]
}
export interface CandidateSnapshot {
  id: number; symbol: string; status: string; setup_category: string; universe_role: string
  total_score: number | null; close: number | null; entry: number | null
  stop: number | null; target: number | null; risk_reward: number | null
  snapshot_time: string; outcome_label: string | null; notes: string | null
  tony_priority_label: string | null; tony_recommended_action: string | null
  tony_setup_read: string | null; tony_hypothesis: string | null
  entry_triggered: boolean; entry_triggered_at: string | null
}
export interface TonyEvent {
  id: number; event_type: string; severity: string; symbol: string | null
  title: string; message: string; created_at: string; acknowledged: boolean
}
export interface ManualPick {
  id: number; symbol: string; status: string; planned_entry: number | null
  planned_stop: number | null; planned_target: number | null; notes: string | null; picked_at: string
}
export interface WatchStatus {
  status: string | null; started_at: string | null; last_heartbeat_at: string | null
  cycles_completed: number; api_requests: number; symbols_scanned: number; last_scan_age_seconds: number | null
}
export interface TodayResponse {
  kpis: { watching: number; triggered: number; win_rate: number | null; last_scan_at: string | null }
  watch: WatchStatus; recent_events: TonyEvent[]; active_snapshots: CandidateSnapshot[]
}
export interface PicksResponse { picks: ManualPick[] }
export interface TrackingResponse { active: CandidateSnapshot[]; watching: CandidateSnapshot[]; open_count: number; triggered_count: number }
export interface OutcomesResponse {
  kpis: { active: number; closed: number; target_hits: number; stop_hits: number; win_rate: number | null }
  snapshots: CandidateSnapshot[]
}
export interface LatestScanResponse { run: ScanRunInfo | null; results: ScanResultRow[]; total: number }
export interface AnalyticsResponse {
  backtest: {
    research_disclaimer: string; snapshots_reviewed: number; conclusive_outcomes: number
    win_rate: number | null; avg_simulated_pl_per_trade: number | null; max_drawdown: number | null
    equity_curve: number[]; by_setup_category: Record<string,unknown>[]
    by_score_bucket: Record<string,unknown>[]; by_universe_role: Record<string,unknown>[]
  }
  outcome_counts: Record<string,unknown>[]
}
export interface TonyEventsResponse { events: TonyEvent[]; total: number; unacknowledged_count: number }
export interface SystemHealthResponse {
  watch: WatchStatus; last_scan_run: ScanRunInfo | null
  open_snapshots: number; triggered_snapshots: number; tony_events_total: number; unacknowledged_warnings: number
}
export interface SymbolDetailResponse {
  symbol: string; latest_snapshot: CandidateSnapshot | null; recent_snapshots: CandidateSnapshot[]
  latest_scan_result: ScanResultRow | null
  chart_bars: { date: string; open: number; high: number; low: number; close: number; volume: number }[]
}
export interface VaultBridgeSummary { available: boolean; latest_date: string | null; content: string | null }
export interface SSEHeartbeat { type: "heartbeat"; watch_status: string; last_scan_age_seconds: number | null; last_heartbeat_at: string }
export interface SSEEvent { type: "event"; event_type: string; severity: string; symbol: string | null; title: string; message: string; created_at: string }
export interface SSELiveAlert { type: "live_alert"; alert_type: "near_entry" | "stop_violation"; symbol: string; price: number; entry?: number; stop?: number }
export interface LiveQuote {
  symbol: string; price: number; bid: number | null; ask: number | null
  prev_close: number; change_pct: number; day_open: number; day_high: number
  day_low: number; day_volume: number; asof: string; is_live: boolean
}
export interface MarketStatus { open: boolean; next_open: string | null; next_close: string | null; timezone: string }
export interface PricesResponse { symbols: LiveQuote[]; market: MarketStatus }
