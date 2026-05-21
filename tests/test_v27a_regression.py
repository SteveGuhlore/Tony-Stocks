"""V27A regression tests — V26D data integrity rules must hold after V27 visual redesign."""

import pandas as pd

from trading_bot.dashboard.helpers import (
    build_active_tracking_product_rows,
    build_pick_card_model,
    build_results_product_rows,
    build_stale_tracking_rows,
    build_tony_watchlist_rows,
    collect_health_issues,
    derive_pick_phase,
    find_unreconciled_tracked_symbols,
)


def _real_row(symbol: str, **kwargs: object) -> dict:
    base: dict = {
        "symbol": symbol,
        "snapshot_time": "2026-05-20T15:00:00+00:00",
        "entry_status": "pending",
        "entry_triggered": 0,
        "planned_entry_price": 50.0,
        "planned_entry_rule": "break_above_high",
        "target": 58.0,
        "stop": 46.0,
        "outcome_label": "unreviewed",
        "data_source": "real_alpaca",
        "snapshot_provider": "alpaca_iex",
        "tony_data_quality_read": "daily_real_alpaca",
        "used_fallback_data": 0,
        "used_demo_data": 0,
        "tony_priority_label": "high_priority",
        "tony_analysis_version": "v1",
    }
    base.update(kwargs)
    return base


def _active_row(symbol: str, **kwargs: object) -> dict:
    base: dict = {
        "symbol": symbol,
        "snapshot_time": "2026-05-19T15:00:00+00:00",
        "entry_status": "triggered",
        "entry_triggered": 1,
        "original_entry_price": 100.0,
        "actual_entry_price": 100.0,
        "tracking_started_at": "2026-05-19T14:30:00+00:00",
        "current_price": 103.0,
        "target": 110.0,
        "stop": 95.0,
        "outcome_label": "still_open",
        "tracking_status": "active",
        "reassessment_label": "still_valid",
        "data_source": "real_alpaca",
        "tony_data_quality_read": "daily_real_alpaca",
        "used_demo_data": 0,
    }
    base.update(kwargs)
    return base


def _stale_row(symbol: str, **kwargs: object) -> dict:
    base: dict = {
        "symbol": symbol,
        "snapshot_time": "2026-05-19T15:00:00+00:00",
        "entry_status": "triggered",
        "entry_triggered": 1,
        "original_entry_price": 100.0,
        "original_target_price": 112.0,
        "original_stop_price": 93.0,
        "tracking_started_at": "2026-05-19T14:30:00+00:00",
        "outcome_label": "still_open",
        "tracking_status": "missing_real_data",
        "data_source": "missing_real_data",
        "missing_real_data_reason": "provider returned empty bars",
        "tony_data_quality_read": "missing_real_data",
        "used_demo_data": 0,
    }
    base.update(kwargs)
    return base


class TestV27ADataQualityFilters:
    """Demo/fake/missing rows must be hidden from Watchlist and Results after V27 redesign."""

    def test_demo_row_hidden_from_watchlist(self) -> None:
        df = pd.DataFrame([
            _real_row("ARM"),
            {"symbol": "HCP", "data_source": "demo_generated", "snapshot_provider": "demo_generated",
             "tony_data_quality_read": "demo_data", "used_demo_data": 1,
             "entry_triggered": 0, "target": 58.0, "stop": 46.0, "outcome_label": "unreviewed"},
        ])
        watchlist = build_tony_watchlist_rows(df)
        symbols = [] if watchlist.empty else list(watchlist["symbol"].astype(str).str.upper())
        assert "HCP" not in symbols
        assert "ARM" in symbols

    def test_missing_real_data_pick_hidden_from_watchlist(self) -> None:
        df = pd.DataFrame([
            _real_row("ZETA"),
            {"symbol": "SMAR", "data_source": "missing_real_data",
             "missing_real_data_reason": "no bars", "tony_data_quality_read": "missing_real_data",
             "used_demo_data": 0, "entry_triggered": 0,
             "target": 58.0, "stop": 46.0, "outcome_label": "unreviewed"},
        ])
        watchlist = build_tony_watchlist_rows(df)
        symbols = [] if watchlist.empty else list(watchlist["symbol"].astype(str).str.upper())
        assert "SMAR" not in symbols
        assert "ZETA" in symbols

    def test_quarantined_symbol_hidden_from_watchlist(self) -> None:
        df = pd.DataFrame([_real_row("CYBR"), _real_row("ARM")])
        watchlist = build_tony_watchlist_rows(df, quarantine_symbols={"CYBR"})
        symbols = [] if watchlist.empty else list(watchlist["symbol"].astype(str).str.upper())
        assert "CYBR" not in symbols
        assert "ARM" in symbols

    def test_bad_dq_value_hidden_from_watchlist(self) -> None:
        row = _real_row("TRUE", tony_data_quality_read="demo_data")
        df = pd.DataFrame([row])
        watchlist = build_tony_watchlist_rows(df)
        symbols = [] if watchlist.empty else list(watchlist["symbol"].astype(str).str.upper())
        assert "TRUE" not in symbols

    def test_fallback_provider_row_hidden_from_watchlist(self) -> None:
        row = _real_row("SQ", snapshot_provider="fallback_demo_provider")
        df = pd.DataFrame([row])
        watchlist = build_tony_watchlist_rows(df)
        symbols = [] if watchlist.empty else list(watchlist["symbol"].astype(str).str.upper())
        assert "SQ" not in symbols

    def test_used_demo_data_row_hidden(self) -> None:
        row = _real_row("CYBR", used_demo_data=1)
        df = pd.DataFrame([row])
        watchlist = build_tony_watchlist_rows(df)
        symbols = [] if watchlist.empty else list(watchlist["symbol"].astype(str).str.upper())
        assert "CYBR" not in symbols


