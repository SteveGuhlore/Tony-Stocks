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
    # ── Additive live-tracking fields (columns already exist in storage; Codex #3) ──
    # All optional/default-None so existing producers stay backward-compatible.
    current_price: float | None = None
    research_unrealized_pl_pct: float | None = None
    reassessment_label: str | None = None
    time_active_minutes: float | None = None
    original_entry: float | None = None
    original_stop: float | None = None
    original_target: float | None = None


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


class LiveQuoteSchema(BaseModel):
    symbol: str
    price: float
    bid: float | None
    ask: float | None
    prev_close: float
    change_pct: float
    day_open: float
    day_high: float
    day_low: float
    day_volume: float
    asof: str
    is_live: bool


class MarketStatus(BaseModel):
    open: bool
    next_open: str | None
    next_close: str | None
    timezone: str


class PricesResponse(BaseModel):
    symbols: list[LiveQuoteSchema]
    market: MarketStatus


# ── Command Center ("Tony Stocks") second-layer contract ─────────────────────
# See docs/CONTRACTS/command-center-bridge.md and dashboard-web/lib/types.ts.
# Producer files are CC-written: reports/tony_stocks_verdicts.json (picks) and
# reports/tony_stocks_record.json (record + agreement). This endpoint only maps
# them; it never writes. `verdict` is passed through verbatim so values outside
# the dashboard enum (e.g. "pass") survive — the frontend degrades unknowns to
# "⋯ awaiting" without erroring.

# ── Morning Prep (off-hours research engine) ─────────────────────────────────
# Mirrors MorningPrep.to_dict() / PrepCandidate.to_dict() from
# trading_bot.analytics.morning_prep.  All fields carry safe defaults so a
# partial or missing report still yields a well-formed response (never 500).

class PrepCandidateResponse(BaseModel):
    symbol: str = ""
    score: float = 0.0
    setup: str = ""
    entry: float | None = None
    stop: float | None = None
    target: float | None = None
    rr: float | None = None
    conviction: str = ""
    catalysts: dict[str, Any] = {}
    warnings: list[str] = []


class MorningPrepResponse(BaseModel):
    generated_at: str = ""
    et_date: str = ""
    phase: str = ""
    shortlist: list[PrepCandidateResponse] = []
    what_changed_overnight: str = ""
    plan_for_open: str = ""


class CommandCenterPick(BaseModel):
    symbol: str
    score: float
    verdict: str
    reasoning: str
    returned_at: str


class CommandCenterRecord(BaseModel):
    win_rate: float | None
    avg_pl_per_trade: float | None
    target_hits: int | None
    stop_hits: int | None
    equity_curve: list[float]


class CommandCenterAgreement(BaseModel):
    agreed_right: int
    agreed_wrong: int
    cc_overrode_saved: int
    cc_overrode_missed: int


class CommandCenterResponse(BaseModel):
    picks: dict[str, CommandCenterPick]
    record: CommandCenterRecord | None
    agreement: CommandCenterAgreement | None
