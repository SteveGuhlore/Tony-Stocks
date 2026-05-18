from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from trading_bot.scoring.score_models import ScoredStock
from trading_bot.storage.repositories import ScannerRepository


TONY_MODES = {"watcher", "analyst"}
TONY_FUTURE_MODES = {"paper_trader", "live_trader"}
TONY_SEVERITIES = {"info", "watch", "warning", "critical"}


@dataclass(frozen=True)
class TonyConfig:
    """Runtime configuration for Tony Stocks events."""

    enabled: bool = True
    agent_name: str = "Tony Stocks"
    mode: str = "watcher"
    create_events_for: tuple[str, ...] = (
        "scan_started",
        "scan_completed",
        "snapshots_created",
        "snapshots_updated",
        "high_score_candidate",
        "invalid_trade_plan_blocked",
        "outcome_updated",
        "warning_summary",
        "watch_cycle_completed",
        "outcome_analytics_updated",
        "data_provider_fallback",
        "stale_data_warning",
        "system_warning",
        "real_provider_active",
        "all_symbol_fallback",
        "provider_health_passed",
        "provider_health_failed",
        "real_data_scan_scaled",
        "rate_limit_warning",
        "universe_rotation_summary",
        "batch_fetch_summary",
        "provider_fallback_summary",
        "analyst_candidate_hypothesis",
        "analyst_market_context",
        "analyst_data_quality",
        "analyst_risk_warning",
        "intraday_analysis_summary",
        "watch_run_started",
        "watch_run_stopped",
        "watch_run_error",
        "watch_heartbeat_stale",
        "watch_waiting_for_market_open",
        "tony_learning_updated",
    )
    high_score_threshold: float = 85.0
    include_seeded_demo_events: bool = False
    max_events_per_cycle: int = 20

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "TonyConfig":
        """Build config from YAML-safe dict values."""
        data = raw or {}
        mode = str(data.get("mode", "watcher"))
        if mode not in TONY_MODES:
            mode = "watcher"
        create_events = data.get("create_events_for", cls.create_events_for)
        return cls(
            enabled=bool(data.get("enabled", True)),
            agent_name=str(data.get("agent_name", "Tony Stocks")),
            mode=mode,
            create_events_for=tuple(str(item) for item in create_events),
            high_score_threshold=float(data.get("high_score_threshold", 85)),
            include_seeded_demo_events=bool(data.get("include_seeded_demo_events", False)),
            max_events_per_cycle=max(1, int(data.get("max_events_per_cycle", 20))),
        )