class TestV27APathLifecycle:
    """PATH-style stale tracked positions must never disappear silently."""

    def test_stale_row_detected_by_build_stale_tracking_rows(self) -> None:
        df = pd.DataFrame([_stale_row("PATH")])
        stale = build_stale_tracking_rows(df)
        assert not stale.empty
        assert "PATH" in stale["symbol"].astype(str).str.upper().values

    def test_stale_row_lifecycle_state_correct(self) -> None:
        df = pd.DataFrame([_stale_row("PATH")])
        stale = build_stale_tracking_rows(df)
        assert stale.iloc[0]["lifecycle_state"] == "stale_tracking_needs_review"

    def test_stale_row_appears_in_watchlist(self) -> None:
        df = pd.DataFrame([_stale_row("PATH")])
        watchlist = build_tony_watchlist_rows(df)
        assert not watchlist.empty
        path_rows = watchlist[watchlist["symbol"].astype(str).str.upper().eq("PATH")]
        assert not path_rows.empty
        assert path_rows.iloc[0]["lifecycle_state"] == "stale_tracking_needs_review"

    def test_path_not_silently_dropped(self) -> None:
        df = pd.DataFrame([_stale_row("PATH")])
        watchlist = build_tony_watchlist_rows(df)
        stale = build_stale_tracking_rows(df)
        in_watchlist = (
            not watchlist.empty
            and "PATH" in watchlist["symbol"].astype(str).str.upper().values
        )
        in_stale = (
            not stale.empty
            and "PATH" in stale["symbol"].astype(str).str.upper().values
        )
        assert in_watchlist or in_stale

    def test_stale_row_not_in_results(self) -> None:
        df = pd.DataFrame([_stale_row("PATH")])
        result_rows = build_results_product_rows(df)
        symbols = [] if result_rows.empty else list(result_rows["symbol"].astype(str).str.upper())
        assert "PATH" not in symbols

    def test_missing_real_data_tracking_phase_stays_tracking(self) -> None:
        row = _stale_row("PATH")
        phase = derive_pick_phase(row)
        assert phase == "tracking"


class TestV27ALifecycleSortOrder:
    """Active must sort before stale; stale before watching."""

    def test_active_before_stale(self) -> None:
        df = pd.DataFrame([_stale_row("PATH"), _active_row("ARM")])
        watchlist = build_tony_watchlist_rows(df)
        assert not watchlist.empty
        if "lifecycle_state" in watchlist.columns:
            states = list(watchlist["lifecycle_state"])
            active_idx = next((i for i, s in enumerate(states) if s == "active"), None)
            stale_idx = next((i for i, s in enumerate(states) if s == "stale_tracking_needs_review"), None)
            if active_idx is not None and stale_idx is not None:
                assert active_idx < stale_idx

    def test_stale_before_watching(self) -> None:
        watching = _real_row("DKNG", planned_entry_price=None, planned_entry_rule=None, entry_status="")
        df = pd.DataFrame([watching, _stale_row("PATH")])
        watchlist = build_tony_watchlist_rows(df)
        assert not watchlist.empty
        if "lifecycle_state" in watchlist.columns:
            states = list(watchlist["lifecycle_state"])
            stale_idx = next((i for i, s in enumerate(states) if s == "stale_tracking_needs_review"), None)
            watching_idx = next((i for i, s in enumerate(states) if s == "watching"), None)
            if stale_idx is not None and watching_idx is not None:
                assert stale_idx < watching_idx


