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
        "system_warning",
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
