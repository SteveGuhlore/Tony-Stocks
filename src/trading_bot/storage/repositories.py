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
    ) -> list[int]:
        """Create candidate snapshots from scored scan results."""
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
                cursor = conn.execute(
                    """
                    INSERT INTO candidate_snapshots (
                        scan_run_id, symbol, snapshot_time, universe_role, tags_json, setup_category,
                        total_score, close, entry, stop, target, risk_reward, dollar_volume,
                        relative_volume, atr_percent, trade_plan_valid, trade_plan_status,
                        reasons_json, warnings_json, candidate_summary,
                        status, entry_trigger_price, entry_triggered
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        result.suggested_entry,
                        0,
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
                SELECT * FROM candidate_snapshots
                {clause}
                ORDER BY snapshot_time DESC, total_score DESC
                LIMIT ?
                """,
                params,
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
                    notes
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