class TonyStocksService:
    """Deterministic internal event layer for Tony Stocks.

    Tony currently writes structured database events only. It does not call
    LLMs, send external notifications, create paper trades, or place orders.
    """

    def __init__(self, repo: ScannerRepository, config: dict[str, Any] | None = None) -> None:
        self.repo = repo
        self.config = TonyConfig.from_dict(config)
        self._events_created_this_cycle = 0

    @property
    def enabled(self) -> bool:
        return self.config.enabled

    def start_cycle(self) -> None:
        """Reset the per-cycle event budget."""
        self._events_created_this_cycle = 0

    def create_event(
        self,
        event_type: str,
        severity: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
        symbol: str | None = None,
        source: str = "tony_stocks",
        notes: str | None = None,
    ) -> int | None:
        """Create one event if enabled, configured, and within budget."""
        if not self.enabled or event_type not in self.config.create_events_for:
            return None
        if severity not in TONY_SEVERITIES:
            severity = "info"
        if self._events_created_this_cycle >= self.config.max_events_per_cycle:
            return None
        event_id = self.repo.create_tony_event(
            event_type=event_type,
            severity=severity,
            symbol=symbol,
            title=title,
            message=message,
            payload=payload or {},
            source=source,
            notes=notes,
        )
        self._events_created_this_cycle += 1
        return event_id

    def record_scan_started(self, symbols_loaded: int, provider: str) -> None:
        self.create_event(
            event_type="scan_started",
            severity="info",
            title=f"{self.config.agent_name}: Scan started",
            message=f"Scan started for {symbols_loaded} configured symbols using {provider}.",
            payload={"symbols_loaded": symbols_loaded, "provider": provider, "mode": self.config.mode},
        )

    def record_scan_completed(
        self,
        scan_summary: dict[str, Any],
        results: list[ScoredStock],
        snapshot_ids: list[int] | None = None,
    ) -> None:
        """Create concise scan-completion, warning, and candidate events."""
        snapshot_count = len(snapshot_ids or [])
        warnings_count = int(scan_summary.get("warnings_count", 0))
        self.create_event(
            event_type="scan_completed",
            severity="info",
            title=f"{self.config.agent_name}: Scan completed",
            message=(
                f"{scan_summary.get('symbols_scored', 0)} symbols scored, "
                f"{snapshot_count} snapshots created, {warnings_count} warnings."
            ),
            payload=scan_summary | {"snapshots_created": snapshot_count},
        )
        if snapshot_count:
            self.create_event(
                event_type="snapshots_created",
                severity="watch",
                title=f"{self.config.agent_name}: Candidate snapshots saved",
                message=f"{snapshot_count} eligible candidate snapshot(s) were saved for follow-up tracking.",
                payload={"snapshot_ids": snapshot_ids or [], "scan_run_id": scan_summary.get("scan_run_id")},
            )
        if warnings_count:
            self.create_event(
                event_type="warning_summary",
                severity="warning",
                title=f"{self.config.agent_name}: Scan warning summary",
                message=f"Scan results include {warnings_count} warning(s). Review setup warnings before acting.",
                payload={"warnings_count": warnings_count, "scan_run_id": scan_summary.get("scan_run_id")},
            )
        invalid_count = sum(1 for result in results if not result.trade_plan_valid)
        if invalid_count:
            self.create_event(
                event_type="invalid_trade_plan_blocked",
                severity="warning",
                title=f"{self.config.agent_name}: Invalid trade plans blocked",
                message=f"{invalid_count} result(s) had invalid trade plans and should not be treated as buy opportunities.",
                payload={"invalid_trade_plan_count": invalid_count, "scan_run_id": scan_summary.get("scan_run_id")},
            )
        self._record_high_score_candidates(results, saved_snapshot_symbols=_snapshot_symbols(results, snapshot_count))

    def record_snapshot_update(self, update_summary: dict[str, Any]) -> None:
        """Create events for snapshot follow-up update summaries."""
        updated = int(update_summary.get("updated", 0))
        if updated:
            outcomes = update_summary.get("outcomes", {}) or {}
            self.create_event(
                event_type="snapshots_updated",
                severity="info",
                title=f"{self.config.agent_name}: Snapshots updated",
                message=_format_update_message(updated, outcomes),
                payload=update_summary,
            )
            self.create_event(
                event_type="outcome_updated",
                severity="watch",
                title=f"{self.config.agent_name}: Outcome summary updated",
                message=f"Latest outcome mix: {_format_outcomes(outcomes) or 'none'}.",
                payload={"outcomes": outcomes},
            )

    def record_watch_cycle_completed(self, cycle_summary: dict[str, Any]) -> None:
        """Create one event after a scheduled watch cycle completes."""
        next_run = cycle_summary.get("next_run_time") or "not scheduled"
        self.create_event(
            event_type="watch_cycle_completed",
            severity="info",
            title=f"{self.config.agent_name}: Watch cycle complete",
            message=(
                f"Watch cycle {cycle_summary.get('cycle')} complete. "
                f"Snapshots created: {cycle_summary.get('snapshots_created', 0)}, "
                f"snapshots updated: {cycle_summary.get('snapshots_updated', 0)}. "
                f"Next scan: {next_run}."
            ),
            payload=cycle_summary,
        )

    def record_data_provider_fallback(self, fallback_symbols: list[str], provider: str) -> None:
        """Create an event when a real provider has missing bars for one or more symbols."""
        if not fallback_symbols:
            return
        self.create_event(
            event_type="data_provider_fallback",
            severity="warning",
            title=f"{self.config.agent_name}: Missing real market data",
            message=(
                f"{len(fallback_symbols)} symbol(s) returned missing real data from {provider}: "
                f"{', '.join(sorted(fallback_symbols)[:10])}. "
                "No demo data was used for these symbols. Check eligibility, API access, and market hours."
            ),
            payload={
                "provider": provider,
                "missing_real_data_symbols": fallback_symbols,
                "fallback_symbols": fallback_symbols,
                "count": len(fallback_symbols),
            },
        )

    def record_stale_data_warning(self, stale_symbols: list[str], provider: str, stale_minutes: int) -> None:
        """Create an event when intraday data is older than the stale threshold."""
        if not stale_symbols:
            return
        self.create_event(
            event_type="stale_data_warning",
            severity="warning",
            title=f"{self.config.agent_name}: Stale intraday data detected",
            message=(
                f"{len(stale_symbols)} symbol(s) returned intraday bars older than {stale_minutes} minutes "
                f"from {provider}: {', '.join(sorted(stale_symbols)[:10])}. "
                "Snapshot signals may reflect outdated intraday prices."
            ),
            payload={"provider": provider, "stale_symbols": stale_symbols, "stale_minutes": stale_minutes, "count": len(stale_symbols)},
        )

    def record_real_data_scan_scaled(self, provider: str, symbols_scanned: int, api_requests: int, batch_requests: int) -> None:
        """Create an info event confirming scaled real-data scan completed."""
        self.create_event(
            event_type="real_data_scan_scaled",
            severity="info",
            title=f"{self.config.agent_name}: Scaled real-data scan complete",
            message=(
                f"{provider} scanned {symbols_scanned} symbols using {api_requests} API request(s) "
                f"({batch_requests} batch). "
                "Alpaca IEX is a single-exchange feed — not full SIP consolidated tape."
            ),
            payload={
                "provider": provider,
                "symbols_scanned": symbols_scanned,
                "api_requests": api_requests,
                "batch_requests": batch_requests,
            },
        )

    def record_rate_limit_warning(self, provider: str, warnings_count: int, waits_count: int) -> None:
        """Create a warning event when rate limiting was triggered during a scan."""
        self.create_event(
            event_type="rate_limit_warning",
            severity="warning",
            title=f"{self.config.agent_name}: Rate limit activity detected",
            message=(
                f"{provider} scan triggered {warnings_count} HTTP 429 response(s) and "
                f"{waits_count} rate-limiter wait(s). "
                "Consider reducing max_symbols_per_scan or increasing request_buffer_percent."
            ),
            payload={"provider": provider, "warnings_count": warnings_count, "waits_count": waits_count},
        )

    def record_universe_rotation_summary(self, rotation: dict[str, Any]) -> None:
        """Create a concise universe rotation event after each cycle."""
        self.create_event(
            event_type="universe_rotation_summary",
            severity="info",
            title=f"{self.config.agent_name}: Universe rotation — bucket {rotation.get('bucket_id', 0)}",
            message=(
                f"Cycle selected {rotation.get('total', 0)} symbols: "
                f"{rotation.get('core_count', 0)} core, "
                f"{rotation.get('open_snapshot_count', 0)} open-snapshot, "
                f"{rotation.get('previous_candidate_count', 0)} prior candidates, "
                f"{rotation.get('discovery_count', 0)} discovery (bucket {rotation.get('bucket_id', 0)})."
            ),
            payload=rotation,
        )

    def record_batch_fetch_summary(self, provider: str, symbols: int, api_requests: int, batch_requests: int, fallbacks: int) -> None:
        """Create a concise batch fetch summary event."""
        self.create_event(
            event_type="batch_fetch_summary",
            severity="info",
            title=f"{self.config.agent_name}: Batch fetch summary",
            message=(
                f"{provider} fetched {symbols} symbol(s) in {api_requests} request(s) "
                f"({batch_requests} batch, {fallbacks} missing/no-bar symbol(s))."
            ),
            payload={
                "provider": provider,
                "symbols": symbols,
                "api_requests": api_requests,
                "batch_requests": batch_requests,
                "fallbacks": fallbacks,
            },
        )

    def record_provider_fallback_summary(self, provider: str, fallback_count: int, total_scanned: int) -> None:
        """Create a warning event when a notable portion of symbols returned no real bars."""
        pct = round(100 * fallback_count / max(total_scanned, 1))
        self.create_event(
            event_type="provider_fallback_summary",
            severity="warning",
            title=f"{self.config.agent_name}: Missing real-data summary",
            message=(
                f"{fallback_count}/{total_scanned} ({pct}%) symbol(s) returned missing real data from {provider}. "
                "Those symbols were not scored from demo data."
            ),
            payload={"provider": provider, "missing_real_data_count": fallback_count, "fallback_count": fallback_count, "total_scanned": total_scanned, "fallback_pct": pct},
        )

    def record_real_provider_active(self, provider: str, symbols_with_real_data: int) -> None:
        """Create an info event confirming a real data provider returned data this cycle."""
        self.create_event(
            event_type="real_provider_active",
            severity="info",
            title=f"{self.config.agent_name}: Real provider returned data",
            message=(
                f"{provider} returned real market data for {symbols_with_real_data} symbol(s) this cycle. "
                "Alpaca IEX is a single-exchange feed — not full SIP consolidated tape."
            ),
            payload={"provider": provider, "symbols_with_real_data": symbols_with_real_data},
        )

    def record_all_symbol_fallback(self, provider: str, fallback_count: int) -> None:
        """Create a critical warning when every scanned symbol fell back to demo data."""
        self.create_event(
            event_type="all_symbol_fallback",
            severity="critical",
            title=f"{self.config.agent_name}: ALL symbols missing real data",
            message=(
                f"All {fallback_count} symbol(s) returned missing real data from {provider} this cycle. "
                "No demo data was used. Check Alpaca API keys, connectivity, and market hours."
            ),
            payload={"provider": provider, "fallback_count": fallback_count},
        )

    def record_provider_health_passed(self, health: dict[str, Any]) -> None:
        """Create an info event when a provider health check confirms data is flowing."""
        self.create_event(
            event_type="provider_health_passed",
            severity="info",
            title=f"{self.config.agent_name}: Provider health check passed",
            message=(
                f"{health.get('effective_provider')} returned data for "
                f"{health.get('symbols_with_data', 0)}/{health.get('symbols_requested', 0)} test symbol(s). "
                f"Latest bar: {health.get('latest_bar_time', 'unknown')}."
            ),
            payload=health,
        )

    def record_provider_health_failed(self, health: dict[str, Any]) -> None:
        """Create a warning event when a provider health check returns no real data."""
        errors = health.get("provider_errors") or []
        error_summary = "; ".join(errors[:3]) if errors else "no bars returned"
        self.create_event(
            event_type="provider_health_failed",
            severity="warning",
            title=f"{self.config.agent_name}: Provider health check failed",
            message=(
                f"{health.get('effective_provider')} health check: "
                f"{health.get('symbols_with_data', 0)}/{health.get('symbols_requested', 0)} symbol(s) returned data. "
                f"Errors: {error_summary}."
            ),
            payload=health,
        )

    def record_analyst_candidate_hypothesis(
        self,
        symbol: str,
        priority_label: str,
        recommended_action: str,
        hypothesis: str,
        setup_read: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        """Create one analyst hypothesis event per high-priority candidate.

        Tony is analyzing, not trading. No paper trades or orders are created.
        """
        severity = "watch" if priority_label in ("high_priority", "watch") else "info"
        self.create_event(
            event_type="analyst_candidate_hypothesis",
            severity=severity,
            symbol=symbol,
            title=f"{self.config.agent_name}: {symbol} — {priority_label} ({setup_read})",
            message=hypothesis,
            payload=payload or {
                "symbol": symbol,
                "priority_label": priority_label,
                "recommended_action": recommended_action,
                "setup_read": setup_read,
            },
        )

    def record_analyst_market_context(
        self,
        context_label: str,
        description: str,
        benchmark_symbols: list[str],
    ) -> None:
        """Create a market context event once per watch cycle."""
        severity = "warning" if context_label == "market_weak" else "info"
        self.create_event(
            event_type="analyst_market_context",
            severity=severity,
            title=f"{self.config.agent_name}: Market context — {context_label}",
            message=description,
            payload={
                "context_label": context_label,
                "benchmark_symbols": benchmark_symbols,
            },
        )

    def record_analyst_data_quality(
        self,
        dq_summary: dict[str, int],
        provider_name: str,
        total_candidates: int,
    ) -> None:
        """Create a data quality summary event once per scan cycle."""
        real_count = dq_summary.get("daily_real_alpaca", dq_summary.get("alpaca_iex_real_data", 0))
        intraday_real = dq_summary.get("intraday_real_alpaca", 0)
        demo_count = dq_summary.get("demo_data", 0)
        fallback_count = dq_summary.get("fallback_data", 0)
        stale_count = dq_summary.get("stale_data", 0)
        intraday_missing = dq_summary.get("intraday_missing", 0)
        intraday_fallback = dq_summary.get("intraday_fallback_demo", 0)
        intraday_stale = dq_summary.get("stale_intraday", 0)
        seeded_count = dq_summary.get("seeded_demo_fixture", 0)
        severity = "warning" if (fallback_count + stale_count + intraday_missing + intraday_fallback + intraday_stale) > 0 else "info"
        self.create_event(
            event_type="analyst_data_quality",
            severity=severity,
            title=f"{self.config.agent_name}: Data quality summary ({provider_name})",
            message=(
                f"{total_candidates} candidates: {real_count} daily real Alpaca, {intraday_real} intraday real Alpaca, "
                f"{demo_count} demo, {fallback_count} daily missing/fallback, {stale_count} daily stale, "
                f"{intraday_missing} intraday missing, {intraday_fallback} intraday fallback, "
                f"{intraday_stale} stale intraday (real Alpaca bars past freshness — often after hours; "
                f"also counted in intraday real when bars exist), {seeded_count} seeded fixtures. "
                "Alpaca IEX is a single-exchange feed — not full SIP consolidated tape."
            ),
            payload={
                "provider": provider_name,
                "total_candidates": total_candidates,
                **dq_summary,
            },
        )

    def record_analyst_risk_warning(
        self,
        symbols_with_risk: list[str],
        risk_types: list[str],
        provider_name: str,
    ) -> None:
        """Create a risk warning event when candidates have elevated ATR or invalid plans."""
        if not symbols_with_risk:
            return
        severity = "warning"
        self.create_event(
            event_type="analyst_risk_warning",
            severity=severity,
            title=f"{self.config.agent_name}: Risk concerns in {len(symbols_with_risk)} candidate(s)",
            message=(
                f"Risk flags in {len(symbols_with_risk)} candidate(s): {', '.join(symbols_with_risk[:10])}. "
                f"Risk types detected: {', '.join(sorted(set(risk_types)))}. "
                "Review before any manual pick decisions. Tony is analyzing, not trading."
            ),
            payload={
                "provider": provider_name,
                "symbols_with_risk": symbols_with_risk,
                "risk_types": risk_types,
                "count": len(symbols_with_risk),
            },
        )

    # ── Watch run lifecycle events ─────────────────────────────────────────────

    def record_intraday_analysis_summary(self, summary: dict[str, Any]) -> None:
        """Create one summary event for Tony's intraday research reads."""
        if not summary.get("enabled", False):
            return
        timeframe = str(summary.get("timeframe", "5Min"))
        provider_used = str(summary.get("intraday_provider", "none"))
        allow_fallback = bool(summary.get("allow_demo_fallback", False))
        requested = int(summary.get("symbols_requested", 0) or 0)
        with_data = int(summary.get("symbols_with_intraday", 0) or 0)
        real_count = int(summary.get("real_intraday_count", with_data) or 0)
        missing = int(summary.get("missing_count", 0) or 0)
        fallback = int(summary.get("intraday_fallback_count", 0) or 0)
        stale = int(summary.get("intraday_stale_count", 0) or 0)
        above = int(summary.get("above_vwap_count", 0) or 0)
        below = int(summary.get("below_vwap_count", 0) or 0)
        severity = "warning" if missing or fallback or stale else "info"
        self.create_event(
            event_type="intraday_analysis_summary",
            severity=severity,
            title=f"{self.config.agent_name}: Intraday analysis summary",
            message=(
                f"{timeframe} intraday provider={provider_used} allow_demo_fallback={allow_fallback}: "
                f"{real_count}/{requested} real Alpaca intraday, {missing} missing, {fallback} fallback, "
                f"{stale} stale real Alpaca (past freshness — often after hours). "
                f"VWAP: {above} above, {below} below. Research-only context; scoring unchanged."
            ),
            payload=summary,
        )

    def record_watch_run_started(
        self,
        run_id: int,
        provider: str,
        interval_minutes: float,
        market_hours_only: bool,
    ) -> None:
        """Create one event when watch mode starts. Research mode only — no trading."""
        self.create_event(
            event_type="watch_run_started",
            severity="info",
            title=f"{self.config.agent_name}: Watch mode started (run_id={run_id})",
            message=(
                f"Watch mode started. Provider: {provider}. "
                f"Interval: {interval_minutes:g} min. Market hours only: {market_hours_only}. "
                "Research mode only — no broker execution, paper trades, or live trading."
            ),
            payload={
                "run_id": run_id,
                "provider": provider,
                "interval_minutes": interval_minutes,
                "market_hours_only": market_hours_only,
            },
        )

    def record_watch_run_stopped(
        self,
        run_id: int,
        cycles_completed: int,
        stop_reason: str,
    ) -> None:
        """Create one event when watch mode stops cleanly."""
        self.create_event(
            event_type="watch_run_stopped",
            severity="info",
            title=f"{self.config.agent_name}: Watch mode stopped (run_id={run_id})",
            message=(
                f"Watch mode stopped cleanly after {cycles_completed} cycle(s). "
                f"Stop reason: {stop_reason}."
            ),
            payload={"run_id": run_id, "cycles_completed": cycles_completed, "stop_reason": stop_reason},
        )

    def record_watch_run_error(
        self,
        run_id: int,
        error_message: str,
        cycles_completed: int,
    ) -> None:
        """Create one critical event when watch mode stops due to an unhandled error."""
        self.create_event(
            event_type="watch_run_error",
            severity="critical",
            title=f"{self.config.agent_name}: Watch mode error (run_id={run_id})",
            message=(
                f"Watch mode stopped due to an error after {cycles_completed} cycle(s). "
                f"Error: {str(error_message)[:200]}"
            ),
            payload={"run_id": run_id, "error_message": str(error_message)[:500], "cycles_completed": cycles_completed},
        )

    def record_watch_heartbeat_stale(
        self,
        run_id: int,
        last_heartbeat_at: str,
        stale_minutes: int,
    ) -> None:
        """Create a warning when a previous watch run's heartbeat is stale at restart."""
        self.create_event(
            event_type="watch_heartbeat_stale",
            severity="warning",
            title=f"{self.config.agent_name}: Previous watch run heartbeat stale (run_id={run_id})",
            message=(
                f"Previous watch run (id={run_id}) last heartbeat was {last_heartbeat_at}, "
                f"more than {stale_minutes} min ago. "
                "The previous process may have exited without a clean shutdown."
            ),
            payload={"run_id": run_id, "last_heartbeat_at": last_heartbeat_at, "stale_minutes": stale_minutes},
        )

    def record_watch_waiting_for_market_open(
        self,
        timezone_name: str,
        current_time_et: str,
    ) -> None:
        """Create one event when watch mode enters the market-closed waiting state."""
        self.create_event(
            event_type="watch_waiting_for_market_open",
            severity="info",
            title=f"{self.config.agent_name}: Watch mode waiting for market hours",
            message=(
                f"Watch mode is running but the market is not open. "
                f"Current time: {current_time_et} ({timezone_name}). "
                "Regular session: 9:30 AM – 4:00 PM ET. No holiday calendar applied."
            ),
            payload={"timezone": timezone_name, "current_time": current_time_et},
        )

    def record_tony_learning_updated(
        self,
        snapshot_count: int,
        analyzed_count: int,
        by_priority: dict[str, Any] | None = None,
    ) -> int | None:
        """Create one event when Tony hypothesis-to-outcome analytics is calculated.

        Fires at most once per outcome-analytics run. Tony is analyzing, not trading.
        Seeded demo fixtures must be excluded before calling this method.
        """
        return self.create_event(
            event_type="tony_learning_updated",
            severity="info",
            title=f"{self.config.agent_name}: Tony learning analytics updated",
            message=(
                f"Tony learning reviewed {snapshot_count} filtered snapshot(s); "
                f"{analyzed_count} have Tony analysis attached. "
                "Early tracking only — not enough history to draw conclusions. "
                "Research mode only."
            ),
            payload={
                "snapshot_count": snapshot_count,
                "analyzed_count": analyzed_count,
                "by_priority": by_priority or {},
            },
        )

    def record_outcome_analytics(self, analytics_summary: dict[str, Any]) -> None:
        """Create one concise event after outcome analytics is calculated."""
        included_seeded = bool(analytics_summary.get("include_seeded_demo", False))
        snapshot_count = int(analytics_summary.get("snapshot_count", 0))
        best_group = analytics_summary.get("best_group") or "none"
        suffix = " Includes seeded demo fixtures; not evidence of real market edge." if included_seeded else ""
        self.create_event(
            event_type="outcome_analytics_updated",
            severity="warning" if included_seeded else "info",
            title=f"{self.config.agent_name}: Outcome analytics updated",
            message=(
                f"Outcome analytics reviewed {snapshot_count} snapshot(s). "
                f"Highest target-hit rate currently appears in {best_group}.{suffix}"
            ),
            payload=analytics_summary,
        )

    def latest_events(
        self,
        limit: int = 20,
        severity: str | None = None,
        event_type: str | None = None,
        symbol: str | None = None,
        unacknowledged: bool = False,
    ) -> pd.DataFrame:
        """List recent Tony events."""
        return self.repo.list_tony_events(
            limit=limit,
            severity=severity,
            event_type=event_type,
            symbol=symbol,
            unacknowledged=unacknowledged,
        )

    def _record_high_score_candidates(self, results: list[ScoredStock], saved_snapshot_symbols: set[str]) -> None:
        candidates = [
            result
            for result in results
            if result.final_score >= self.config.high_score_threshold
            and result.universe_role == "primary_candidate"
            and result.trade_plan_valid
            and result.setup_category not in {"Weak / Avoid", "Overextended / Wait", "Invalid Trade Plan"}
        ]
        for result in candidates:
            saved_text = " Snapshot saved." if result.symbol in saved_snapshot_symbols else ""
            self.create_event(
                event_type="high_score_candidate",
                severity="watch",
                title=f"{self.config.agent_name}: {result.symbol} high-score candidate",
                message=(
                    f"{result.symbol} entered {result.setup_category} with score {result.final_score}. "
                    f"Trade plan valid.{saved_text}"
                ),
                payload={
                    "symbol": result.symbol,
                    "score": result.final_score,
                    "setup_category": result.setup_category,
                    "trade_plan_valid": result.trade_plan_valid,
                    "risk_reward": result.risk_reward_ratio,
                },
                symbol=result.symbol,
            )


def _format_update_message(updated: int, outcomes: dict[str, int]) -> str:
    target = outcomes.get("target_hit", 0) + outcomes.get("target_before_stop", 0)
    stop = outcomes.get("stop_hit", 0) + outcomes.get("stop_before_target", 0)
    insufficient = outcomes.get("insufficient_future_data", 0)
    partial_failed = outcomes.get("partial_move", 0) + outcomes.get("failed_setup", 0)
    return (
        f"{updated} snapshots updated: {target} target-related, {stop} stop-related, "
        f"{partial_failed} partial/failed, {insufficient} insufficient data."
    )


def _format_outcomes(outcomes: dict[str, int]) -> str:
    return ", ".join(f"{label}: {count}" for label, count in sorted(outcomes.items(), key=lambda item: (-item[1], item[0]))[:8])


def _snapshot_symbols(results: list[ScoredStock], snapshot_count: int) -> set[str]:
    if snapshot_count <= 0:
        return set()
    eligible_categories = {"Breakout Watch", "Pullback Watch", "Momentum Continuation", "Base Building", "Speculative Watchlist"}
    return {
        result.symbol
        for result in results
        if result.trade_plan_valid and result.setup_category in eligible_categories and result.universe_role in {"primary_candidate", "speculative_candidate"}
    }
