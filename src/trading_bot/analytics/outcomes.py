from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd


TARGET_OUTCOMES = {"target_hit", "target_before_stop"}
STOP_OUTCOMES = {"stop_hit", "stop_before_target"}
FAILURE_OUTCOMES = {"stop_hit", "stop_before_target", "failed_setup"}
PARTIAL_OUTCOMES = {"partial_move"}
NO_TRIGGER_OUTCOMES = {"entry_not_triggered", "expired_no_trigger"}
INSUFFICIENT_OUTCOMES = {"insufficient_future_data"}
RETURN_COLUMNS = ["result_eod", "result_3d", "result_5d", "result_10d", "result_20d"]
MARKET_TIMEZONE = "America/New_York"
MARKET_TZ = ZoneInfo(MARKET_TIMEZONE)


@dataclass(frozen=True)
class OutcomeAnalytics:
    """Calculate research summaries from candidate snapshots."""

    snapshots: pd.DataFrame
    include_seeded_demo: bool = False
    real_only: bool = True
    include_demo: bool = False
    include_legacy: bool = False
    exclude_demo: bool = False
    today: bool = False
    provider: str | None = None

    def prepared(self) -> pd.DataFrame:
        """Return normalized snapshots with seeded fixtures filtered as configured."""
        data = self.snapshots.copy()
        if data.empty:
            return data
        for column in (
            "notes",
            "tags_json",
            "warnings_json",
            "outcome_label",
            "snapshot_provider",
            "tony_data_quality_read",
            "snapshot_time",
            "data_source",
            "data_source_provider",
            "used_demo_data",
            "used_fallback_data",
            "real_data_only_run",
            "missing_real_data_reason",
        ):
            if column not in data.columns:
                data[column] = "" if column != "tags_json" and column != "warnings_json" else "[]"
        data["is_seeded_demo"] = data.apply(_is_seeded_demo_row, axis=1)
        data["data_source_classification"] = data.apply(classify_snapshot_data_source, axis=1)
        if not self.include_seeded_demo:
            data = data[~data["is_seeded_demo"]].copy()
        if self.exclude_demo or not self.include_demo:
            data = data[~data["data_source_classification"].eq("demo_generated")].copy()
        if not self.include_legacy:
            data = data[~data["data_source_classification"].eq("legacy_unknown")].copy()
        data = data[~data["data_source_classification"].eq("missing_real_data")].copy()
        if self.real_only:
            data = data[data["data_source_classification"].isin({"real_alpaca", "recorded_real_fixture"})].copy()
        if self.provider:
            data = data[data["snapshot_provider"].fillna("").eq(self.provider)].copy()
        if self.today:
            today = new_york_market_date()
            data = data[_market_date_mask(data["snapshot_time"], today)].copy()
        data["score_bucket"] = data["total_score"].apply(score_bucket)
        data["outcome_label"] = data["outcome_label"].fillna("unreviewed")
        data["entry_triggered"] = data["entry_triggered"].fillna(0).astype(int)
        for column in RETURN_COLUMNS + ["total_score"]:
            if column in data.columns:
                data[column] = pd.to_numeric(data[column], errors="coerce")
        return data

    def grouped_by(self, column: str) -> pd.DataFrame:
        """Summarize outcome performance by a dataframe column."""
        data = self.prepared()
        if data.empty or column not in data.columns:
            return _empty_summary(column)
        rows = []
        for group_value, group in data.groupby(column, dropna=False):
            rows.append(_summary_row(column, group_value, group))
        result = pd.DataFrame(rows)
        return result.sort_values(["total_snapshots", column], ascending=[False, True]).reset_index(drop=True)

    def warning_type_summary(self) -> pd.DataFrame:
        """Summarize outcomes by parsed warning text."""
        data = self.prepared()
        if data.empty:
            return _empty_summary("warning_type")
        rows: list[dict[str, Any]] = []
        for _, snapshot in data.iterrows():
            warnings = _safe_json_list(snapshot.get("warnings_json"))
            if not warnings:
                warnings = ["No warning"]
            for warning in warnings:
                item = snapshot.to_dict()
                item["warning_type"] = warning
                rows.append(item)
        expanded = pd.DataFrame(rows)
        if expanded.empty:
            return _empty_summary("warning_type")
        summary_rows = [
            _summary_row("warning_type", warning, group)
            for warning, group in expanded.groupby("warning_type", dropna=False)
        ]
        return pd.DataFrame(summary_rows).sort_values(["total_snapshots", "warning_type"], ascending=[False, True]).reset_index(drop=True)

    def tag_summary(self) -> pd.DataFrame:
        """Summarize outcomes by parsed symbol tag."""
        data = self.prepared()
        if data.empty:
            return _empty_summary("tag")
        rows: list[dict[str, Any]] = []
        for _, snapshot in data.iterrows():
            tags = _safe_json_list(snapshot.get("tags_json"))
            for tag in tags or ["untagged"]:
                item = snapshot.to_dict()
                item["tag"] = tag
                rows.append(item)
        expanded = pd.DataFrame(rows)
        if expanded.empty:
            return _empty_summary("tag")
        summary_rows = [
            _summary_row("tag", tag, group)
            for tag, group in expanded.groupby("tag", dropna=False)
        ]
        return pd.DataFrame(summary_rows).sort_values(["total_snapshots", "tag"], ascending=[False, True]).reset_index(drop=True)

    def outcome_counts(self) -> pd.DataFrame:
        """Count outcome labels after seeded-demo filtering."""
        data = self.prepared()
        if data.empty:
            return pd.DataFrame(columns=["outcome_label", "count"])
        return (
            data["outcome_label"]
            .fillna("unreviewed")
            .value_counts()
            .rename_axis("outcome_label")
            .reset_index(name="count")
        )

    def data_source_counts(self) -> pd.DataFrame:
        """Count snapshots by derived data-source class after active filters."""
        data = self.prepared()
        if data.empty:
            return pd.DataFrame(columns=["data_source_classification", "count"])
        return (
            data["data_source_classification"]
                .fillna("legacy_unknown")
            .value_counts()
            .rename_axis("data_source_classification")
            .reset_index(name="count")
        )

    def raw_data_source_counts(self) -> pd.DataFrame:
        """Count snapshots by derived data-source class before active source filters."""
        data = self.classified_snapshots()
        if data.empty:
            return pd.DataFrame(columns=["data_source_classification", "count"])
        return (
            data["data_source_classification"]
            .fillna("legacy_unknown")
            .value_counts()
            .rename_axis("data_source_classification")
            .reset_index(name="count")
        )

    def classified_snapshots(self) -> pd.DataFrame:
        """Return snapshots with seeded-demo and data-source classification added.

        This is the raw history view used for reconciliation and exclusion reporting.
        No real/demo/legacy/missing filters are applied beyond the seeded-demo toggle.
        """
        data = self.snapshots.copy()
        if data.empty:
            return data
        for column in (
            "notes",
            "tags_json",
            "warnings_json",
            "snapshot_provider",
            "tony_data_quality_read",
            "data_source",
            "data_source_provider",
            "used_demo_data",
            "used_fallback_data",
            "missing_real_data_reason",
        ):
            if column not in data.columns:
                data[column] = "" if column not in {"tags_json", "warnings_json"} else "[]"
        data["is_seeded_demo"] = data.apply(_is_seeded_demo_row, axis=1)
        data["data_source_classification"] = data.apply(classify_snapshot_data_source, axis=1)
        if not self.include_seeded_demo:
            data = data[~data["is_seeded_demo"]].copy()
        return data

    def exclusion_counts(self) -> dict[str, int]:
        """Return counts excluded from default real-data-only analytics."""
        raw = self.raw_data_source_counts()
        counts = {str(row["data_source_classification"]): int(row["count"]) for _, row in raw.iterrows()}
        return {
            "real_rows": counts.get("real_alpaca", 0) + counts.get("recorded_real_fixture", 0),
            "demo_rows_excluded": counts.get("demo_generated", 0),
            "legacy_unknown_rows_excluded": counts.get("legacy_unknown", 0),
            "missing_real_data_rows_excluded": counts.get("missing_real_data", 0),
        }

    def daily_tony_memory_summary(
        self,
        *,
        report_date: str | None = None,
        reconciliation: dict[str, int] | None = None,
        exclusions: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Build a research-only daily memory summary from filtered rows."""
        return build_daily_tony_memory_summary(
            self.prepared(),
            report_date=report_date,
            reconciliation=reconciliation,
            exclusions=exclusions,
        )

    def tony_self_review(
        self,
        memory_summary: dict[str, Any],
        *,
        reconciliation: dict[str, int] | None = None,
    ) -> dict[str, Any]:
        """Build a plain-English self-review from filtered real-only rows."""
        return build_tony_self_review(
            self.prepared(),
            memory_summary,
            reconciliation=reconciliation,
        )


def score_bucket(score: float | int | None) -> str:
    """Assign a 0-100 score into research buckets."""
    value = float(score or 0)
    if value >= 90:
        return "90-100"
    if value >= 80:
        return "80-89"
    if value >= 70:
        return "70-79"
    if value >= 60:
        return "60-69"
    return "below 60"


def classify_snapshot_data_source(row: pd.Series) -> str:
    """Classify a candidate snapshot using existing nullable metadata.

    Returns one of: real_alpaca, missing_real_data, recorded_real_fixture,
    legacy_unknown, or demo_generated for old demo rows.
    """
    explicit_source = str(row.get("data_source") or "").lower()
    if explicit_source in {"real_alpaca", "missing_real_data", "recorded_real_fixture", "demo_generated", "legacy_unknown"}:
        return explicit_source
    provider = str(row.get("snapshot_provider") or row.get("provider") or "").lower()
    source_provider = str(row.get("data_source_provider") or "").lower()
    notes = str(row.get("notes") or "").lower()
    dq = str(row.get("tony_data_quality_read") or "").lower()
    tags = {str(tag).lower() for tag in _safe_json_list(row.get("tags_json"))}
    warnings = " | ".join(str(item).lower() for item in _safe_json_list(row.get("warnings_json")))
    used_demo = _truthy(row.get("used_demo_data"))
    used_fallback = _truthy(row.get("used_fallback_data"))
    missing_reason = str(row.get("missing_real_data_reason") or "").lower()
    if _is_seeded_demo_row(row):
        return "demo_generated"
    if missing_reason or explicit_source == "missing_real_data":
        return "missing_real_data"
    if "recorded_real_fixture" in {explicit_source, source_provider, provider}:
        return "recorded_real_fixture"
    demo_markers = (
        "demo data only" in warnings
        or "demo-generated" in warnings
        or "demo_generated" in provider
        or "demo_generated" in source_provider
        or "demo_data" == dq
        or "demo" in tags
        or "demo seeded" in notes
        or used_demo
    )
    fallback_markers = (
        "fallback" in warnings
        or "fallback" in dq
        or "fallback" in provider
        or "fallback" in source_provider
        or "fallback_data" == dq
        or "intraday_fallback_demo" == dq
        or used_fallback
    )
    real_markers = (
        provider == "alpaca_iex"
        or source_provider == "alpaca_iex"
        or dq in {"daily_real_alpaca", "intraday_real_alpaca"}
    )
    if demo_markers:
        return "demo_generated"
    if fallback_markers:
        return "missing_real_data"
    if real_markers:
        return "real_alpaca"
    return "legacy_unknown"


def build_daily_tony_memory_summary(
    rows: pd.DataFrame,
    *,
    report_date: str | None = None,
    reconciliation: dict[str, int] | None = None,
    exclusions: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Summarize one day's real-only research memory without changing strategy logic."""
    data = rows.copy()
    if data.empty:
        return {
            "report_date": report_date,
            "row_count": 0,
            "setup_counts": {},
            "triggered_count": 0,
            "active_count": int((reconciliation or {}).get("deduped_active_positions", 0)),
            "closed_count": int((reconciliation or {}).get("deduped_closed_results", 0)),
            "target_hit_count": int((reconciliation or {}).get("target_hits", 0)),
            "stop_hit_count": int((reconciliation or {}).get("stop_hits", 0)),
            "partial_move_count": int((reconciliation or {}).get("partial_moves", 0)),
            "reassessment_label_counts": {},
            "best_setup_note": "No real-only rows were available for Tony memory today.",
            "worst_setup_note": "No real-only rows were available for Tony memory today.",
            "data_quality_notes": _memory_data_quality_notes(0, reconciliation, exclusions),
        }

    for column in ("setup_category", "outcome_label", "tracking_status", "entry_status", "reassessment_label"):
        if column not in data.columns:
            data[column] = ""
        data[column] = data[column].fillna("").astype(str)
    for column in ("entry_triggered", "actual_entry_price", "original_entry_price", "result_5d"):
        if column not in data.columns:
            data[column] = 0
        data[column] = pd.to_numeric(data[column], errors="coerce")

    setup_counts = (
        data["setup_category"]
        .replace("", "Unspecified setup")
        .value_counts()
        .sort_index()
        .to_dict()
    )
    triggered_mask = _memory_triggered_mask(data)
    closed_mask = _memory_closed_mask(data)
    target_mask = data["outcome_label"].isin(TARGET_OUTCOMES)
    stop_mask = data["outcome_label"].isin(STOP_OUTCOMES)
    partial_mask = data["outcome_label"].isin(PARTIAL_OUTCOMES)

    best_setup_note, worst_setup_note = _best_worst_setup_notes(data)
    reassessment_counts = (
        data["reassessment_label"]
        .replace("", pd.NA)
        .dropna()
        .value_counts()
        .sort_index()
        .to_dict()
    )

    return {
        "report_date": report_date,
        "row_count": int(len(data)),
        "setup_counts": {str(key): int(value) for key, value in setup_counts.items()},
        "triggered_count": int(triggered_mask.sum()),
        "active_count": int((reconciliation or {}).get("deduped_active_positions", _memory_active_count(data))),
        "closed_count": int((reconciliation or {}).get("deduped_closed_results", closed_mask.sum())),
        "target_hit_count": int((reconciliation or {}).get("target_hits", target_mask.sum())),
        "stop_hit_count": int((reconciliation or {}).get("stop_hits", stop_mask.sum())),
        "partial_move_count": int((reconciliation or {}).get("partial_moves", partial_mask.sum())),
        "reassessment_label_counts": {str(key): int(value) for key, value in reassessment_counts.items()},
        "best_setup_note": best_setup_note,
        "worst_setup_note": worst_setup_note,
        "data_quality_notes": _memory_data_quality_notes(len(data), reconciliation, exclusions),
    }


def _memory_triggered_mask(data: pd.DataFrame) -> pd.Series:
    entry_status = data["entry_status"].str.lower()
    outcome_label = data["outcome_label"].str.lower()
    entry_triggered = data["entry_triggered"].fillna(0)
    return (
        entry_status.eq("triggered")
        | entry_triggered.ge(1)
        | data["actual_entry_price"].notna()
        | data["original_entry_price"].notna()
        | outcome_label.isin(TARGET_OUTCOMES | STOP_OUTCOMES | PARTIAL_OUTCOMES | FAILURE_OUTCOMES | {"still_open"})
    )


def _memory_active_count(data: pd.DataFrame) -> int:
    tracking_status = data["tracking_status"].str.lower()
    outcome_label = data["outcome_label"].str.lower()
    return int((tracking_status.eq("active") | outcome_label.eq("still_open")).sum())


def _memory_closed_mask(data: pd.DataFrame) -> pd.Series:
    tracking_status = data["tracking_status"].str.lower()
    outcome_label = data["outcome_label"].str.lower()
    closed_outcomes = TARGET_OUTCOMES | STOP_OUTCOMES | PARTIAL_OUTCOMES | NO_TRIGGER_OUTCOMES | INSUFFICIENT_OUTCOMES | FAILURE_OUTCOMES
    return tracking_status.isin({"closed", "expired", "invalidated"}) | outcome_label.isin(closed_outcomes)


def _best_worst_setup_notes(data: pd.DataFrame) -> tuple[str, str]:
    if data.empty or "setup_category" not in data.columns:
        return (
            "No real-only setup groups were available for Tony memory today.",
            "No real-only setup groups were available for Tony memory today.",
        )
    rows: list[dict[str, Any]] = []
    for setup_name, group in data.groupby("setup_category", dropna=False):
        setup = str(setup_name or "Unspecified setup")
        triggered = int(_memory_triggered_mask(group).sum())
        if triggered <= 0:
            continue
        target_hits = int(group["outcome_label"].isin(TARGET_OUTCOMES).sum())
        stop_hits = int(group["outcome_label"].isin(STOP_OUTCOMES | FAILURE_OUTCOMES).sum())
        partial_moves = int(group["outcome_label"].isin(PARTIAL_OUTCOMES).sum())
        mean_result = float(group["result_5d"].dropna().mean()) if group["result_5d"].notna().any() else 0.0
        score = (target_hits + (0.5 * partial_moves) - stop_hits) / max(triggered, 1)
        rows.append(
            {
                "setup": setup,
                "triggered": triggered,
                "target_hits": target_hits,
                "stop_hits": stop_hits,
                "partial_moves": partial_moves,
                "mean_result_5d": mean_result,
                "score": score,
            }
        )
    if not rows:
        note = "No triggered real-only setups were available to rank in Tony memory today."
        return note, note
    ranked = pd.DataFrame(rows).sort_values(
        ["score", "target_hits", "partial_moves", "mean_result_5d", "setup"],
        ascending=[False, False, False, False, True],
    ).reset_index(drop=True)
    best = ranked.iloc[0]
    worst = ranked.sort_values(
        ["score", "stop_hits", "target_hits", "mean_result_5d", "setup"],
        ascending=[True, False, True, True, True],
    ).reset_index(drop=True).iloc[0]
    best_note = (
        f"Preliminary best follow-through: {best['setup']} recorded "
        f"{int(best['target_hits'])} target hit(s) and {int(best['partial_moves'])} partial move(s) "
        f"across {int(best['triggered'])} triggered row(s)."
    )
    worst_note = (
        f"Preliminary weakest follow-through: {worst['setup']} logged "
        f"{int(worst['stop_hits'])} stop/failure outcome(s) across {int(worst['triggered'])} triggered row(s)."
    )
    return best_note, worst_note


def _memory_data_quality_notes(
    row_count: int,
    reconciliation: dict[str, int] | None,
    exclusions: dict[str, int] | None,
) -> list[str]:
    notes = [
        "Tony memory is research-only. It does not change scoring, trigger rules, or trading behavior automatically."
    ]
    if row_count <= 0:
        notes.append("No real-only rows were available for this memory summary.")
    else:
        notes.append("This memory summary only uses filtered real-only rows.")
    if reconciliation:
        history_hidden = int(reconciliation.get("history_rows_hidden_from_product_views", 0) or 0)
        incomplete_hidden = int(reconciliation.get("incomplete_rows_hidden_from_product_views", 0) or 0)
        if history_hidden > 0:
            notes.append(
                f"{history_hidden} historical row(s) stayed in raw history but were hidden from current product views."
            )
        if incomplete_hidden > 0:
            notes.append(
                f"{incomplete_hidden} incomplete row(s) were hidden from product views and preserved in raw history."
            )
    if exclusions:
        demo_rows = int(exclusions.get("demo_rows_excluded", 0) or 0)
        legacy_rows = int(exclusions.get("legacy_unknown_rows_excluded", 0) or 0)
        missing_rows = int(exclusions.get("missing_real_data_rows_excluded", 0) or 0)
        if demo_rows > 0:
            notes.append(f"{demo_rows} demo row(s) were excluded.")
        if legacy_rows > 0:
            notes.append(f"{legacy_rows} legacy/unknown row(s) were excluded.")
        if missing_rows > 0:
            notes.append(f"{missing_rows} fallback or missing real-data row(s) were excluded.")
    return notes


def build_tony_self_review(
    rows: pd.DataFrame,
    memory_summary: dict[str, Any],
    *,
    reconciliation: dict[str, int] | None = None,
) -> dict[str, Any]:
    """Generate a plain-English daily self-review from real-only rows and memory summary.

    Derives what worked, what failed, what needs more data, and what to watch tomorrow.
    Research-only. Does not change scoring, trigger rules, or trading behavior.
    """
    if rows.empty:
        return _empty_self_review()

    data = rows.copy()
    for column in ("setup_category", "outcome_label", "tracking_status", "entry_status", "reassessment_label"):
        if column not in data.columns:
            data[column] = ""
        data[column] = data[column].fillna("").astype(str)

    what_worked: list[str] = []
    what_failed: list[str] = []
    needs_more_data: list[str] = []

    for setup_name, group in data.groupby("setup_category", dropna=False):
        setup = str(setup_name or "Unspecified setup")
        triggered = int(_memory_triggered_mask(group).sum())
        total = len(group)
        if triggered <= 0 or total <= 0:
            continue
        target_hits = int(group["outcome_label"].isin(TARGET_OUTCOMES).sum())
        stop_hits = int(group["outcome_label"].isin(STOP_OUTCOMES | FAILURE_OUTCOMES).sum())
        partial = int(group["outcome_label"].isin(PARTIAL_OUTCOMES).sum())

        if target_hits > 0:
            note = f"{setup}: {target_hits} target hit(s)"
            if partial > 0:
                note += f", {partial} partial move(s)"
            what_worked.append(note + f" out of {triggered} triggered row(s).")
        if stop_hits > 0:
            what_failed.append(
                f"{setup}: {stop_hits} stop or failure outcome(s) out of {triggered} triggered row(s)."
            )
        if triggered < 2 and target_hits == 0 and stop_hits == 0:
            needs_more_data.append(
                f"{setup}: only {total} row(s) today — not enough context to read direction."
            )

    needs_review_setups = (
        data[data["reassessment_label"].eq("needs_review")]["setup_category"]
        .unique()
        .tolist()
    )
    for setup in needs_review_setups:
        entry = f"{setup}: reassessment flagged as needs_review — check current conditions."
        if entry not in needs_more_data:
            needs_more_data.append(entry)

    tomorrow_watch: list[str] = []
    active_count = int(
        (data["tracking_status"].eq("active") | data["outcome_label"].eq("still_open")).sum()
    )
    pending_count = int((reconciliation or {}).get("pending_triggers", 0) or 0)
    label_counts = memory_summary.get("reassessment_label_counts") or {}
    weakening_count = int(label_counts.get("weakening", 0) or 0)
    invalidated_count = int(label_counts.get("invalidated", 0) or 0)

    if active_count > 0:
        tomorrow_watch.append(
            f"{active_count} active position(s) carry over — check reassessment labels at next open."
        )
    if pending_count > 0:
        tomorrow_watch.append(
            f"{pending_count} pending trigger(s) still waiting — watch for intraday trigger levels."
        )
    if weakening_count > 0:
        tomorrow_watch.append(
            f"{weakening_count} setup(s) flagged weakening — monitor for further deterioration."
        )
    if invalidated_count > 0:
        tomorrow_watch.append(
            f"{invalidated_count} setup(s) invalidated today — review before next scan."
        )
    if not tomorrow_watch:
        tomorrow_watch.append("No specific items flagged for tomorrow based on today's real-only data.")

    if not what_worked:
        what_worked.append("No setups recorded a target or partial hit in today's real-only rows.")
    if not what_failed:
        what_failed.append("No setups recorded a stop or failure outcome in today's real-only rows.")
    if not needs_more_data:
        needs_more_data.append("All active setups had enough data to classify today.")

    return {
        "strongest_setup": memory_summary.get(
            "best_setup_note", "No best setup note available."
        ),
        "weakest_setup": memory_summary.get(
            "worst_setup_note", "No weakest setup note available."
        ),
        "what_worked": what_worked,
        "what_failed": what_failed,
        "needs_more_data": needs_more_data,
        "tomorrow_watch": tomorrow_watch,
        "research_only": True,
    }


def _empty_self_review() -> dict[str, Any]:
    return {
        "strongest_setup": "No real-only rows were available for Tony self-review today.",
        "weakest_setup": "No real-only rows were available for Tony self-review today.",
        "what_worked": ["No real-only rows were available today."],
        "what_failed": ["No real-only rows were available today."],
        "needs_more_data": ["All setups need real data before patterns can emerge."],
        "tomorrow_watch": ["No specific items flagged — check tomorrow's scan results."],
        "research_only": True,
    }


def new_york_market_date(now: pd.Timestamp | None = None) -> str:
    """Return the current market date in America/New_York."""
    timestamp = now if now is not None else pd.Timestamp.now(tz=MARKET_TZ)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize("UTC")
    else:
        timestamp = timestamp.tz_convert(MARKET_TZ)
    return timestamp.strftime("%Y-%m-%d")


def market_date_mask(values: pd.Series, market_date: str) -> pd.Series:
    """Public wrapper for ET market-date filtering against stored timestamps."""
    return _market_date_mask(values, market_date)


def _market_date_mask(values: pd.Series, market_date: str) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce", utc=True)
    local_dates = parsed.dt.tz_convert(MARKET_TZ).dt.strftime("%Y-%m-%d")
    return local_dates.eq(market_date).fillna(False)
    return "legacy_unknown"


def _summary_row(group_column: str, group_value: Any, group: pd.DataFrame) -> dict[str, Any]:
    outcomes = group["outcome_label"].fillna("unreviewed")
    enough_data = group[~outcomes.isin(INSUFFICIENT_OUTCOMES | {"unreviewed"})]
    enough_count = len(enough_data)
    target_count = int(outcomes.isin(TARGET_OUTCOMES).sum())
    failure_count = int(outcomes.isin(FAILURE_OUTCOMES).sum())
    row = {
        group_column: str(group_value),
        "total_snapshots": int(len(group)),
        "entry_triggered_count": int(group["entry_triggered"].fillna(0).astype(int).sum()),
        "target_hit_count": target_count,
        "stop_hit_count": int(outcomes.isin(STOP_OUTCOMES).sum()),
        "partial_move_count": int(outcomes.isin(PARTIAL_OUTCOMES).sum()),
        "failed_setup_count": int((outcomes == "failed_setup").sum()),
        "entry_not_triggered_count": int(outcomes.isin(NO_TRIGGER_OUTCOMES).sum()),
        "insufficient_future_data_count": int(outcomes.isin(INSUFFICIENT_OUTCOMES).sum()),
        "average_score": _mean_or_none(group.get("total_score")),
        "target_hit_rate": round(target_count / enough_count, 4) if enough_count else 0.0,
        "failure_rate": round(failure_count / enough_count, 4) if enough_count else 0.0,
    }
    for column in RETURN_COLUMNS:
        row[f"average_{column}"] = _mean_or_none(group.get(column))
    return row


def _empty_summary(group_column: str) -> pd.DataFrame:
    columns = [
        group_column,
        "total_snapshots",
        "entry_triggered_count",
        "target_hit_count",
        "stop_hit_count",
        "partial_move_count",
        "failed_setup_count",
        "entry_not_triggered_count",
        "insufficient_future_data_count",
        "average_score",
        "target_hit_rate",
        "failure_rate",
    ] + [f"average_{column}" for column in RETURN_COLUMNS]
    return pd.DataFrame(columns=columns)


def _mean_or_none(series: pd.Series | None) -> float | None:
    if series is None:
        return None
    numeric = pd.to_numeric(series, errors="coerce").dropna()
    if numeric.empty:
        return None
    return round(float(numeric.mean()), 6)


def _is_seeded_demo_row(row: pd.Series) -> bool:
    notes = str(row.get("notes") or "").lower()
    category = str(row.get("setup_category") or "").lower()
    tags = {str(tag).lower() for tag in _safe_json_list(row.get("tags_json"))}
    return (
        "demo seeded snapshot" in notes
        or "seeded demo snapshot" in notes
        or category == "demo outcome fixture"
        or bool({"demo_seeded", "outcome_fixture"} & tags)
    )


def _safe_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    try:
        parsed = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
