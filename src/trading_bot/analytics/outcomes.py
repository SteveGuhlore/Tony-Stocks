from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pandas as pd


TARGET_OUTCOMES = {"target_hit", "target_before_stop"}
STOP_OUTCOMES = {"stop_hit", "stop_before_target"}
FAILURE_OUTCOMES = {"stop_hit", "stop_before_target", "failed_setup"}
PARTIAL_OUTCOMES = {"partial_move"}
NO_TRIGGER_OUTCOMES = {"entry_not_triggered", "expired_no_trigger"}
INSUFFICIENT_OUTCOMES = {"insufficient_future_data"}
RETURN_COLUMNS = ["result_eod", "result_3d", "result_5d", "result_10d", "result_20d"]


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
            today = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
            data = data[data["snapshot_time"].fillna("").astype(str).str.slice(0, 10).eq(today)].copy()
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