class TestV27AResultsLedger:
    """Results must use tracked-position ledger — not disappear when active positions exist."""

    def test_results_not_empty_with_active_position(self) -> None:
        df = pd.DataFrame([_active_row("ARM")])
        result_rows = build_results_product_rows(df)
        assert not result_rows.empty
        assert "ARM" in result_rows["symbol"].astype(str).str.upper().values

    def test_results_active_phase_for_triggered_position(self) -> None:
        df = pd.DataFrame([_active_row("ZETA")])
        result_rows = build_results_product_rows(df)
        assert not result_rows.empty
        zeta_rows = result_rows[result_rows["symbol"].astype(str).str.upper().eq("ZETA")]
        assert not zeta_rows.empty
        assert zeta_rows.iloc[0]["results_phase"] == "active"

    def test_watching_only_excluded_from_results(self) -> None:
        watching = _real_row("DKNG", planned_entry_price=None, planned_entry_rule=None, entry_status="")
        df = pd.DataFrame([watching])
        result_rows = build_results_product_rows(df)
        symbols = [] if result_rows.empty else list(result_rows["symbol"].astype(str).str.upper())
        assert "DKNG" not in symbols

    def test_results_active_symbols_match_watchlist_active(self) -> None:
        df = pd.DataFrame([_active_row("ARM"), _active_row("ZETA")])
        result_rows = build_results_product_rows(df)
        watchlist = build_tony_watchlist_rows(df)
        result_active = set(
            result_rows[result_rows["results_phase"].eq("active")]["symbol"].astype(str).str.upper()
        ) if not result_rows.empty else set()
        wl_active = set()
        if not watchlist.empty and "lifecycle_state" in watchlist.columns:
            wl_active = set(
                watchlist[watchlist["lifecycle_state"].isin({"active", "weakening"})]["symbol"]
                .astype(str).str.upper()
            )
        assert result_active == wl_active


class TestV27AUnreconciledDiagnostic:
    """find_unreconciled_tracked_symbols must detect ledger gaps."""

    def test_empty_when_all_accounted_in_active(self) -> None:
        df = pd.DataFrame([_active_row("ARM")])
        result = find_unreconciled_tracked_symbols(df, active_symbols={"ARM"}, stale_symbols=set())
        assert "ARM" not in result

    def test_returns_gap_symbol(self) -> None:
        df = pd.DataFrame([_active_row("ARM")])
        result = find_unreconciled_tracked_symbols(df, active_symbols=set(), stale_symbols=set())
        assert "ARM" in result

    def test_ignores_terminal_outcome(self) -> None:
        df = pd.DataFrame([_active_row("ARM", outcome_label="target_hit", tracking_status="target_hit")])
        result = find_unreconciled_tracked_symbols(df, active_symbols=set(), stale_symbols=set())
        assert "ARM" not in result

    def test_ignores_symbol_in_stale_set(self) -> None:
        df = pd.DataFrame([_stale_row("PATH")])
        result = find_unreconciled_tracked_symbols(df, active_symbols=set(), stale_symbols={"PATH"})
        assert "PATH" not in result

    def test_empty_with_no_triggered_rows(self) -> None:
        df = pd.DataFrame([_real_row("DKNG")])
        result = find_unreconciled_tracked_symbols(df, active_symbols=set(), stale_symbols=set())
        assert "DKNG" not in result


class TestV27AHealthIssues:
    """collect_health_issues must report stale and missing tracked positions."""

    def test_warns_stale_symbols(self) -> None:
        issues = collect_health_issues(
            watch_status="no_run",
            real_data_only=True,
            provider="alpaca_iex",
            demo_blocked=False,
            rate_limit_count=0,
            all_fallback=False,
            stale_symbols=["PATH"],
        )
        assert any("PATH" in i or "stale" in i.lower() or "prior tracked" in i.lower() for i in issues)

    def test_warns_missing_tracked_symbols(self) -> None:
        issues = collect_health_issues(
            watch_status="no_run",
            real_data_only=True,
            provider="alpaca_iex",
            demo_blocked=False,
            rate_limit_count=0,
            all_fallback=False,
            missing_tracked_symbols=["PATH"],
        )
        assert any("PATH" in i or "tracked" in i.lower() for i in issues)

    def test_silent_when_no_ledger_gaps(self) -> None:
        issues = collect_health_issues(
            watch_status="no_run",
            real_data_only=True,
            provider="alpaca_iex",
            demo_blocked=False,
            rate_limit_count=0,
            all_fallback=False,
        )
        assert not any("prior tracked" in i.lower() for i in issues)


class TestV27AWatchingOnlyCardModel:
    """Watching-only cards must show N/A for target/stop and include needed_before_entry."""

    def test_watching_only_target_is_na(self) -> None:
        row = _real_row("DKNG", planned_entry_price=None, planned_entry_rule=None, entry_status="")
        card = build_pick_card_model(row)
        assert card["target"] == "N/A"

    def test_watching_only_stop_is_na(self) -> None:
        row = _real_row("DKNG", planned_entry_price=None, planned_entry_rule=None, entry_status="")
        card = build_pick_card_model(row)
        assert card["stop"] == "N/A"

    def test_watching_only_has_needed_before_entry(self) -> None:
        row = _real_row("DKNG", planned_entry_price=None, planned_entry_rule=None, entry_status="")
        card = build_pick_card_model(row)
        assert card.get("needed_before_entry", "") != ""

    def test_waiting_for_trigger_has_real_target_and_stop(self) -> None:
        row = _real_row("MARA")
        card = build_pick_card_model(row)
        assert card["target"] != "N/A"
        assert card["stop"] != "N/A"
