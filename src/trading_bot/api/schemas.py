from __future__ import annotations

from typing import Any

from pydantic import BaseModel


# ── Shared primitives ───────────────────────────────────────────────────────

class ScanRunInfo(BaseModel):
    id: int
    created_at: str
    universe_count: int
    provider: str


class ScanResultRow(BaseModel):
    symbol: str
    score: float
    setup_category: str
    tags: list[str]
    universe_role: str
    name: str
    sector: str
    close: float
    entry: float
    stop: float
    target: float
    rr: float
    trade_plan_valid: bool
    trend_score: float
    momentum_score: float
    volume_score: float
    risk_score: float
    setup_quality_score: float
    reasons: list[str]
    warnings: list[str]


class CandidateSnapshotRow(BaseModel):
    id: int
    symbol: str
    status: str
    setup_category: str
    universe_role: str
    total_score: float | None
    close: float | None
    entry: float | None
    stop: float | None
    target: float | None
    risk_reward: float | None
    snapshot_time: str
    outcome_label: str | None
    notes: str | None
    tony_priority_label: str | None
    tony_recommended_action: str | None
    tony_setup_read: str | None
    tony_hypothesis: str | None
    entry_triggered: bool
    entry_triggered_at: str | None


class TonyEventRow(BaseModel):
    id: int
    event_type: str
    severity: str
    symbol: str | None
    title: str
    message: str
    created_at: str
    acknowledged: bool


class ManualPickRow(BaseModel):
    id: int
    symbol: str
    status: str
    planned_entry: float | None
    planned_stop: float | None
    planned_target: float | None
    notes: str | None
    picked_at: str


class WatchStatus(BaseModel):
    status: str | None
    started_at: str | None
    last_heartbeat_at: str | None
    cycles_completed: int
    api_requests: int
    symbols_scanned: int
    last_scan_age_seconds: float | None


# ── Route responses ─────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    db_path: str


class TodayKPIs(BaseModel):
    watching: int
    triggered: int
    win_rate: float | None
    last_scan_at: str | None


class TodayResponse(BaseModel):
    kpis: TodayKPIs
    watch: WatchStatus
    recent_events: list[TonyEventRow]
    active_snapshots: list[CandidateSnapshotRow]


class PicksResponse(BaseModel):
    picks: list[ManualPickRow]


class TrackingResponse(BaseModel):
    active: list[CandidateSnapshotRow]
    watching: list[CandidateSnapshotRow]
    open_count: int
    triggered_count: int


class OutcomeKPIs(BaseModel):
    active: int
    closed: int
    target_hits: int
    stop_hits: int
    win_rate: float | None


class OutcomesResponse(BaseModel):
    kpis: OutcomeKPIs
    snapshots: list[CandidateSnapshotRow]


class LatestScanResponse(BaseModel):
    run: ScanRunInfo | None
    results: list[ScanResultRow]
    total: int


class ScanOverviewResponse(BaseModel):
    scanned: int
    candidates: int
    picks: int
    last_scan_at: str | None


class BacktestSummaryResponse(BaseModel):
    research_disclaimer: str
    snapshots_reviewed: int
    conclusive_outcomes: int
    win_rate: float | None
    avg_simulated_pl_per_trade: float | None
    max_drawdown: float | None
    equity_curve: list[float]
    by_setup_category: list[dict[str, Any]]
    by_score_bucket: list[dict[str, Any]]
    by_universe_role: list[dict[str, Any]]


class AnalyticsResponse(BaseModel):
    backtest: BacktestSummaryResponse
    outcome_counts: list[dict[str, Any]]


class TonyEventsResponse(BaseModel):
    events: list[TonyEventRow]
    total: int
    unacknowledged_count: int


class SystemHealthResponse(BaseModel):
    watch: WatchStatus
    last_scan_run: ScanRunInfo | None
    open_snapshots: int
    triggered_snapshots: int
    tony_events_total: int
    unacknowledged_warnings: int


class ChartBar(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class SymbolDetailResponse(BaseModel):
    symbol: str
    latest_snapshot: CandidateSnapshotRow | None
    recent_snapshots: list[CandidateSnapshotRow]
    latest_scan_result: ScanResultRow | None
    chart_bars: list[ChartBar]


class VaultBridgeSummary(BaseModel):
    available: bool
    latest_date: str | None
    content: str | None
