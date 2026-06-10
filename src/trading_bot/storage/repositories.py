from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from trading_bot.scoring.score_models import ScoredStock
from trading_bot.storage.database import connect, initialize_database
from trading_bot.utils.time_utils import utc_now_iso


class ScannerRepository:
    """Repository for scan runs, scan results, picks, and paper trades."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        initialize_database(self.database_path)

    def create_scan_run(self, universe_count: int, provider: str, config_snapshot: dict[str, Any]) -> int:
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO scan_runs (created_at, universe_count, provider, config_snapshot_json)
                VALUES (?, ?, ?, ?)
                """,
                (utc_now_iso(), universe_count, provider, json.dumps(config_snapshot, default=str)),
            )
            return int(cursor.lastrowid)

    def save_scan_results(self, scan_run_id: int, results: list[ScoredStock]) -> None:
        with connect(self.database_path) as conn:
            conn.executemany(
                """
                INSERT INTO scan_results (
                    scan_run_id, symbol, final_score, setup_category, tags_json, universe_role, name,
                    sector, industry, demo_profile, notes, candidate_summary,
                    trend_score, momentum_score, volume_score, risk_score, setup_quality_score,
                    latest_close, avg_volume_20, dollar_volume_20, return_5d, return_10d,
                    return_20d, atr_14, atr_percent, volatility_20d, relative_volume,
                    suggested_entry, suggested_stop,
                    suggested_target_1, risk_reward_ratio, trade_plan_valid, trade_plan_status,
                    reasons_json, warnings_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        scan_run_id,
                        result.symbol,
                        result.final_score,
                        result.setup_category,
                        json.dumps(result.tags),
                        result.universe_role,
                        result.name,
                        result.sector,
                        result.industry,
                        result.demo_profile,
                        result.notes,
                        result.candidate_summary,
                        result.trend_score,
                        result.momentum_score,
                        result.volume_score,
                        result.risk_score,
                        result.setup_quality_score,
                        result.latest_close,
                        result.avg_volume_20,
                        result.dollar_volume_20,
                        result.return_5d,
                        result.return_10d,
                        result.return_20d,
                        result.atr_14,
                        result.atr_percent,
                        result.volatility_20d,
                        result.relative_volume,
                        result.suggested_entry,
                        result.suggested_stop,
                        result.suggested_target_1,
                        result.risk_reward_ratio,
                        int(result.trade_plan_valid),
                        result.trade_plan_status,
                        json.dumps(result.reasons),
                        json.dumps(result.warnings),
                        result.scanned_at,
                    )
                    for result in results
                ],
            )

    def latest_scan_run(self) -> dict[str, Any] | None:
        with connect(self.database_path) as conn:
            row = conn.execute("SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def list_scan_runs(self, limit: int = 200) -> list[dict[str, Any]]:
        """Return recent scan runs ordered newest-first."""
        with connect(self.database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_scan_results(self) -> pd.DataFrame:
        run = self.latest_scan_run()
        if not run:
            return pd.DataFrame()
        with connect(self.database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM scan_results WHERE scan_run_id = ? ORDER BY final_score DESC",
                (run["id"],),
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def list_scan_results_for_run_ids(self, scan_run_ids: list[int], limit: int = 10000) -> pd.DataFrame:
        """Return scan results for the provided scan run ids."""
        ids = [int(run_id) for run_id in scan_run_ids if run_id is not None]
        if not ids:
            return pd.DataFrame()
        placeholders = ", ".join("?" for _ in ids)
        params: list[Any] = [*ids, limit]
        with connect(self.database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT *
                FROM scan_results
                WHERE scan_run_id IN ({placeholders})
                ORDER BY created_at DESC, final_score DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def get_recent_scan_result_metrics(self, max_age_days: int = 7, limit: int = 5000) -> list[dict[str, Any]]:
        """Return lightweight symbol metrics from recent scan results for pre-screening.

        Only fetches the fields needed by the pre-screener (symbol, latest_close,
        avg_volume_20, created_at).  Returns one row per (symbol, created_at) — the
        caller (``build_recent_symbol_metrics``) picks the most recent per symbol.

        Parameters
        ----------
        max_age_days:
            Only return rows created within this many days.  Set conservatively;
            7 days means a symbol that last appeared in a scan up to a week ago
            can still be pre-screened without any extra API calls.
        limit:
            Hard cap on result rows to avoid reading the entire history table.
        """
        cutoff_iso = (
            __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
            - __import__("datetime").timedelta(days=max_age_days)
        ).isoformat()
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT symbol, latest_close, avg_volume_20, created_at
                FROM scan_results
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (cutoff_iso, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def add_manual_pick(
        self,
        symbol: str,
        scan_run_id: int | None,
        planned_entry: float | None,
        planned_stop: float | None,
        planned_target: float | None,
        notes: str,
        status: str = "watching",
    ) -> None:
        with connect(self.database_path) as conn:
            conn.execute(
                """
                INSERT INTO manual_picks (
                    symbol, scan_run_id, picked_at, planned_entry, planned_stop, planned_target, notes, status
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (symbol.upper(), scan_run_id, utc_now_iso(), planned_entry, planned_stop, planned_target, notes, status),
            )

    def manual_picks(self) -> pd.DataFrame:
        with connect(self.database_path) as conn:
            rows = conn.execute("SELECT * FROM manual_picks ORDER BY picked_at DESC").fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def add_paper_trade(self, trade: dict[str, Any]) -> None:
        entry = float(trade.get("entry_price") or 0)
        exit_price = trade.get("exit_price")
        shares = float(trade.get("shares") or 0)
        pnl = None
        pnl_pct = None
        if exit_price not in (None, "") and entry > 0 and shares:
            exit_value = float(exit_price)
            pnl = (exit_value - entry) * shares
            pnl_pct = (exit_value / entry - 1) * 100
        with connect(self.database_path) as conn:
            conn.execute(
                """
                INSERT INTO paper_trades (
                    symbol, picked_at, entry_date, entry_price, stop_price, target_price,
                    exit_date, exit_price, shares, pnl, pnl_pct, status, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(trade.get("symbol", "")).upper(),
                    trade.get("picked_at"),
                    trade.get("entry_date"),
                    trade.get("entry_price"),
                    trade.get("stop_price"),
                    trade.get("target_price"),
                    trade.get("exit_date"),
                    exit_price,
                    trade.get("shares"),
                    pnl,
                    pnl_pct,
                    trade.get("status", "open"),
                    trade.get("notes", ""),
                ),
            )

    def paper_trades(self) -> pd.DataFrame:
        with connect(self.database_path) as conn:
            rows = conn.execute("SELECT * FROM paper_trades ORDER BY id DESC").fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def create_tony_event(
        self,
        event_type: str,
        severity: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
        source: str = "tony_stocks",
        symbol: str | None = None,
        notes: str | None = None,
    ) -> int:
        """Create one internal Tony Stocks event."""
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO tony_events (
                    created_at, event_type, severity, symbol, title, message,
                    payload_json, source, acknowledged, dismissed, notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?)
                """,
                (
                    utc_now_iso(),
                    event_type,
                    severity,
                    symbol.upper() if symbol else None,
                    title,
                    message,
                    json.dumps(payload or {}, default=str),
                    source,
                    notes,
                ),
            )
            return int(cursor.lastrowid)

    def list_tony_events(
        self,
        limit: int = 50,
        severity: str | None = None,
        event_type: str | None = None,
        symbol: str | None = None,
        unacknowledged: bool = False,
    ) -> pd.DataFrame:
        """List recent Tony Stocks events with optional filters."""
        where: list[str] = []
        params: list[Any] = []
        if severity:
            where.append("severity = ?")
            params.append(severity)
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        if symbol:
            where.append("symbol = ?")
            params.append(symbol.upper())
        if unacknowledged:
            where.append("acknowledged = 0")
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with connect(self.database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM tony_events
                {clause}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def count_tony_events(self, severity: str | None = None, event_type: str | None = None) -> int:
        """Count Tony Stocks events with optional filters."""
        where: list[str] = []
        params: list[Any] = []
        if severity:
            where.append("severity = ?")
            params.append(severity)
        if event_type:
            where.append("event_type = ?")
            params.append(event_type)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        with connect(self.database_path) as conn:
            row = conn.execute(f"SELECT COUNT(*) AS count FROM tony_events {clause}", params).fetchone()
            return int(row["count"])

    def create_candidate_snapshots(
        self,
        scan_run_id: int,
        results: list[ScoredStock],
        snapshot_config: dict[str, Any] | None = None,
        tony_analyses: dict[str, Any] | None = None,
        entry_plans: dict[str, dict[str, Any]] | None = None,
    ) -> list[int]:
        """Create candidate snapshots from scored scan results.

        tony_analyses maps symbol → dict with Tony analyst fields (from CandidateAnalysis.to_dict()
        plus 'tony_analysis_version'). When provided the Tony hypothesis fields are stored on the
        snapshot row. When absent or when no analysis exists for a symbol, Tony fields are NULL.
        No broker execution, paper trades, or orders are created.
        """
        config = snapshot_config or {}
        if not config.get("enabled", True):
            return []

        min_score = float(config.get("min_score", 0))
        include_roles = set(config.get("include_roles", []))
        include_categories = set(config.get("include_categories", []))
        exclude_categories = set(config.get("exclude_categories", []))
        include_benchmarks = bool(config.get("include_benchmarks", False))
        include_references = bool(config.get("include_references", False))
        allow_invalid_trade_plans = bool(config.get("allow_invalid_trade_plans", False))
        dedupe_minutes = int(config.get("dedupe_minutes", 0) or 0)

        created_ids: list[int] = []
        snapshot_time = utc_now_iso()
        with connect(self.database_path) as conn:
            for result in results:
                if not allow_invalid_trade_plans and not result.trade_plan_valid:
                    continue
                if result.final_score < min_score:
                    continue
                if include_roles and result.universe_role not in include_roles:
                    if not (include_benchmarks and result.universe_role == "benchmark") and not (
                        include_references and result.universe_role == "reference"
                    ):
                        continue
                if result.universe_role == "benchmark" and not include_benchmarks:
                    continue
                if result.universe_role == "reference" and not include_references:
                    continue
                if include_categories and result.setup_category not in include_categories:
                    continue
                if result.setup_category in exclude_categories:
                    continue
                if dedupe_minutes and self._recent_snapshot_exists(
                    conn=conn,
                    symbol=result.symbol,
                    setup_category=result.setup_category,
                    dedupe_minutes=dedupe_minutes,
                ):
                    continue
                ta: dict[str, Any] | None = (tony_analyses or {}).get(result.symbol)
                ep: dict[str, Any] = (entry_plans or {}).get(result.symbol, {})
                planned_entry = ep.get("planned_entry_price")
                cursor = conn.execute(
                    """
                    INSERT INTO candidate_snapshots (
                        scan_run_id, symbol, snapshot_time, universe_role, tags_json, setup_category,
                        total_score, close, entry, stop, target, risk_reward, dollar_volume,
                        relative_volume, atr_percent, trade_plan_valid, trade_plan_status,
                        reasons_json, warnings_json, candidate_summary,
                        status, entry_trigger_price, entry_triggered,
                        snapshot_price, snapshot_bar_time, planned_entry_price, planned_entry_rule,
                        planned_entry_buffer_pct, actual_entry_price, actual_entry_time, entry_status,
                        entry_trigger_source, entry_trigger_timeframe, entry_trigger_notes,
                        tony_priority_label, tony_recommended_action, tony_setup_read,
                        tony_volume_read, tony_risk_read, tony_market_context_read,
                        tony_data_quality_read, tony_outcome_context, tony_hypothesis,
                        tony_reasons_json, tony_concerns_json, tony_analysis_version,
                        tony_intraday_read, intraday_timeframe, intraday_close, intraday_vwap,
                        intraday_above_vwap, intraday_day_change_percent,
                        intraday_relative_volume, intraday_opening_range_status,
                        data_source, data_source_provider, used_demo_data, used_fallback_data,
                        real_data_only_run, missing_real_data_reason
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scan_run_id,
                        result.symbol,
                        snapshot_time,
                        result.universe_role,
                        json.dumps(result.tags),
                        result.setup_category,
                        result.final_score,
                        result.latest_close,
                        result.suggested_entry,
                        result.suggested_stop,
                        result.suggested_target_1,
                        result.risk_reward_ratio,
                        result.dollar_volume_20,
                        result.relative_volume,
                        result.atr_percent,
                        int(result.trade_plan_valid),
                        result.trade_plan_status,
                        json.dumps(result.reasons),
                        json.dumps(result.warnings),
                        result.candidate_summary,
                        "open/watch",
                        planned_entry if planned_entry is not None else result.suggested_entry,
                        0,
                        ep.get("snapshot_price"),
                        ep.get("snapshot_bar_time"),
                        planned_entry,
                        ep.get("planned_entry_rule"),
                        ep.get("planned_entry_buffer_pct"),
                        ep.get("actual_entry_price"),
                        ep.get("actual_entry_time"),
                        ep.get("entry_status"),
                        ep.get("entry_trigger_source"),
                        ep.get("entry_trigger_timeframe"),
                        ep.get("entry_trigger_notes"),
                        ta.get("priority_label") if ta else None,
                        ta.get("recommended_action") if ta else None,
                        ta.get("setup_read") if ta else None,
                        ta.get("volume_read") if ta else None,
                        ta.get("risk_read") if ta else None,
                        ta.get("market_context_read") if ta else None,
                        ta.get("data_quality_read") if ta else None,
                        ta.get("outcome_context") if ta else None,
                        ta.get("tony_hypothesis") if ta else None,
                        json.dumps(ta.get("reasons", [])) if ta else None,
                        json.dumps(ta.get("concerns", [])) if ta else None,
                        ta.get("tony_analysis_version") if ta else None,
                        ta.get("intraday_read") if ta else None,
                        ta.get("intraday_timeframe") if ta else None,
                        ta.get("intraday_close") if ta else None,
                        ta.get("intraday_vwap") if ta else None,
                        _bool_to_int_or_none(ta.get("intraday_above_vwap")) if ta else None,
                        ta.get("intraday_day_change_percent") if ta else None,
                        ta.get("intraday_relative_volume") if ta else None,
                        ta.get("intraday_opening_range_status") if ta else None,
                        ta.get("data_source") if ta else None,
                        ta.get("data_source_provider") if ta else None,
                        _bool_to_int_or_none(ta.get("used_demo_data")) if ta else None,
                        _bool_to_int_or_none(ta.get("used_fallback_data")) if ta else None,
                        _bool_to_int_or_none(ta.get("real_data_only_run")) if ta else None,
                        ta.get("missing_real_data_reason") if ta else None,
                    ),
                )
                created_ids.append(int(cursor.lastrowid))
        return created_ids

    def list_candidate_snapshots(
        self,
        status: str | None = None,
        setup_category: str | None = None,
        universe_role: str | None = None,
        date: str | None = None,
        limit: int = 200,
    ) -> pd.DataFrame:
        """List candidate snapshots with optional simple filters."""
        where: list[str] = []
        params: list[Any] = []
        if status:
            where.append("status = ?")
            params.append(status)
        if setup_category:
            where.append("setup_category = ?")
            params.append(setup_category)
        if universe_role:
            where.append("universe_role = ?")
            params.append(universe_role)
        if date:
            where.append("substr(snapshot_time, 1, 10) = ?")
            params.append(date)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with connect(self.database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM candidate_snapshots
                {clause}
                ORDER BY snapshot_time DESC, total_score DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def list_snapshots_for_analytics(
        self,
        include_seeded_demo: bool = False,
        days: int | None = None,
        universe_role: str | None = None,
        setup_category: str | None = None,
        outcome_label: str | None = None,
        min_score: float | None = None,
        limit: int = 5000,
    ) -> pd.DataFrame:
        """List candidate snapshots for outcome analytics."""
        where: list[str] = []
        params: list[Any] = []
        if not include_seeded_demo:
            where.append(
                """
                NOT (
                    COALESCE(notes, '') LIKE '%Demo seeded snapshot%'
                    OR COALESCE(notes, '') LIKE '%Seeded demo snapshot%'
                    OR setup_category = 'Demo Outcome Fixture'
                    OR tags_json LIKE '%demo_seeded%'
                    OR tags_json LIKE '%outcome_fixture%'
                )
                """
            )
        if days is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).replace(microsecond=0).isoformat()
            where.append("snapshot_time >= ?")
            params.append(cutoff)
        if universe_role:
            where.append("universe_role = ?")
            params.append(universe_role)
        if setup_category:
            where.append("setup_category = ?")
            params.append(setup_category)
        if outcome_label:
            where.append("COALESCE(outcome_label, 'unreviewed') = ?")
            params.append(outcome_label)
        if min_score is not None:
            where.append("total_score >= ?")
            params.append(min_score)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        params.append(limit)
        with connect(self.database_path) as conn:
            rows = conn.execute(
                f"""
                SELECT
                    candidate_snapshots.*,
                    scan_runs.provider AS snapshot_provider,
                    scan_runs.created_at AS scan_created_at
                FROM candidate_snapshots
                LEFT JOIN scan_runs ON scan_runs.id = candidate_snapshots.scan_run_id
                {clause}
                ORDER BY candidate_snapshots.snapshot_time DESC, candidate_snapshots.total_score DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def list_snapshot_subscores(self, limit: int = 10000) -> pd.DataFrame:
        """Join candidate snapshots to their scan_results sub-scores.

        The five component sub-scores (trend/momentum/volume/risk/setup_quality) live only
        in ``scan_results``; ``candidate_snapshots`` keeps the blended ``total_score``. This
        join — on ``(scan_run_id, symbol)`` — recovers the sub-scores per snapshot for
        divergence-calibration attribution. Read-only.
        """
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    cs.symbol AS symbol,
                    cs.snapshot_time AS snapshot_time,
                    cs.setup_category AS setup_category,
                    cs.total_score AS total_score,
                    sr.trend_score AS trend_score,
                    sr.momentum_score AS momentum_score,
                    sr.volume_score AS volume_score,
                    sr.risk_score AS risk_score,
                    sr.setup_quality_score AS setup_quality_score
                FROM candidate_snapshots cs
                JOIN scan_results sr
                    ON sr.scan_run_id = cs.scan_run_id AND sr.symbol = cs.symbol
                ORDER BY cs.snapshot_time DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def latest_candidate_snapshots(self, limit: int = 100) -> pd.DataFrame:
        """Return recent candidate snapshots."""
        return self.list_candidate_snapshots(limit=limit)

    def create_demo_candidate_snapshot(self, snapshot: dict[str, Any], dedupe: bool = True) -> int | None:
        """Insert one clearly labeled demo/testing candidate snapshot."""
        with connect(self.database_path) as conn:
            if dedupe and self._demo_snapshot_exists(
                conn=conn,
                symbol=str(snapshot["symbol"]),
                notes=str(snapshot.get("notes", "")),
            ):
                return None
            cursor = conn.execute(
                """
                INSERT INTO candidate_snapshots (
                    scan_run_id, symbol, snapshot_time, universe_role, tags_json, setup_category,
                    total_score, close, entry, stop, target, risk_reward, trade_plan_valid,
                    trade_plan_status, dollar_volume, relative_volume, atr_percent, reasons_json,
                    warnings_json, candidate_summary, status, entry_trigger_price, entry_triggered,
                    notes, data_source, data_source_provider, used_demo_data, used_fallback_data,
                    real_data_only_run, missing_real_data_reason
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(snapshot["scan_run_id"]),
                    str(snapshot["symbol"]).upper(),
                    snapshot["snapshot_time"],
                    snapshot.get("universe_role", "primary_candidate"),
                    json.dumps(snapshot.get("tags", ["demo_seeded"])),
                    snapshot.get("setup_category", "Demo Outcome Fixture"),
                    float(snapshot.get("total_score", 70)),
                    float(snapshot["close"]),
                    float(snapshot["entry"]),
                    float(snapshot["stop"]),
                    float(snapshot["target"]),
                    float(snapshot["risk_reward"]),
                    int(snapshot.get("trade_plan_valid", 1)),
                    snapshot.get("trade_plan_status", "valid"),
                    float(snapshot.get("dollar_volume", 0)),
                    float(snapshot.get("relative_volume", 1)),
                    float(snapshot.get("atr_percent", 0)),
                    json.dumps(snapshot.get("reasons", ["Demo seeded snapshot for outcome tracker testing."])),
                    json.dumps(snapshot.get("warnings", ["Demo seeded snapshot; not evidence of real market edge."])),
                    snapshot.get("candidate_summary", "Demo seeded snapshot for dashboard/outcome tracker testing only."),
                    snapshot.get("status", "open/watch"),
                    float(snapshot["entry"]),
                    0,
                    snapshot.get("notes", "Demo seeded snapshot for outcome tracker testing."),
                    "demo_generated",
                    "demo_generated",
                    1,
                    0,
                    0,
                    None,
                ),
            )
            return int(cursor.lastrowid)

    def list_open_candidate_snapshots(self, limit: int = 500) -> pd.DataFrame:
        """Return open/watch candidate snapshots for follow-up updates."""
        return self.list_candidate_snapshots(status="open/watch", limit=limit)

    def update_candidate_snapshot_followup(self, snapshot_id: int, **fields: Any) -> None:
        """Update follow-up tracking fields for a candidate snapshot."""
        allowed = {
            "status",
            "entry_trigger_price",
            "entry_triggered",
            "entry_triggered_at",
            "snapshot_price",
            "snapshot_bar_time",
            "planned_entry_price",
            "planned_entry_rule",
            "planned_entry_buffer_pct",
            "actual_entry_price",
            "actual_entry_time",
            "entry_status",
            "entry_trigger_source",
            "entry_trigger_timeframe",
            "entry_trigger_notes",
            "highest_price_seen",
            "lowest_price_seen",
            "last_checked_at",
            "result_1h",
            "result_eod",
            "result_3d",
            "result_5d",
            "result_10d",
            "result_20d",
            "outcome_label",
            "notes",
            "original_entry_price",
            "original_target_price",
            "original_stop_price",
            "original_plan_captured_at",
            "tracking_status",
            "tracking_started_at",
            "current_price",
            "current_price_at",
            "research_unrealized_pl_pct",
            "current_target_price",
            "current_stop_price",
            "reassessment_label",
            "reassessment_note",
            "last_reassessed_at",
            "invalidation_reason",
            "time_active_minutes",
            "pick_phase",
        }
        updates = {key: value for key, value in fields.items() if key in allowed}
        if not updates:
            return
        assignments = ", ".join(f"{key} = ?" for key in updates)
        params = list(updates.values()) + [snapshot_id]
        with connect(self.database_path) as conn:
            conn.execute(f"UPDATE candidate_snapshots SET {assignments} WHERE id = ?", params)

    def count_candidate_snapshots_by_outcome(self) -> pd.DataFrame:
        """Count candidate snapshots grouped by outcome label."""
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT COALESCE(outcome_label, 'unreviewed') AS outcome_label, COUNT(*) AS count
                FROM candidate_snapshots
                GROUP BY COALESCE(outcome_label, 'unreviewed')
                ORDER BY count DESC, outcome_label
                """
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def count_open_candidate_snapshots(self) -> int:
        """Count open/watch candidate snapshots."""
        with connect(self.database_path) as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM candidate_snapshots WHERE status = 'open/watch'").fetchone()
            return int(row["count"])

    def count_triggered_candidate_snapshots(self) -> int:
        """Count candidate snapshots with entry_triggered set."""
        with connect(self.database_path) as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM candidate_snapshots WHERE entry_triggered = 1").fetchone()
            return int(row["count"])

    def count_entry_trigger_status(self, status: str, date: str | None = None) -> int:
        """Count snapshots by V15 entry_status, optionally filtered to one UTC date prefix."""
        with connect(self.database_path) as conn:
            if date:
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS count FROM candidate_snapshots
                    WHERE entry_status = ? AND substr(snapshot_time, 1, 10) = ?
                    """,
                    (status, date),
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) AS count FROM candidate_snapshots WHERE entry_status = ?",
                    (status,),
                ).fetchone()
            return int(row["count"])

    def count_planned_triggers_today(self, today: str) -> int:
        """Count snapshots today with a planned entry trigger price."""
        with connect(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS count FROM candidate_snapshots
                WHERE substr(snapshot_time, 1, 10) = ? AND planned_entry_price IS NOT NULL
                """,
                (today,),
            ).fetchone()
            return int(row["count"])

    def count_candidate_snapshots_by_category(self) -> pd.DataFrame:
        """Count candidate snapshots grouped by setup category."""
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT setup_category, COUNT(*) AS count
                FROM candidate_snapshots
                GROUP BY setup_category
                ORDER BY count DESC, setup_category
                """
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    def count_candidate_snapshots_by_role(self) -> pd.DataFrame:
        """Count candidate snapshots grouped by universe role."""
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT universe_role, COUNT(*) AS count
                FROM candidate_snapshots
                GROUP BY universe_role
                ORDER BY count DESC, universe_role
                """
            ).fetchall()
        return pd.DataFrame([dict(row) for row in rows])

    # ── Watch run state ────────────────────────────────────────────────────────

    def create_watch_run(
        self,
        provider: str,
        interval_minutes: float,
        market_hours_only: bool,
    ) -> int:
        """Create a watch run record when watch mode starts."""
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO watch_runs (
                    started_at, last_heartbeat_at, status, provider, interval_minutes, market_hours_only
                )
                VALUES (?, ?, 'running', ?, ?, ?)
                """,
                (utc_now_iso(), utc_now_iso(), provider, float(interval_minutes), int(market_hours_only)),
            )
            return int(cursor.lastrowid)

    def update_watch_run_heartbeat(
        self,
        run_id: int,
        cycles_completed: int = 0,
        latest_scan_run_id: int | None = None,
        latest_symbols_selected: int | None = None,
        latest_symbols_scored: int | None = None,
        latest_snapshots_created: int | None = None,
        latest_api_requests_used: int | None = None,
        latest_rate_limit_warnings: int | None = None,
        latest_fallback_count: int | None = None,
    ) -> None:
        """Update heartbeat timestamp and latest cycle stats after each watch cycle."""
        with connect(self.database_path) as conn:
            conn.execute(
                """
                UPDATE watch_runs SET
                    last_heartbeat_at = ?,
                    cycles_completed = ?,
                    latest_scan_run_id = ?,
                    latest_symbols_selected = ?,
                    latest_symbols_scored = ?,
                    latest_snapshots_created = ?,
                    latest_api_requests_used = ?,
                    latest_rate_limit_warnings = ?,
                    latest_fallback_count = ?
                WHERE id = ?
                """,
                (
                    utc_now_iso(),
                    cycles_completed,
                    latest_scan_run_id,
                    latest_symbols_selected,
                    latest_symbols_scored,
                    latest_snapshots_created,
                    latest_api_requests_used,
                    latest_rate_limit_warnings,
                    latest_fallback_count,
                    run_id,
                ),
            )

    def update_watch_run_stopped(self, run_id: int, stop_reason: str) -> None:
        """Mark a watch run as cleanly stopped."""
        with connect(self.database_path) as conn:
            conn.execute(
                "UPDATE watch_runs SET stopped_at = ?, status = 'stopped', stop_reason = ? WHERE id = ?",
                (utc_now_iso(), str(stop_reason), run_id),
            )

    def update_watch_run_error(self, run_id: int, error_message: str) -> None:
        """Mark a watch run as stopped due to an error."""
        with connect(self.database_path) as conn:
            conn.execute(
                """
                UPDATE watch_runs SET
                    stopped_at = ?, status = 'error', latest_error_message = ?
                WHERE id = ?
                """,
                (utc_now_iso(), str(error_message)[:500], run_id),
            )

    def latest_watch_run(self) -> dict[str, Any] | None:
        """Return the most recent watch run record, or None."""
        with connect(self.database_path) as conn:
            row = conn.execute("SELECT * FROM watch_runs ORDER BY id DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    def recent_watch_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return recent watch run records ordered newest-first."""
        with connect(self.database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM watch_runs ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            return [dict(row) for row in rows]

    # ── Paper trading (orders + positions) ───────────────────────────────────────

    def record_paper_order(
        self, *, broker_order_id: str | None, account_label: str, symbol: str, side: str,
        qty: int, entry: float | None, stop: float | None, target: float | None,
        time_in_force: str, status: str, snapshot_id: int | None, reason: str | None,
        submitted_at: str,
    ) -> int:
        """Journal a submitted paper order. Returns the new row id."""
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO paper_orders (
                    broker_order_id, account_label, symbol, side, qty, entry, stop, target,
                    time_in_force, status, snapshot_id, reason, submitted_at, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (broker_order_id, account_label, str(symbol).upper(), side, int(qty), entry, stop,
                 target, time_in_force, status, snapshot_id, reason, submitted_at, utc_now_iso()),
            )
            return int(cursor.lastrowid)

    def count_paper_orders_today(self, *, account_label: str, day: str | None = None) -> int:
        """Count orders for an account submitted on a given YYYY-MM-DD (by submitted_at)."""
        day = day or utc_now_iso()[:10]
        with connect(self.database_path) as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM paper_orders WHERE account_label = ? AND substr(submitted_at, 1, 10) = ?",
                (account_label, day),
            ).fetchone()
            return int(row[0])

    def open_paper_position(
        self, *, account_label: str, symbol: str, qty: int, entry_price: float | None,
        stop: float | None, target: float | None, broker_order_id: str | None,
        snapshot_id: int | None, opened_at: str,
    ) -> int:
        """Record a newly opened paper position. Returns the new row id."""
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO paper_positions (
                    account_label, symbol, qty, entry_price, stop, target, status,
                    broker_order_id, snapshot_id, opened_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, ?)
                """,
                (account_label, str(symbol).upper(), int(qty), entry_price, stop, target,
                 broker_order_id, snapshot_id, opened_at),
            )
            return int(cursor.lastrowid)

    def close_paper_position(
        self, symbol: str, *, account_label: str, result: str, exit_price: float | None,
        realized_pl: float | None, closed_at: str,
    ) -> None:
        """Mark the open position for a symbol/account closed with its terminal outcome."""
        with connect(self.database_path) as conn:
            conn.execute(
                """
                UPDATE paper_positions
                SET status = 'closed', result = ?, exit_price = ?, realized_pl = ?, closed_at = ?
                WHERE account_label = ? AND symbol = ? AND status = 'open'
                """,
                (result, exit_price, realized_pl, closed_at, account_label, str(symbol).upper()),
            )

    def list_open_paper_positions(self, *, account_label: str | None = None) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            if account_label is None:
                rows = conn.execute("SELECT * FROM paper_positions WHERE status = 'open' ORDER BY id").fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM paper_positions WHERE status = 'open' AND account_label = ? ORDER BY id",
                    (account_label,),
                ).fetchall()
            return [dict(row) for row in rows]

    def open_paper_position_symbols(self, *, account_label: str) -> set[str]:
        with connect(self.database_path) as conn:
            rows = conn.execute(
                "SELECT symbol FROM paper_positions WHERE status = 'open' AND account_label = ?",
                (account_label,),
            ).fetchall()
            return {str(row[0]).upper() for row in rows}

    def sectors_for_symbols(self, symbols: Any) -> dict[str, str]:
        """Map UPPER(symbol) -> latest non-empty ``scan_results.sector``.

        Used by the sector-exposure cap to classify open positions + candidates. Reads
        the scanner's own classification (most complete for the live universe); symbols
        with no scanned sector are simply absent (caller falls back to the sector map).
        """
        syms = {str(s).upper() for s in (symbols or []) if s}
        if not syms:
            return {}
        placeholders = ",".join("?" for _ in syms)
        with connect(self.database_path) as conn:
            rows = conn.execute(
                f"SELECT symbol, sector FROM scan_results "
                f"WHERE UPPER(symbol) IN ({placeholders}) AND COALESCE(sector, '') != '' "
                f"ORDER BY scan_run_id DESC",
                tuple(syms),
            ).fetchall()
        out: dict[str, str] = {}
        for row in rows:
            sym = str(row[0]).upper()
            if sym not in out:  # first row per symbol = newest (ORDER BY scan_run_id DESC)
                out[sym] = str(row[1])
        return out

    def symbols_closed_today(self, *, account_label: str, day: str) -> set[str]:
        """Symbols with a paper position CLOSED on ``day`` (ET YYYY-MM-DD, by closed_at).

        Used by the re-entry guard so the bot does not immediately re-buy a name it
        just exited the same day (e.g. right after a stop fill is reconciled closed).
        """
        with connect(self.database_path) as conn:
            rows = conn.execute(
                "SELECT DISTINCT symbol FROM paper_positions "
                "WHERE account_label = ? AND status = 'closed' "
                "AND substr(COALESCE(closed_at, ''), 1, 10) = ?",
                (account_label, day),
            ).fetchall()
            return {str(row[0]).upper() for row in rows}

    def list_paper_positions(self, *, account_label: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            if account_label is None:
                rows = conn.execute("SELECT * FROM paper_positions ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM paper_positions WHERE account_label = ? ORDER BY id DESC LIMIT ?",
                    (account_label, limit),
                ).fetchall()
            return [dict(row) for row in rows]

    def triggerable_paper_picks(self, *, day: str, limit: int = 200) -> list[dict[str, Any]]:
        """Open snapshots whose entry triggered on ``day`` (ET date), with a valid plan.

        Used by the paper-trading watch hook to find picks to submit. Terminal rows
        (target/stop/closed) are excluded. entry/target/stop fall back from the frozen
        original_* plan to the working columns.
        """
        terminal = ("target_hit", "stop_hit", "closed", "expired", "invalidated")
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT id, symbol, original_entry_price, actual_entry_price,
                       original_target_price, target, original_stop_price, stop
                FROM candidate_snapshots
                WHERE entry_status = 'triggered'
                  AND substr(COALESCE(entry_triggered_at, actual_entry_time, ''), 1, 10) = ?
                  AND LOWER(COALESCE(tracking_status, '')) NOT IN (?, ?, ?, ?, ?)
                ORDER BY id DESC LIMIT ?
                """,
                (day, *terminal, limit),
            ).fetchall()
        picks: list[dict[str, Any]] = []
        for row in rows:
            entry = row["original_entry_price"] if row["original_entry_price"] is not None else row["actual_entry_price"]
            target = row["original_target_price"] if row["original_target_price"] is not None else row["target"]
            stop = row["original_stop_price"] if row["original_stop_price"] is not None else row["stop"]
            if entry and target and stop:
                picks.append({
                    "symbol": str(row["symbol"]).upper(), "entry": float(entry),
                    "stop": float(stop), "target": float(target), "snapshot_id": int(row["id"]),
                })
        return picks

    # ── Intraday bars (Kinetic Tape chart endpoint) ─────────────────────────────

    def upsert_intraday_bar(
        self, *, symbol: str, ts: str, open: float | None, high: float | None,
        low: float | None, close: float | None, volume: float | None,
    ) -> None:
        """Persist one polled intraday bar. Idempotent on (symbol, ts) — re-polling the
        same bar updates it in place. Fail-quiet callers swallow errors; here we let
        sqlite errors propagate so they are visible in tests."""
        with connect(self.database_path) as conn:
            conn.execute(
                """
                INSERT INTO intraday_bars (symbol, ts, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, ts) DO UPDATE SET
                    open = excluded.open, high = excluded.high, low = excluded.low,
                    close = excluded.close, volume = excluded.volume
                """,
                (str(symbol).upper(), ts, open, high, low, close, volume),
            )

    def list_intraday_bars(self, symbol: str, *, limit: int = 5000) -> list[dict[str, Any]]:
        """Return stored bars for a symbol oldest-first (chart-ready)."""
        with connect(self.database_path) as conn:
            rows = conn.execute(
                """
                SELECT symbol, ts, open, high, low, close, volume
                FROM intraday_bars WHERE symbol = ? ORDER BY ts ASC LIMIT ?
                """,
                (str(symbol).upper(), limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def latest_intraday_bar_ts(self, symbol: str) -> str | None:
        with connect(self.database_path) as conn:
            row = conn.execute(
                "SELECT MAX(ts) AS ts FROM intraday_bars WHERE symbol = ?",
                (str(symbol).upper(),),
            ).fetchone()
        return row["ts"] if row and row["ts"] else None

    def prune_intraday_bars(self, *, before_ts: str) -> int:
        """Delete bars with ts strictly older than ``before_ts`` (rolling retention).
        Returns the number of rows removed."""
        with connect(self.database_path) as conn:
            cursor = conn.execute("DELETE FROM intraday_bars WHERE ts < ?", (before_ts,))
            return int(cursor.rowcount)

    # ── Action audit + idempotency (control endpoints) ──────────────────────────

    def find_action_audit(self, *, action: str, idempotency_key: str) -> dict[str, Any] | None:
        """Return a prior audit row matching (action, idempotency_key), or None."""
        with connect(self.database_path) as conn:
            row = conn.execute(
                "SELECT * FROM action_audit WHERE action = ? AND idempotency_key = ? LIMIT 1",
                (action, idempotency_key),
            ).fetchone()
        return dict(row) if row else None

    def record_action_audit(
        self, *, action: str, actor: str = "dashboard", idempotency_key: str | None = None,
        result: str = "ok", detail: str | None = None,
    ) -> int:
        """Write an immutable audit row for a control action. Returns the new row id."""
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO action_audit (ts, action, actor, idempotency_key, result, detail)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (utc_now_iso(), action, actor, idempotency_key, result, detail),
            )
            return int(cursor.lastrowid)

    def list_action_audit(self, limit: int = 100) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            rows = conn.execute(
                "SELECT * FROM action_audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    # ── Personalization (pins / notes / presets / journal / ratings / alerts) ────

    def add_pin(self, symbol: str) -> None:
        with connect(self.database_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO pins (symbol, created_at) VALUES (?, ?)",
                (str(symbol).upper(), utc_now_iso()),
            )

    def remove_pin(self, symbol: str) -> None:
        with connect(self.database_path) as conn:
            conn.execute("DELETE FROM pins WHERE symbol = ?", (str(symbol).upper(),))

    def list_pins(self) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            rows = conn.execute("SELECT * FROM pins ORDER BY created_at DESC").fetchall()
        return [dict(row) for row in rows]

    def add_note(self, *, symbol: str, body: str) -> int:
        now = utc_now_iso()
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                "INSERT INTO notes (symbol, body, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (str(symbol).upper(), body, now, now),
            )
            return int(cursor.lastrowid)

    def list_notes(self, *, symbol: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM notes WHERE symbol = ? ORDER BY id DESC LIMIT ?",
                    (str(symbol).upper(), limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM notes ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def upsert_preset(self, *, name: str, payload_json: str) -> int:
        now = utc_now_iso()
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO presets (name, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET payload_json = excluded.payload_json, updated_at = excluded.updated_at
                """,
                (name, payload_json, now, now),
            )
            return int(cursor.lastrowid or 0)

    def list_presets(self) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            rows = conn.execute("SELECT * FROM presets ORDER BY name ASC").fetchall()
        return [dict(row) for row in rows]

    def add_journal_entry(self, *, symbol: str | None, entry: str) -> int:
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                "INSERT INTO journal (symbol, entry, created_at) VALUES (?, ?, ?)",
                (str(symbol).upper() if symbol else None, entry, utc_now_iso()),
            )
            return int(cursor.lastrowid)

    def list_journal(self, limit: int = 200) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            rows = conn.execute("SELECT * FROM journal ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def add_call_rating(self, *, symbol: str, rating: int, note: str | None = None) -> int:
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                "INSERT INTO call_ratings (symbol, rating, note, created_at) VALUES (?, ?, ?, ?)",
                (str(symbol).upper(), int(rating), note, utc_now_iso()),
            )
            return int(cursor.lastrowid)

    def list_call_ratings(self, *, symbol: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            if symbol:
                rows = conn.execute(
                    "SELECT * FROM call_ratings WHERE symbol = ? ORDER BY id DESC LIMIT ?",
                    (str(symbol).upper(), limit),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM call_ratings ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def add_price_alert(self, *, symbol: str, target_price: float, direction: str = "above") -> int:
        with connect(self.database_path) as conn:
            cursor = conn.execute(
                """
                INSERT INTO price_alerts (symbol, target_price, direction, active, created_at)
                VALUES (?, ?, ?, 1, ?)
                """,
                (str(symbol).upper(), float(target_price), direction, utc_now_iso()),
            )
            return int(cursor.lastrowid)

    def list_price_alerts(self, *, active_only: bool = False, limit: int = 200) -> list[dict[str, Any]]:
        with connect(self.database_path) as conn:
            if active_only:
                rows = conn.execute(
                    "SELECT * FROM price_alerts WHERE active = 1 ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM price_alerts ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    def deactivate_price_alert(self, alert_id: int) -> None:
        with connect(self.database_path) as conn:
            conn.execute("UPDATE price_alerts SET active = 0 WHERE id = ?", (int(alert_id),))

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _recent_snapshot_exists(self, conn: Any, symbol: str, setup_category: str, dedupe_minutes: int) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=dedupe_minutes)).replace(microsecond=0).isoformat()
        row = conn.execute(
            """
            SELECT id FROM candidate_snapshots
            WHERE symbol = ? AND setup_category = ? AND snapshot_time >= ?
            LIMIT 1
            """,
            (symbol, setup_category, cutoff),
        ).fetchone()
        return row is not None

    def _demo_snapshot_exists(self, conn: Any, symbol: str, notes: str) -> bool:
        prefix = notes.split(" - ", 1)[0] if notes else "Demo seeded snapshot"
        row = conn.execute(
            """
            SELECT id FROM candidate_snapshots
            WHERE symbol = ? AND notes LIKE ?
            LIMIT 1
            """,
            (symbol.upper(), f"{prefix}%"),
        ).fetchone()
        return row is not None


def _bool_to_int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return int(bool(value))
