from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from trading_bot.data.market_data import build_market_data_provider
from trading_bot.data.symbol_quarantine import load_symbol_quarantine_config
from trading_bot.data.universe import load_universe, load_universe_metadata, load_universe_tags
from trading_bot.analytics import OutcomeAnalytics
from trading_bot.dashboard.helpers import (
    build_active_tracking_product_rows,
    build_pick_card_model,
    build_result_card_model,
    build_results_product_rows,
    build_tony_pick_product_rows,
    build_tony_watchlist_rows,
    build_top_watch_rows,
    build_tracked_setup_card_model,
    collect_health_issues,
    count_hypothesis_by_priority,
    count_interesting_and_risky_stocks,
    eod_outcome_summary_today,
    event_age_label,
    filter_events_by_type,
    filter_research_snapshots,
    human_review_items,
    is_fallback_provider,
    is_waiting_for_market_open,
    latest_event_of_type,
    market_context_plain_english,
    missing_symbols_from_events,
    snapshot_symbol_lookup,
    snapshots_today_count,
    snapshots_today_dataframe,
    split_snapshots_by_phase,
    home_briefing_review_items,
    RESULTS_FILTERS,
    filter_results_product_rows,
    risk_reward_definition_text,
    select_home_preview_picks,
    select_home_tracking_rows,
    summarize_results_product_counts,
    summarize_product_reconciliation,
    summarize_research_pl,
    tony_status_home_message,
    summarize_results_plain_english,
    summarize_symbol_list,
    summarize_system_health,
    tony_status_beginner_label,
    trigger_tracker_summary,
    watch_status_label,
)
from trading_bot.dashboard.theme import (
    avg_research_pl_from_prepared,
    briefing_line,
    inject_tony_theme,
    render_hero,
    render_pick_preview_card,
    render_pick_signal_card,
    render_result_card,
    render_results_performance,
    render_stat_grid,
    render_tracking_position_card,
    render_tracking_preview_card,
    section_header,
)
from trading_bot.settings import load_scanner_settings, real_data_only_enabled, resolve_effective_provider
from trading_bot.indicators import simple_moving_average
from trading_bot.storage.repositories import ScannerRepository


st.set_page_config(page_title="Tony Stocks", layout="wide")


@st.cache_resource
def repository() -> ScannerRepository:
    settings = load_scanner_settings()
    return ScannerRepository(settings.database_path)


def latest_results(repo: ScannerRepository) -> pd.DataFrame:
    results = repo.latest_scan_results()
    if not results.empty:
        for column in ("reasons_json", "warnings_json", "tags_json"):
            if column in results.columns:
                results[column] = results[column].fillna("[]")
        results["key_reason"] = results["reasons_json"].apply(lambda value: (json.loads(value or "[]") or [""])[0])
        results["warning_count"] = results["warnings_json"].apply(lambda value: len(json.loads(value or "[]")))
        results["is_etf_or_benchmark"] = results["tags_json"].apply(
            lambda value: bool({"etf", "benchmark"} & set(json.loads(value or "[]")))
        )
        results["is_mega_cap"] = results["tags_json"].apply(
            lambda value: "mega_cap" in set(json.loads(value or "[]"))
        )
        results["tags_list"] = results["tags_json"].apply(lambda value: json.loads(value or "[]"))
        if "universe_role" not in results.columns:
            results["universe_role"] = "primary_candidate"
        if "candidate_summary" not in results.columns:
            results["candidate_summary"] = ""
        if "trade_plan_valid" not in results.columns:
            results["trade_plan_valid"] = 1
        if "trade_plan_status" not in results.columns:
            results["trade_plan_status"] = "valid"
        results["trade_plan_valid"] = results["trade_plan_valid"].fillna(1).astype(bool)
    return results


def render_data_provider_status(repo: ScannerRepository | None = None) -> None:
    """Show a compact data provider status card in the Overview tab."""
    settings = load_scanner_settings()
    configured_provider = settings.provider
    effective_provider = resolve_effective_provider(settings)
    market_data_cfg = settings.market_data or {}
    alpaca_cfg = market_data_cfg.get("alpaca") or {}
    real_enabled = bool(market_data_cfg.get("real_provider_enabled", False))

    last_scan_run = repo.latest_scan_run() if repo else None
    last_scan_provider = str(last_scan_run.get("provider", "unknown")) if last_scan_run else "no scan yet"

    with st.expander("Data Provider Status", expanded=False):
        top_cols = st.columns(4)
        top_cols[0].metric("Configured Provider", configured_provider)
        top_cols[1].metric("Effective Provider", effective_provider)
        top_cols[2].metric("real_provider_enabled", str(real_enabled))
        top_cols[3].metric("Last Scan Provider", last_scan_provider)

        if effective_provider == "alpaca_iex":
            feed = alpaca_cfg.get("feed", "iex")
            timeframe = alpaca_cfg.get("timeframe", "1Day")
            max_symbols = alpaca_cfg.get("max_symbols_per_scan", 30)
            batch_enabled = bool(alpaca_cfg.get("batch_requests_enabled", True))
            max_per_batch = int(alpaca_cfg.get("max_symbols_per_batch", 175))
            max_rpm = int(alpaca_cfg.get("max_requests_per_minute", 175))
            detail_cols = st.columns(5)
            detail_cols[0].metric("Feed", str(feed).upper())
            detail_cols[1].metric("Timeframe", str(timeframe))
            detail_cols[2].metric("Max Symbols/Scan", str(max_symbols))
            detail_cols[3].metric("Batch Mode", "ON" if batch_enabled else "OFF")
            detail_cols[4].metric("Max RPM (safe)", str(max_rpm))

            intraday_cfg = settings.intraday or {}
            intraday_cols = st.columns(4)
            intraday_cols[0].metric("Intraday Reads", "enabled" if intraday_cfg.get("enabled", False) else "disabled")
            intraday_cols[1].metric("Intraday TF", str(intraday_cfg.get("timeframe", "5Min")))
            intraday_cols[2].metric("Tony Uses Intraday", str(bool(intraday_cfg.get("use_for_tony_analysis", True))))
            intraday_cols[3].metric("Scoring Uses Intraday", str(bool(intraday_cfg.get("use_for_scoring", False))))
            st.caption("Intraday reads are research-only and are not entry automation.")

            rotation_cfg = settings.watch_universe_rotation or {}
            if rotation_cfg.get("enabled", False):
                rot_cols = st.columns(4)
                rot_cols[0].metric("Rotation", "enabled")
                rot_cols[1].metric("Max/Cycle", str(rotation_cfg.get("max_symbols_per_cycle", 175)))
                rot_cols[2].metric("Core Max", str(rotation_cfg.get("core_max_symbols", 50)))
                rot_cols[3].metric("Bucket Size", str(rotation_cfg.get("rotating_bucket_size", 125)))

            try:
                universe_cfg_path = settings.universe_config_path
                all_syms = load_universe(universe_cfg_path)
                universe_tags = load_universe_tags(universe_cfg_path)
                universe_meta = load_universe_metadata(universe_cfg_path)
                core_syms = [s for s, t in universe_tags.items() if "watchlist_core" in t]
                discovery_syms = [s for s, t in universe_tags.items() if "discovery" in t]
                active_syms = [s for s, m in universe_meta.items() if m.universe_role != "excluded_by_default"]
                univ_cols = st.columns(4)
                univ_cols[0].metric("Universe Total", len(all_syms))
                univ_cols[1].metric("Active (non-excluded)", len(active_syms))
                univ_cols[2].metric("Watchlist Core", len(core_syms))
                univ_cols[3].metric("Discovery Pool", len(discovery_syms))
            except Exception:
                pass

            st.warning(
                "**Alpaca IEX data notice:** Alpaca IEX is a single-exchange feed and may differ from "
                "consolidated SIP market tape. Do not use as sole basis for execution decisions. "
                "This is market data for research and scanning only — no orders are placed."
            )
            if repo:
                recent_events = repo.list_tony_events(limit=200)
                fallback_count = 0
                stale_count = 0
                all_fallback_count = 0
                batch_summary_count = 0
                scaled_count = 0
                rate_limit_count = 0
                if not recent_events.empty and "event_type" in recent_events.columns:
                    fallback_count = int(recent_events["event_type"].eq("data_provider_fallback").sum())
                    stale_count = int(recent_events["event_type"].eq("stale_data_warning").sum())
                    all_fallback_count = int(recent_events["event_type"].eq("all_symbol_fallback").sum())
                    batch_summary_count = int(recent_events["event_type"].eq("batch_fetch_summary").sum())
                    scaled_count = int(recent_events["event_type"].eq("real_data_scan_scaled").sum())
                    rate_limit_count = int(recent_events["event_type"].eq("rate_limit_warning").sum())
                event_cols = st.columns(3)
                event_cols[0].metric("Fallback Events (recent)", fallback_count)
                event_cols[1].metric("Stale Data Events (recent)", stale_count)
                event_cols[2].metric("All-Symbol Fallback Events", all_fallback_count)
                v9_cols = st.columns(3)
                v9_cols[0].metric("Batch Fetch Events", batch_summary_count)
                v9_cols[1].metric("Scaled Scan Events", scaled_count)
                v9_cols[2].metric("Rate Limit Warnings", rate_limit_count)
                if all_fallback_count > 0:
                    st.error(
                        f"**{all_fallback_count} all-symbol fallback event(s) recorded.** "
                        "All symbols fell back to demo data in at least one recent cycle. "
                        "Check Alpaca API keys, connectivity, and market hours."
                    )
                if rate_limit_count > 0:
                    st.warning(
                        f"**{rate_limit_count} rate limit warning(s) recorded.** "
                        "Scans slowed due to Alpaca rate limits. Consider reducing max_symbols_per_cycle."
                    )
        else:
            detail_cols = st.columns(2)
            detail_cols[0].metric("Timeframe", settings.timeframe)
            detail_cols[1].metric("Mode", "research/testing")
            if effective_provider == "demo_generated":
                st.info("Provider is demo_generated. Set real_provider_enabled: true and provider: alpaca_iex in market_data config, then add API keys to .env.")


def render_overview(repo: ScannerRepository, results: pd.DataFrame) -> None:
    run = repo.latest_scan_run()
    primary = results[results["universe_role"].eq("primary_candidate")] if not results.empty else results
    mid_small = results[results["tags_list"].apply(lambda tags: bool({"mid_cap", "small_cap"} & set(tags)))] if not results.empty else results
    cols = st.columns(6)
    cols[0].metric("Latest scan", run["created_at"] if run else "No scan")
    cols[1].metric("Stocks scanned", len(results))
    cols[2].metric("Average score", round(float(results["final_score"].mean()), 2) if not results.empty else 0)
    cols[3].metric("Primary candidates", len(primary))
    cols[4].metric("Mid/small-cap candidates", len(mid_small))
    cols[5].metric("Warnings", int(results["warning_count"].sum()) if not results.empty else 0)
    render_data_provider_status(repo)
    render_watch_status(repo, run)
    if not results.empty:
        chart_cols = st.columns(3)
        chart_cols[0].plotly_chart(
            go.Figure(data=[go.Histogram(x=results["final_score"], nbinsx=10)]).update_layout(title="Score Distribution"),
            width="stretch",
        )
        category_counts = results["setup_category"].value_counts().reset_index()
        category_counts.columns = ["setup_category", "count"]
        chart_cols[1].plotly_chart(
            go.Figure(data=[go.Bar(x=category_counts["setup_category"], y=category_counts["count"])]).update_layout(title="Category Counts"),
            width="stretch",
        )
        top_10 = results.head(10).sort_values("final_score")
        chart_cols[2].plotly_chart(
            go.Figure(data=[go.Bar(x=top_10["final_score"], y=top_10["symbol"], orientation="h")]).update_layout(title="Top 10 Scores"),
            width="stretch",
        )
        st.subheader("Primary Swing Candidates")
        st.dataframe(_ranked_columns(_default_primary_candidates(results).head(15)), width="stretch", hide_index=True)
        section_cols = st.columns(3)
        with section_cols[0]:
            st.subheader("Benchmarks / Market Context")
            st.dataframe(_ranked_columns(results[results["universe_role"].isin(["benchmark"])]), width="stretch", hide_index=True)
        with section_cols[1]:
            st.subheader("Mega-Cap References")
            st.dataframe(_ranked_columns(results[results["is_mega_cap"] | results["universe_role"].eq("reference")]), width="stretch", hide_index=True)
        with section_cols[2]:
            st.subheader("Avoid / Weak / Overextended")
            avoid = results[results["setup_category"].isin(["Weak / Avoid", "Overextended / Wait", "Invalid Trade Plan"])]
            st.dataframe(_ranked_columns(avoid), width="stretch", hide_index=True)
        st.subheader("Speculative Watchlist")
        speculative = results[results["universe_role"].eq("speculative_candidate") | results["tags_list"].apply(lambda tags: "speculative" in tags)]
        st.dataframe(_ranked_columns(speculative), width="stretch", hide_index=True)


def render_watch_status(repo: ScannerRepository, run: dict | None) -> None:
    """Show a compact readout for scheduled scan/snapshot collection."""
    outcome_counts = repo.count_candidate_snapshots_by_outcome()
    latest_snapshots = repo.latest_candidate_snapshots(limit=100)
    latest_snapshot_count = 0
    if not latest_snapshots.empty and "scan_run_id" in latest_snapshots.columns and run:
        latest_snapshot_count = int(latest_snapshots["scan_run_id"].eq(run["id"]).sum())
    status_cols = st.columns(6)
    status_cols[0].metric("Watch Latest Scan", run["created_at"] if run else "No scan")
    status_cols[1].metric("Latest Scan Snapshots", latest_snapshot_count)
    status_cols[2].metric("Open/Watch Snapshots", repo.count_open_candidate_snapshots())
    status_cols[3].metric("Triggered Snapshots", repo.count_triggered_candidate_snapshots())
    status_cols[4].metric("Target Outcomes", _count_outcome(outcome_counts, ["target_hit", "target_before_stop"]))
    status_cols[5].metric("Still Open", _count_outcome(outcome_counts, ["still_open", "insufficient_future_data"]))


def render_ranked(results: pd.DataFrame) -> None:
    st.subheader("Ranked Stocks")
    if results.empty:
        st.info("Run a scan first.")
        return
    min_score = st.slider("Minimum score", 0, 100, 0)
    categories = ["All"] + sorted(results["setup_category"].dropna().unique().tolist())
    category = st.selectbox("Setup category", categories)
    roles = ["All"] + sorted(results["universe_role"].fillna("primary_candidate").unique().tolist())
    role = st.selectbox("Universe role", roles, index=roles.index("primary_candidate") if "primary_candidate" in roles else 0)
    all_tags = sorted({tag for tags in results["tags_list"] for tag in tags})
    selected_tags = st.multiselect("Tags", all_tags)
    cols = st.columns(5)
    primary_only = cols[0].checkbox("Primary candidates only", value=True)
    exclude_etfs = cols[1].checkbox("Exclude ETFs/benchmarks", value=True)
    exclude_mega_caps = cols[2].checkbox("Exclude mega-caps", value=False)
    max_price = cols[3].number_input("Max price", min_value=0.0, value=0.0, help="0 means no max.")
    min_dollar_volume = cols[4].number_input("Min dollar volume", min_value=0, value=0, step=1000000)
    filtered = results[(results["final_score"] >= min_score) & (results["dollar_volume_20"] >= min_dollar_volume)]
    if category != "All":
        filtered = filtered[filtered["setup_category"] == category]
    if role != "All":
        filtered = filtered[filtered["universe_role"] == role]
    if primary_only:
        filtered = _default_primary_candidates(filtered)
    if selected_tags:
        selected_set = set(selected_tags)
        filtered = filtered[filtered["tags_list"].apply(lambda tags: selected_set.issubset(set(tags)))]
    if exclude_etfs:
        filtered = filtered[~filtered["is_etf_or_benchmark"]]
    if exclude_mega_caps:
        filtered = filtered[~filtered["is_mega_cap"]]
    if max_price > 0:
        filtered = filtered[filtered["latest_close"] <= max_price]
    st.dataframe(_ranked_columns(filtered), width="stretch", hide_index=True)


def render_detail(results: pd.DataFrame) -> None:
    st.subheader("Stock Detail")
    if results.empty:
        st.info("Run a scan first.")
        return
    symbol = st.selectbox("Symbol", results["symbol"].tolist())
    row = results[results["symbol"] == symbol].iloc[0]
    meta_cols = st.columns(5)
    meta_cols[0].metric("Universe Role", row.get("universe_role", "primary_candidate"))
    meta_cols[1].metric("Setup Category", row.get("setup_category", "Uncategorized"))
    meta_cols[2].metric("Warnings", int(row.get("warning_count", 0)))
    meta_cols[3].metric("Risk/Reward", row.get("risk_reward_ratio", 0))
    meta_cols[4].metric("Trade Plan", "Valid" if bool(row.get("trade_plan_valid", True)) else "Invalid")
    st.write("Tags", row.get("tags_list", []))
    st.write("Candidate Summary", row.get("candidate_summary", ""))
    cols = st.columns(5)
    for col, key in zip(cols, ["trend_score", "momentum_score", "volume_score", "risk_score", "setup_quality_score"]):
        col.metric(key.replace("_", " ").title(), row[key])
    breakdown = pd.DataFrame(
        {
            "score_type": ["Trend", "Momentum", "Volume", "Risk", "Setup Quality"],
            "score": [row["trend_score"], row["momentum_score"], row["volume_score"], row["risk_score"], row["setup_quality_score"]],
        }
    )
    st.plotly_chart(
        go.Figure(data=[go.Bar(x=breakdown["score_type"], y=breakdown["score"])]).update_layout(title=f"{symbol} Score Breakdown", yaxis_range=[0, 100]),
        width="stretch",
    )
    st.write("Reasons", json.loads(row["reasons_json"] or "[]"))
    st.write("Warnings", json.loads(row["warnings_json"] or "[]"))
    st.write(
        {
            "suggested_entry": row["suggested_entry"],
            "suggested_stop": row["suggested_stop"],
            "suggested_target_1": row["suggested_target_1"],
            "risk_reward_ratio": row["risk_reward_ratio"],
            "trade_plan_valid": bool(row.get("trade_plan_valid", True)),
            "trade_plan_status": row.get("trade_plan_status", "valid"),
        }
    )
    settings = load_scanner_settings()
    metadata = load_universe_metadata(settings.universe_config_path)
    profiles_by_symbol = {
        item_symbol: item.demo_profile
        for item_symbol, item in metadata.items()
        if item.demo_profile
    }
    provider = build_market_data_provider(
        resolve_effective_provider(settings),
        settings.cache_dir,
        profiles_by_symbol=profiles_by_symbol,
        market_data_config=settings.market_data,
    )
    data = provider.fetch_ohlcv(symbol, settings.lookback_days, settings.timeframe)
    data["sma20"] = simple_moving_average(data["close"], 20)
    data["sma50"] = simple_moving_average(data["close"], 50)
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=data.index, open=data["open"], high=data["high"], low=data["low"], close=data["close"], name=symbol))
    fig.add_trace(go.Scatter(x=data.index, y=data["sma20"], name="SMA20"))
    fig.add_trace(go.Scatter(x=data.index, y=data["sma50"], name="SMA50"))
    st.plotly_chart(fig, width="stretch")

    run = repository().latest_scan_run()
    with st.form("detail_manual_pick"):
        notes = st.text_area("Manual pick notes")
        if st.form_submit_button("Add Manual Pick"):
            repository().add_manual_pick(
                symbol=symbol,
                scan_run_id=run["id"] if run else None,
                planned_entry=float(row["suggested_entry"]),
                planned_stop=float(row["suggested_stop"]),
                planned_target=float(row["suggested_target_1"]),
                notes=notes,
            )
            st.success("Manual pick added.")


def render_manual_picks(repo: ScannerRepository, results: pd.DataFrame) -> None:
    st.subheader("Manual Picks")
    run = repo.latest_scan_run()
    symbols = results["symbol"].tolist() if not results.empty else []
    with st.form("manual_pick"):
        symbol = st.selectbox("Symbol", symbols) if symbols else st.text_input("Symbol")
        notes = st.text_area("Notes")
        submitted = st.form_submit_button("Add Pick")
        if submitted and symbol:
            row = results[results["symbol"] == symbol].iloc[0] if not results.empty and symbol in symbols else None
            repo.add_manual_pick(
                symbol=symbol,
                scan_run_id=run["id"] if run else None,
                planned_entry=float(row["suggested_entry"]) if row is not None else None,
                planned_stop=float(row["suggested_stop"]) if row is not None else None,
                planned_target=float(row["suggested_target_1"]) if row is not None else None,
                notes=notes,
            )
            st.success("Manual pick added.")
    picks = repo.manual_picks()
    st.dataframe(picks, width="stretch", hide_index=True)


def render_paper_journal(repo: ScannerRepository) -> None:
    st.subheader("Paper Trade Journal")
    with st.form("paper_trade"):
        cols = st.columns(4)
        symbol = cols[0].text_input("Symbol")
        entry_price = cols[1].number_input("Entry", min_value=0.0, value=0.0)
        shares = cols[2].number_input("Shares", min_value=0.0, value=0.0)
        status = cols[3].selectbox("Status", ["open", "closed", "stopped", "target_hit"])
        cols2 = st.columns(3)
        stop_price = cols2[0].number_input("Stop", min_value=0.0, value=0.0)
        target_price = cols2[1].number_input("Target", min_value=0.0, value=0.0)
        exit_price = cols2[2].number_input("Exit", min_value=0.0, value=0.0)
        notes = st.text_area("Trade notes")
        submitted = st.form_submit_button("Add Paper Trade")
        if submitted and symbol:
            repo.add_paper_trade(
                {
                    "symbol": symbol,
                    "entry_price": entry_price,
                    "stop_price": stop_price,
                    "target_price": target_price,
                    "exit_price": exit_price if exit_price else None,
                    "shares": shares,
                    "status": status,
                    "notes": notes,
                }
            )
            st.success("Paper trade added.")
    st.dataframe(repo.paper_trades(), width="stretch", hide_index=True)


def render_performance(repo: ScannerRepository) -> None:
    st.subheader("Performance")
    trades = repo.paper_trades()
    if trades.empty:
        st.info("No paper trades logged yet.")
        return
    closed = trades.dropna(subset=["pnl"])
    cols = st.columns(5)
    cols[0].metric("Total trades", len(trades))
    cols[1].metric("Win rate", f"{round((closed['pnl'] > 0).mean() * 100, 2)}%" if not closed.empty else "0%")
    cols[2].metric("Average P&L", round(float(closed["pnl"].mean()), 2) if not closed.empty else 0)
    cols[3].metric("Total P&L", round(float(closed["pnl"].sum()), 2) if not closed.empty else 0)
    cols[4].metric("Open trades", int((trades["status"] == "open").sum()) if "status" in trades else 0)
    st.dataframe(trades, width="stretch", hide_index=True)


def render_candidate_snapshots(repo: ScannerRepository) -> None:
    st.subheader("Candidate Snapshots")
    snapshots = repo.latest_candidate_snapshots(limit=500)
    if snapshots.empty:
        st.info("No candidate snapshots saved yet. Run: python -m trading_bot.cli snapshot --config config/default_config.yaml")
        return
    for column in ("tags_json", "reasons_json", "warnings_json"):
        if column in snapshots.columns:
            snapshots[column] = snapshots[column].fillna("[]")
    snapshots["tags_list"] = snapshots["tags_json"].apply(lambda value: json.loads(value or "[]"))
    snapshots["warning_count"] = snapshots["warnings_json"].apply(lambda value: len(json.loads(value or "[]")))
    snapshots["snapshot_date"] = snapshots["snapshot_time"].str.slice(0, 10)

    if "trade_plan_valid" not in snapshots.columns:
        snapshots["trade_plan_valid"] = 1
    if "trade_plan_status" not in snapshots.columns:
        snapshots["trade_plan_status"] = "valid"
    snapshots["trade_plan_valid"] = snapshots["trade_plan_valid"].fillna(1).astype(bool)

    today = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    today_count = int((snapshots["snapshot_date"] == today).sum())
    open_count = repo.count_open_candidate_snapshots()
    triggered_count = repo.count_triggered_candidate_snapshots()
    category_counts = repo.count_candidate_snapshots_by_category()
    role_counts = repo.count_candidate_snapshots_by_role()
    outcome_counts = repo.count_candidate_snapshots_by_outcome()

    planned_today = repo.count_planned_triggers_today(today) if hasattr(repo, "count_planned_triggers_today") else 0
    triggered_today = repo.count_entry_trigger_status("triggered", today) if hasattr(repo, "count_entry_trigger_status") else 0
    pending_entries = repo.count_entry_trigger_status("pending") if hasattr(repo, "count_entry_trigger_status") else 0
    expired_entries = (
        repo.count_entry_trigger_status("expired")
        + repo.count_entry_trigger_status("not_triggered")
        if hasattr(repo, "count_entry_trigger_status")
        else 0
    )

    cols = st.columns(6)
    cols[0].metric("Snapshots Today", today_count)
    cols[1].metric("Open/Watch", open_count)
    cols[2].metric("Triggered", triggered_count)
    cols[3].metric("Target Hit", _count_outcome(outcome_counts, ["target_hit", "target_before_stop"]))
    cols[4].metric("Stop Hit", _count_outcome(outcome_counts, ["stop_hit", "stop_before_target"]))
    cols[5].metric("Insufficient Data", _count_outcome(outcome_counts, ["insufficient_future_data"]))

    trigger_cols = st.columns(4)
    trigger_cols[0].metric("Planned Triggers Today", planned_today)
    trigger_cols[1].metric("Triggered Entries Today", triggered_today)
    trigger_cols[2].metric("Pending Entries", pending_entries)
    trigger_cols[3].metric("Expired / No Trigger", expired_entries)

    status_cols = st.columns(3)
    status_cols[0].metric("Still Open", _count_outcome(outcome_counts, ["still_open"]))
    status_cols[1].metric("Categories", len(category_counts))
    status_cols[2].metric("Warnings", int(snapshots["warning_count"].sum()))

    chart_cols = st.columns(3)
    if not category_counts.empty:
        chart_cols[0].plotly_chart(
            go.Figure(data=[go.Bar(x=category_counts["setup_category"], y=category_counts["count"])]).update_layout(title="Snapshots by Setup Category"),
            width="stretch",
        )
    if not role_counts.empty:
        chart_cols[1].plotly_chart(
            go.Figure(data=[go.Bar(x=role_counts["universe_role"], y=role_counts["count"])]).update_layout(title="Snapshots by Universe Role"),
            width="stretch",
        )
    if not outcome_counts.empty:
        chart_cols[2].plotly_chart(
            go.Figure(data=[go.Bar(x=outcome_counts["outcome_label"], y=outcome_counts["count"])]).update_layout(title="Snapshots by Outcome"),
            width="stretch",
        )

    filter_cols = st.columns(6)
    status = filter_cols[0].selectbox("Status", ["All"] + sorted(snapshots["status"].dropna().unique().tolist()))
    category = filter_cols[1].selectbox("Setup Category", ["All"] + sorted(snapshots["setup_category"].dropna().unique().tolist()))
    role = filter_cols[2].selectbox("Universe Role", ["All"] + sorted(snapshots["universe_role"].dropna().unique().tolist()))
    outcomes = ["All"] + sorted(snapshots["outcome_label"].fillna("unreviewed").unique().tolist())
    outcome = filter_cols[3].selectbox("Outcome", outcomes)
    triggered_filter = filter_cols[4].selectbox("Entry Triggered", ["All", "Yes", "No"])
    date = filter_cols[5].selectbox("Date", ["All"] + sorted(snapshots["snapshot_date"].dropna().unique().tolist(), reverse=True))

    filtered = snapshots.copy()
    if status != "All":
        filtered = filtered[filtered["status"] == status]
    if category != "All":
        filtered = filtered[filtered["setup_category"] == category]
    if role != "All":
        filtered = filtered[filtered["universe_role"] == role]
    if outcome != "All":
        filtered = filtered[filtered["outcome_label"].fillna("unreviewed") == outcome]
    if triggered_filter == "Yes":
        filtered = filtered[filtered["entry_triggered"].fillna(0).astype(int).eq(1)]
    elif triggered_filter == "No":
        filtered = filtered[filtered["entry_triggered"].fillna(0).astype(int).eq(0)]
    if date != "All":
        filtered = filtered[filtered["snapshot_date"] == date]

    st.subheader("Top Snapshot Candidates")
    st.dataframe(_snapshot_columns(filtered.sort_values("total_score", ascending=False).head(100)), width="stretch", hide_index=True)

    if filtered.empty:
        st.info("No snapshots match the current filters.")
        return
    selected_id = st.selectbox("Selected Snapshot", filtered["id"].tolist())
    if selected_id:
        row = filtered[filtered["id"] == selected_id].iloc[0]
        detail_cols = st.columns(5)
        detail_cols[0].metric("Symbol", row["symbol"])
        detail_cols[1].metric("Score", row["total_score"])
        detail_cols[2].metric("Setup", row["setup_category"])
        detail_cols[3].metric("Role", row["universe_role"])
        detail_cols[4].metric("Risk/Reward", row["risk_reward"])
        st.write("Trade Plan", {"valid": bool(row.get("trade_plan_valid", True)), "status": row.get("trade_plan_status", "valid")})
        _render_snapshot_intraday_read(row)
        st.write("Tags", row["tags_list"])
        st.write(
            {
                "snapshot_time": row["snapshot_time"],
                "snapshot_price": row.get("snapshot_price"),
                "planned_entry_price": row.get("planned_entry_price"),
                "planned_entry_rule": row.get("planned_entry_rule"),
                "entry_status": row.get("entry_status"),
                "actual_entry_price": row.get("actual_entry_price"),
                "actual_entry_time": row.get("actual_entry_time"),
                "close": row["close"],
                "entry": row["entry"],
                "stop": row["stop"],
                "target": row["target"],
                "dollar_volume": row["dollar_volume"],
                "relative_volume": row["relative_volume"],
                "atr_percent": row["atr_percent"],
                "status": row["status"],
                "entry_trigger_price": row["entry_trigger_price"],
                "entry_triggered": bool(row["entry_triggered"]),
                "highest_price_seen": row["highest_price_seen"],
                "lowest_price_seen": row["lowest_price_seen"],
                "last_checked_at": row["last_checked_at"],
                "result_1h": row["result_1h"],
                "result_eod": row["result_eod"],
                "result_3d": row["result_3d"],
                "result_5d": row["result_5d"],
                "result_10d": row["result_10d"],
                "result_20d": row["result_20d"],
                "outcome_label": row["outcome_label"],
                "notes": row.get("notes", ""),
                "tony_intraday_read": row.get("tony_intraday_read"),
                "intraday_timeframe": row.get("intraday_timeframe"),
                "intraday_close": row.get("intraday_close"),
                "intraday_vwap": row.get("intraday_vwap"),
                "intraday_above_vwap": row.get("intraday_above_vwap"),
                "intraday_day_change_percent": row.get("intraday_day_change_percent"),
                "intraday_relative_volume": row.get("intraday_relative_volume"),
                "intraday_opening_range_status": row.get("intraday_opening_range_status"),
            }
        )
        st.write("Reasons", json.loads(row["reasons_json"] or "[]"))
        st.write("Warnings", json.loads(row["warnings_json"] or "[]"))
        st.write("Candidate Summary", row["candidate_summary"])


def _render_snapshot_intraday_read(row: pd.Series) -> None:
    """Render compact intraday read fields when stored on a snapshot."""
    read = row.get("tony_intraday_read")
    timeframe = row.get("intraday_timeframe")
    if read in (None, "", "nan") and timeframe in (None, "", "nan"):
        return
    st.subheader("Intraday Read")
    st.caption("Research-only intraday context. Not entry automation and not a trade instruction.")
    cols = st.columns(5)
    cols[0].metric("Tony Read", str(read or "unavailable").replace("_", " "))
    cols[1].metric("Timeframe", timeframe or "n/a")
    cols[2].metric("Close", row.get("intraday_close", "n/a"))
    cols[3].metric("VWAP", row.get("intraday_vwap", "n/a"))
    cols[4].metric("Above VWAP", row.get("intraday_above_vwap", "n/a"))
    st.write(
        {
            "day_change_percent": row.get("intraday_day_change_percent"),
            "relative_volume": row.get("intraday_relative_volume"),
            "opening_range_status": row.get("intraday_opening_range_status"),
        }
    )


def render_tony_stocks(repo: ScannerRepository) -> None:
    st.subheader("Tony Stocks")
    settings = load_scanner_settings()
    tony_config = settings.tony_stocks or {}
    st.info(
        "Tony Stocks is an analyst, not a trader. "
        "No paper trades, broker orders, or live trades are placed. "
        "Hypotheses are deterministic reads of scanner output — not financial advice."
    )
    events = repo.list_tony_events(limit=500)
    status_cols = st.columns(6)
    status_cols[0].metric("Tony Mode", str(tony_config.get("mode", "watcher")))
    latest_scan = _latest_event_time(events, "scan_completed")
    latest_watch = _latest_event_time(events, "watch_cycle_completed")
    status_cols[1].metric("Latest Scan Event", latest_scan or "None")
    status_cols[2].metric("Latest Watch Event", latest_watch or "None")
    status_cols[3].metric("Warnings", repo.count_tony_events(severity="warning"))
    status_cols[4].metric("High-Score Events", repo.count_tony_events(event_type="high_score_candidate"))
    status_cols[5].metric("Analyst Hypotheses", repo.count_tony_events(event_type="analyst_candidate_hypothesis"))

    # ── Analyst reads section ─────────────────────────────────────────────────
    analyst_events = repo.list_tony_events(event_type="analyst_candidate_hypothesis", limit=50)
    mkt_events = repo.list_tony_events(event_type="analyst_market_context", limit=5)
    dq_events = repo.list_tony_events(event_type="analyst_data_quality", limit=5)
    risk_events = repo.list_tony_events(event_type="analyst_risk_warning", limit=10)

    with st.expander("Analyst Reads (latest cycle)", expanded=True):
        if not mkt_events.empty:
            mkt_row = mkt_events.iloc[0]
            mkt_payload = json.loads(mkt_row.get("payload_json") or "{}")
            mkt_label = mkt_payload.get("context_label", "unknown")
            mkt_color = {"market_supportive": "✅", "market_weak": "⚠️", "market_mixed": "🔶", "benchmark_data_missing": "❓"}
            st.markdown(f"**Market Context:** {mkt_color.get(mkt_label, '')} `{mkt_label}` — {mkt_row.get('message', '')}")
        if not dq_events.empty:
            dq_row = dq_events.iloc[0]
            st.markdown(f"**Data Quality:** {dq_row.get('message', '')}")
        if not risk_events.empty:
            risk_row = risk_events.iloc[0]
            st.markdown(f"**Risk Warning:** {risk_row.get('message', '')}")

        if not analyst_events.empty:
            st.markdown("---")
            st.markdown("**Candidate Hypotheses** *(Tony is analyzing, not trading)*")
            for _, ev in analyst_events.iterrows():
                payload = json.loads(ev.get("payload_json") or "{}")
                sym = ev.get("symbol") or payload.get("symbol", "?")
                priority = payload.get("priority_label", "")
                action = payload.get("recommended_action", "")
                setup = payload.get("setup_read", "")
                priority_icon = {"high_priority": "🔴", "watch": "🟡", "low_priority": "🟢", "avoid": "⛔", "reference_only": "📊"}.get(priority, "")
                with st.expander(f"{priority_icon} {sym} — {priority} | {action} | {setup}"):
                    st.write(ev.get("message", ""))
                    if payload:
                        st.json(payload)
        elif not events.empty:
            st.info("No analyst hypothesis events yet. Analyst mode produces events when scanning with real or demo data.")

    if events.empty:
        st.info("No Tony Stocks events yet. Run a scan, snapshot update, or watch cycle.")
        return

    st.markdown("---")
    st.subheader("All Tony Events")

    # separate current real-data events from old fallback events
    if not events.empty and "event_type" in events.columns:
        fallback_types = {"data_provider_fallback", "all_symbol_fallback", "provider_fallback_summary"}
        real_data_types = {"real_data_scan_scaled", "batch_fetch_summary", "real_provider_active", "universe_rotation_summary"}
        has_real = not events[events["event_type"].isin(real_data_types)].empty
        has_fallback = not events[events["event_type"].isin(fallback_types)].empty
        if has_real and has_fallback:
            st.info("This event log contains both real-data scan events and fallback events from earlier cycles.")

    filter_cols = st.columns(4)
    severity = filter_cols[0].selectbox("Severity", ["All"] + sorted(events["severity"].dropna().unique().tolist()))
    event_type = filter_cols[1].selectbox("Event Type", ["All"] + sorted(events["event_type"].dropna().unique().tolist()))
    symbols = ["All"] + sorted(events["symbol"].dropna().unique().tolist())
    symbol = filter_cols[2].selectbox("Symbol", symbols)
    unacknowledged = filter_cols[3].checkbox("Unacknowledged only", value=False)

    filtered = events.copy()
    if severity != "All":
        filtered = filtered[filtered["severity"] == severity]
    if event_type != "All":
        filtered = filtered[filtered["event_type"] == event_type]
    if symbol != "All":
        filtered = filtered[filtered["symbol"] == symbol]
    if unacknowledged:
        filtered = filtered[filtered["acknowledged"].fillna(0).astype(int).eq(0)]

    st.dataframe(_tony_event_columns(filtered.head(100)), width="stretch", hide_index=True)
    if filtered.empty:
        st.info("No Tony events match the current filters.")
        return
    selected_id = st.selectbox("Selected Tony Event", filtered["id"].tolist())
    if selected_id:
        row = filtered[filtered["id"] == selected_id].iloc[0]
        st.write(
            {
                "created_at": row["created_at"],
                "event_type": row["event_type"],
                "severity": row["severity"],
                "symbol": row["symbol"],
                "source": row["source"],
                "acknowledged": bool(row["acknowledged"]),
                "dismissed": bool(row["dismissed"]),
                "notes": row.get("notes", ""),
            }
        )
        st.write("Title", row["title"])
        st.write("Message", row["message"])
        st.json(json.loads(row["payload_json"] or "{}"))


def render_outcome_analytics(repo: ScannerRepository) -> None:
    st.subheader("Outcome Analytics")
    st.info("Outcome analytics are for model evaluation and research. Seeded demo fixture results are excluded by default and are not proof of strategy quality.")
    filter_cols = st.columns(4)
    include_seeded = filter_cols[0].checkbox("Include seeded demo fixtures", value=False)
    days = filter_cols[1].number_input("Last N days", min_value=0, value=0, help="0 means all available snapshots.")
    min_score = filter_cols[2].number_input("Minimum score", min_value=0.0, max_value=100.0, value=0.0)
    role_filter = filter_cols[3].text_input("Universe role filter")
    snapshots = repo.list_snapshots_for_analytics(
        include_seeded_demo=include_seeded,
        days=int(days) if days else None,
        universe_role=role_filter.strip() or None,
        min_score=min_score if min_score > 0 else None,
    )
    analytics = OutcomeAnalytics(snapshots, include_seeded_demo=include_seeded)
    prepared = analytics.prepared()
    seeded_count = int(prepared["is_seeded_demo"].sum()) if not prepared.empty and "is_seeded_demo" in prepared else 0
    metric_cols = st.columns(5)
    metric_cols[0].metric("Snapshots Reviewed", len(prepared))
    metric_cols[1].metric("Seeded Fixtures", seeded_count)
    metric_cols[2].metric("Triggered", int(prepared["entry_triggered"].sum()) if not prepared.empty else 0)
    metric_cols[3].metric("Target Hits", int(prepared["outcome_label"].isin(["target_hit", "target_before_stop"]).sum()) if not prepared.empty else 0)
    metric_cols[4].metric("Failures", int(prepared["outcome_label"].isin(["stop_hit", "stop_before_target", "failed_setup"]).sum()) if not prepared.empty else 0)
    if prepared.empty:
        st.info("No snapshots match the current analytics filters.")
        return

    setup_summary = analytics.grouped_by("setup_category")
    bucket_summary = analytics.grouped_by("score_bucket")
    role_summary = analytics.grouped_by("universe_role")
    warning_summary = analytics.warning_type_summary()
    outcome_counts = analytics.outcome_counts()

    chart_cols = st.columns(3)
    if not outcome_counts.empty:
        chart_cols[0].plotly_chart(
            go.Figure(data=[go.Bar(x=outcome_counts["outcome_label"], y=outcome_counts["count"])]).update_layout(title="Outcome Counts"),
            width="stretch",
        )
    if not setup_summary.empty:
        chart_cols[1].plotly_chart(
            go.Figure(data=[go.Bar(x=setup_summary["setup_category"], y=setup_summary["target_hit_rate"])]).update_layout(title="Target Rate by Setup"),
            width="stretch",
        )
    if not bucket_summary.empty and "average_result_5d" in bucket_summary.columns:
        chart_cols[2].plotly_chart(
            go.Figure(data=[go.Bar(x=bucket_summary["score_bucket"], y=bucket_summary["average_result_5d"])]).update_layout(title="Avg 5D Return by Score Bucket"),
            width="stretch",
        )

    st.subheader("Setup Category Performance")
    st.dataframe(setup_summary, width="stretch", hide_index=True)
    st.subheader("Score Bucket Performance")
    st.dataframe(bucket_summary, width="stretch", hide_index=True)
    st.subheader("Universe Role Performance")
    st.dataframe(role_summary, width="stretch", hide_index=True)
    st.subheader("Outcome Label Counts")
    st.dataframe(outcome_counts, width="stretch", hide_index=True)
    st.subheader("Warning Type Performance")
    st.dataframe(warning_summary.head(100), width="stretch", hide_index=True)


def _ranked_columns(results: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "symbol",
        "universe_role",
        "final_score",
        "setup_category",
        "latest_close",
        "suggested_entry",
        "suggested_stop",
        "suggested_target_1",
        "risk_reward_ratio",
        "trade_plan_valid",
        "trade_plan_status",
        "key_reason",
        "candidate_summary",
        "warning_count",
    ]
    return results[[column for column in columns if column in results.columns]].rename(
        columns={
            "symbol": "Symbol",
            "universe_role": "Role",
            "final_score": "Score",
            "setup_category": "Setup Category",
            "latest_close": "Close",
            "suggested_entry": "Entry",
            "suggested_stop": "Stop",
            "suggested_target_1": "Target",
            "risk_reward_ratio": "Risk/Reward",
            "trade_plan_valid": "Trade Plan Valid",
            "trade_plan_status": "Trade Plan Status",
            "key_reason": "Key Reason",
            "candidate_summary": "Why / Why Not",
            "warning_count": "Warning Count",
        }
    )


def _snapshot_columns(snapshots: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "id",
        "snapshot_time",
        "symbol",
        "total_score",
        "setup_category",
        "universe_role",
        "snapshot_price",
        "planned_entry_price",
        "planned_entry_rule",
        "entry_status",
        "actual_entry_price",
        "actual_entry_time",
        "close",
        "entry",
        "stop",
        "target",
        "risk_reward",
        "highest_price_seen",
        "lowest_price_seen",
        "result_eod",
        "result_3d",
        "result_5d",
        "result_10d",
        "result_20d",
        "outcome_label",
        "tony_intraday_read",
        "intraday_timeframe",
        "intraday_vwap",
        "intraday_above_vwap",
        "intraday_opening_range_status",
        "notes",
        "trade_plan_valid",
        "trade_plan_status",
        "status",
        "warning_count",
        "candidate_summary",
    ]
    return snapshots[[column for column in columns if column in snapshots.columns]].rename(
        columns={
            "id": "ID",
            "snapshot_time": "Snapshot Time",
            "symbol": "Symbol",
            "total_score": "Score",
            "setup_category": "Setup Category",
            "universe_role": "Role",
            "snapshot_price": "Snapshot Price",
            "planned_entry_price": "Planned Entry",
            "planned_entry_rule": "Planned Rule",
            "entry_status": "Entry Status",
            "actual_entry_price": "Actual Entry",
            "actual_entry_time": "Actual Entry Time",
            "close": "Close",
            "entry": "Entry",
            "stop": "Stop",
            "target": "Target",
            "risk_reward": "Risk/Reward",
            "highest_price_seen": "High Seen",
            "lowest_price_seen": "Low Seen",
            "result_eod": "EOD Return",
            "result_3d": "3D Return",
            "result_5d": "5D Return",
            "result_10d": "10D Return",
            "result_20d": "20D Return",
            "outcome_label": "Outcome",
            "tony_intraday_read": "Tony Intraday Read",
            "intraday_timeframe": "Intraday TF",
            "intraday_vwap": "Intraday VWAP",
            "intraday_above_vwap": "Above VWAP",
            "intraday_opening_range_status": "Opening Range",
            "notes": "Notes",
            "trade_plan_valid": "Trade Plan Valid",
            "trade_plan_status": "Trade Plan Status",
            "status": "Status",
            "warning_count": "Warning Count",
            "candidate_summary": "Why / Why Not",
        }
    )


def _default_primary_candidates(results: pd.DataFrame) -> pd.DataFrame:
    """Return the default opportunity list without context/reference rows."""
    if results.empty:
        return results
    return results[
        results["universe_role"].eq("primary_candidate")
        & ~results["is_etf_or_benchmark"]
        & ~results["is_mega_cap"]
        & results["trade_plan_valid"]
        & ~results["setup_category"].isin(["Weak / Avoid", "Overextended / Wait", "ETF / Benchmark Reference", "Invalid Trade Plan"])
    ]


def _count_outcome(outcome_counts: pd.DataFrame, labels: list[str]) -> int:
    if outcome_counts.empty:
        return 0
    return int(outcome_counts[outcome_counts["outcome_label"].isin(labels)]["count"].sum())


def _latest_event_time(events: pd.DataFrame, event_type: str) -> str | None:
    if events.empty:
        return None
    rows = events[events["event_type"] == event_type]
    if rows.empty:
        return None
    return str(rows.iloc[0]["created_at"])


def _fallback_symbols_from_events(events: pd.DataFrame) -> list[str]:
    return missing_symbols_from_events(events)


def _tony_event_columns(events: pd.DataFrame) -> pd.DataFrame:
    columns = ["created_at", "severity", "event_type", "symbol", "title", "message", "acknowledged", "dismissed"]
    return events[[column for column in columns if column in events.columns]].rename(
        columns={
            "created_at": "Created",
            "severity": "Severity",
            "event_type": "Event Type",
            "symbol": "Symbol",
            "title": "Title",
            "message": "Message",
            "acknowledged": "Acknowledged",
            "dismissed": "Dismissed",
        }
    )


def _cc_hypothesis_cards(analyst_events: pd.DataFrame, limit: int = 8) -> None:
    """Compact hypothesis cards for the Command Center. No orders, no buy/sell wording."""
    if analyst_events.empty:
        st.info("No analyst hypothesis events yet. Run a scan to generate analyst reads.")
        return
    st.caption("Tony is analyzing, not trading. No orders, paper trades, or broker execution.")
    priority_icon = {
        "high_priority": "🔴",
        "watch": "🟡",
        "low_priority": "🟢",
        "avoid": "⛔",
        "reference_only": "📊",
    }
    action_labels = {
        "snapshot_only": "Snapshot Only",
        "watch_only": "Watch Only",
        "avoid": "Avoid",
        "needs_more_data": "Needs More Data",
        "reference_only": "Reference Only",
    }
    for _, ev in analyst_events.head(limit).iterrows():
        payload = json.loads(ev.get("payload_json") or "{}")
        sym = ev.get("symbol") or payload.get("symbol", "?")
        priority = payload.get("priority_label", "")
        action = payload.get("recommended_action", "")
        setup = payload.get("setup_read", "")
        icon = priority_icon.get(priority, "")
        age = event_age_label(ev.get("created_at"))
        header = f"{icon} **{sym}** — {action_labels.get(action, action)} | {setup} | {age}"
        with st.expander(header, expanded=False):
            card_cols = st.columns(5)
            card_cols[0].metric("Priority", priority.replace("_", " ").title() if priority else "—")
            card_cols[1].metric("Volume", payload.get("volume_read", "—").replace("_", " "))
            card_cols[2].metric("Risk", payload.get("risk_read", "—").replace("_", " "))
            card_cols[3].metric("Data", payload.get("data_quality_read", "—").replace("_", " "))
            card_cols[4].metric("Intraday", payload.get("intraday_read", "—").replace("_", " "))
            concerns = payload.get("concerns", [])
            if concerns:
                st.caption("Concerns: " + ", ".join(str(c) for c in concerns))
            hypothesis = ev.get("message") or payload.get("tony_hypothesis", "")
            if hypothesis:
                st.write(hypothesis)


def render_watch_health(repo: ScannerRepository) -> None:
    """Watch Health panel — universe size, rotation stats, API/batch requests, rate limits."""
    settings = load_scanner_settings()
    events = repo.list_tony_events(limit=100)

    # Universe metrics from config
    universe_total = 0
    active_count = 0
    core_count = 0
    discovery_count = 0
    try:
        universe_cfg_path = settings.universe_config_path
        all_syms = load_universe(universe_cfg_path)
        universe_tags = load_universe_tags(universe_cfg_path)
        universe_meta = load_universe_metadata(universe_cfg_path)
        core_count = sum(1 for tags in universe_tags.values() if "watchlist_core" in tags)
        discovery_count = sum(1 for tags in universe_tags.values() if "discovery" in tags)
        active_count = sum(1 for m in universe_meta.values() if m.universe_role != "excluded_by_default")
        universe_total = len(all_syms)
    except Exception:
        pass

    # Rotation stats from latest universe_rotation_summary event
    rotation_event = latest_event_of_type(events, "universe_rotation_summary")
    symbols_selected = None
    open_snapshot_count = None
    bucket_id = None
    if rotation_event:
        rp = json.loads(rotation_event.get("payload_json") or "{}")
        symbols_selected = rp.get("symbols_selected") or rp.get("cycle_symbols_count")
        open_snapshot_count = rp.get("open_snapshot_count")
        bucket_id = rp.get("bucket_id") or rp.get("rotation_bucket_id")

    # API/batch stats from latest batch_fetch_summary
    batch_event = latest_event_of_type(events, "batch_fetch_summary")
    api_requests = None
    batch_requests = None
    if batch_event:
        bp = json.loads(batch_event.get("payload_json") or "{}")
        api_requests = bp.get("api_requests_used") or bp.get("api_requests")
        batch_requests = bp.get("batch_requests_used") or bp.get("batch_requests")

    # Rate limit / fallback counts from recent events
    rate_limit_count = int(filter_events_by_type(events, "rate_limit_warning").shape[0])
    fallback_count = int(
        filter_events_by_type(events, "data_provider_fallback").shape[0]
        + filter_events_by_type(events, "all_symbol_fallback").shape[0]
    )
    stale_count = int(filter_events_by_type(events, "stale_data_warning").shape[0])

    st.subheader("Watch Health")
    row1 = st.columns(4)
    row1[0].metric("Universe Total", universe_total or "—")
    row1[1].metric("Active Symbols", active_count or "—")
    row1[2].metric("Watchlist Core", core_count or "—")
    row1[3].metric("Discovery Pool", discovery_count or "—")

    row2 = st.columns(4)
    row2[0].metric("Symbols Selected/Cycle", symbols_selected if symbols_selected is not None else "—")
    row2[1].metric("Open Snapshots (rotation)", open_snapshot_count if open_snapshot_count is not None else repo.count_open_candidate_snapshots())
    row2[2].metric("Rotation Bucket", bucket_id if bucket_id is not None else "—")
    rotation_cfg = settings.watch_universe_rotation or {}
    row2[3].metric("Max/Cycle", rotation_cfg.get("max_symbols_per_cycle", "—"))

    row3 = st.columns(4)
    row3[0].metric("API Requests (last batch)", api_requests if api_requests is not None else "—")
    row3[1].metric("Batch Requests (last batch)", batch_requests if batch_requests is not None else "—")
    row3[2].metric("Rate-Limit Warnings", rate_limit_count)
    row3[3].metric("Fallback / Stale Events", f"{fallback_count} / {stale_count}")

    if rate_limit_count > 0:
        st.warning(f"{rate_limit_count} rate-limit warning(s). Reduce max_symbols_per_cycle or increase request_sleep_seconds.")


def render_data_quality_panel(repo: ScannerRepository) -> None:
    """Data Quality panel — IEX notice, fallback summary, stale warning, no key values shown."""
    settings = load_scanner_settings()
    effective_provider = resolve_effective_provider(settings)
    events = repo.list_tony_events(limit=100)

    dq_event = latest_event_of_type(events, "analyst_data_quality")
    real_count = demo_count = fallback_count = stale_count = seeded_count = total = 0
    dq_provider = effective_provider
    if dq_event:
        dp = json.loads(dq_event.get("payload_json") or "{}")
        real_count = dp.get("daily_real_alpaca", dp.get("alpaca_iex_real_data", 0))
        demo_count = dp.get("demo_data", 0)
        fallback_count = dp.get("fallback_data", 0)
        stale_count = dp.get("stale_data", 0)
        seeded_count = dp.get("seeded_demo_fixture", 0)
        total = dp.get("total_candidates", 0)
        dq_provider = dp.get("provider", effective_provider)

    st.subheader("Data Quality")

    if effective_provider == "alpaca_iex":
        st.warning(
            "**Alpaca IEX single-exchange notice:** IEX is not full SIP consolidated tape. "
            "Price/volume data may differ from NBBO. Research and scanning only — no orders placed."
        )
    elif is_fallback_provider(effective_provider):
        st.error(
            f"**Provider is {effective_provider} (demo/fallback).** Real market data is not active. "
            "Add Alpaca API keys to .env and set real_provider_enabled: true."
        )

    cols = st.columns(5)
    cols[0].metric("Real IEX Data", real_count)
    cols[1].metric("Demo Data", demo_count)
    cols[2].metric("Fallback Data", fallback_count)
    cols[3].metric("Stale Data", stale_count)
    cols[4].metric("Seeded Fixtures", seeded_count)

    if dq_event:
        age = event_age_label(dq_event.get("created_at"))
        st.caption(f"From latest analyst_data_quality event ({age}) — provider: {dq_provider} — {total} candidates")

    if fallback_count > 0 or stale_count > 0:
        st.warning(
            f"{fallback_count} fallback and {stale_count} stale data reads in the last scan. "
            "Analyst reads for these symbols used degraded data."
        )

    if demo_count == total and total > 0:
        st.error("All candidates are using demo data. Real Alpaca IEX data is not flowing.")


def render_market_day_review(repo: ScannerRepository) -> None:
    """Compact market-day data quality review for real vs demo hygiene."""
    st.subheader("Market Day Review")
    st.caption("Research-only data quality review. Tony does not place orders or make trade recommendations.")
    settings = load_scanner_settings()
    quarantine_cfg = load_symbol_quarantine_config(settings)
    configured_quarantine = [entry.symbol for entry in quarantine_cfg.entries]
    events = repo.list_tony_events(limit=300)
    snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=True, limit=5000)
    analytics = OutcomeAnalytics(snapshots, include_seeded_demo=True, today=True, real_only=True)
    prepared = analytics.prepared()
    source_counts = analytics.raw_data_source_counts()
    source_map = {
        str(row["data_source_classification"]): int(row["count"])
        for row in source_counts.to_dict("records")
    } if not source_counts.empty else {}
    exclusions = analytics.exclusion_counts()
    intraday_event = latest_event_of_type(events, "intraday_analysis_summary")
    intraday_payload = json.loads(intraday_event.get("payload_json") or "{}") if intraday_event else {}
    fallback_symbols = _fallback_symbols_from_events(events)
    analyst_events = filter_events_by_type(events, "analyst_candidate_hypothesis")
    priority_counts = count_hypothesis_by_priority(analyst_events)

    cols = st.columns(6)
    cols[0].metric("Real Rows", source_map.get("real_alpaca", 0))
    cols[1].metric("Demo Excluded", exclusions["demo_rows_excluded"])
    cols[2].metric("Legacy Excluded", exclusions["legacy_unknown_rows_excluded"])
    cols[3].metric("Snapshots Today", len(prepared))
    cols[4].metric("Real Intraday", int(intraday_payload.get("real_intraday_count", 0) or 0))
    cols[5].metric("Stale Intraday", int(intraday_payload.get("intraday_stale_count", 0) or 0))

    st.caption(f"Missing real-data symbols (events): {', '.join(fallback_symbols[:12]) if fallback_symbols else 'none'}")
    st.caption(
        f"Configured quarantined: {', '.join(configured_quarantine) if configured_quarantine else 'none'} "
        "(excluded from real-data-only scan/watch; still in universe YAML)"
    )
    if quarantine_cfg.replacement_symbols:
        st.caption(f"Configured replacements: {', '.join(quarantine_cfg.replacement_symbols)}")
    repeated = ", ".join(f"{key}: {value}" for key, value in priority_counts.items())
    st.caption(f"Tony repeated symbols: {repeated or 'none'}")
    if source_map.get("demo_generated", 0) or source_map.get("legacy_unknown", 0) or source_map.get("missing_real_data", 0):
        st.warning("Demo, missing-real-data, or legacy rows exist in the database but are excluded from this real-only review.")


def render_outcome_snapshot_panel(repo: ScannerRepository) -> None:
    """Outcome Snapshot panel — today count, open/watch, triggered, hit/miss. Seeded demo excluded."""
    outcome_counts = repo.count_candidate_snapshots_by_outcome()
    open_count = repo.count_open_candidate_snapshots()
    triggered_count = repo.count_triggered_candidate_snapshots()
    today_count = snapshots_today_count(repo)

    st.subheader("Snapshot Summary")
    st.caption("Seeded demo fixtures are excluded from all counts below.")

    cols = st.columns(6)
    cols[0].metric("Snapshots Today", today_count)
    cols[1].metric("Open / Watch", open_count)
    cols[2].metric("Triggered", triggered_count)
    cols[3].metric("Target Hit", _count_outcome(outcome_counts, ["target_hit", "target_before_stop"]))
    cols[4].metric("Stop Hit", _count_outcome(outcome_counts, ["stop_hit", "stop_before_target"]))
    cols[5].metric("Insufficient Data", _count_outcome(outcome_counts, ["insufficient_future_data"]))


def _render_safety_strip(real_only: bool) -> None:
    st.info(
        "**Research only** · No broker orders · No paper trades · No live trades · "
        "Tony does not place trades · No demo data in active learning."
    )
    if real_only:
        st.success("**Real data only:** Yes — demo data is blocked for active Tony watch and learning.")
    else:
        st.warning("Real-data-only mode is off in config. Check settings before trusting results.")


def _load_research_snapshots(repo: ScannerRepository, limit: int = 2000) -> pd.DataFrame:
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False, limit=limit)
    return filter_research_snapshots(snaps)


def _dashboard_context(repo: ScannerRepository, results: pd.DataFrame) -> dict:
    """Shared Tony dashboard context for Home and product tabs."""
    settings = load_scanner_settings()
    watch_config = settings.scheduled_watch or {}
    quarantine_cfg = load_symbol_quarantine_config(settings)
    effective_provider = resolve_effective_provider(settings)
    real_only = real_data_only_enabled(settings)
    demo_blocked = real_only and not settings.allow_demo_fallback_in_watch
    stale_heartbeat_minutes = int(watch_config.get("stale_heartbeat_minutes", 10))
    today_utc = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")

    watch_run = repo.latest_watch_run()
    wsr_label = watch_status_label(watch_run, stale_heartbeat_minutes)
    events = repo.list_tony_events(limit=300)
    analyst_events = repo.list_tony_events(event_type="analyst_candidate_hypothesis", limit=50)
    mkt_events = repo.list_tony_events(event_type="analyst_market_context", limit=3)

    latest_scan_ts = _latest_event_time(events, "scan_completed")
    waiting = is_waiting_for_market_open(events)
    beginner_status = tony_status_beginner_label(wsr_label, waiting_for_market=waiting)

    missing_symbols = missing_symbols_from_events(events)
    quarantined_symbols = list(quarantine_cfg.symbols)
    rate_limit_count = int(filter_events_by_type(events, "rate_limit_warning").shape[0])
    all_fallback = bool(latest_event_of_type(events, "all_symbol_fallback"))

    health_issues = collect_health_issues(
        watch_status=wsr_label,
        real_data_only=real_only,
        provider=effective_provider,
        demo_blocked=demo_blocked,
        rate_limit_count=rate_limit_count,
        all_fallback=all_fallback,
    )

    research_snaps = _load_research_snapshots(repo)
    phases = split_snapshots_by_phase(research_snaps)
    picks_df = build_tony_pick_product_rows(research_snaps)
    tracking_df = build_active_tracking_product_rows(research_snaps)
    pending_symbol_count = 0
    if not picks_df.empty:
        pending_symbol_count = int(
            picks_df.apply(lambda row: str(row.get("entry_status") or "").strip().lower() == "pending", axis=1).sum()
        )

    trigger_counts = trigger_tracker_summary(
        planned_today=repo.count_planned_triggers_today(today_utc),
        triggered_today=repo.count_entry_trigger_status("triggered", today_utc),
        pending=pending_symbol_count,
        expired_not_triggered=repo.count_entry_trigger_status("expired")
        + repo.count_entry_trigger_status("not_triggered"),
        missing_real_data=repo.count_entry_trigger_status("missing_real_data"),
    )

    mkt_row = latest_event_of_type(mkt_events, "analyst_market_context")
    mkt_payload = json.loads(mkt_row.get("payload_json") or "{}") if mkt_row else {}
    market_headline, market_line = market_context_plain_english(
        mkt_payload.get("context_label"),
        mkt_row.get("message") if mkt_row else None,
    )
    interesting_count, risky_count = count_interesting_and_risky_stocks(analyst_events)
    pl_summary = summarize_research_pl(research_snaps)

    batch_event = latest_event_of_type(events, "batch_fetch_summary")
    api_requests = symbols_scanned = None
    if batch_event:
        bp = json.loads(batch_event.get("payload_json") or "{}")
        api_requests = bp.get("api_requests_used") or bp.get("api_requests")
        symbols_scanned = bp.get("symbols_fetched") or bp.get("symbols_scanned")
    if symbols_scanned is None and not results.empty:
        symbols_scanned = len(results)

    return {
        "settings": settings,
        "watch_run": watch_run,
        "wsr_label": wsr_label,
        "beginner_status": beginner_status,
        "real_only": real_only,
        "demo_blocked": demo_blocked,
        "effective_provider": effective_provider,
        "missing_symbols": missing_symbols,
        "quarantined_symbols": quarantined_symbols,
        "events": events,
        "analyst_events": analyst_events,
        "latest_scan_ts": latest_scan_ts,
        "health_issues": health_issues,
        "rate_limit_count": rate_limit_count,
        "market_headline": market_headline,
        "market_line": market_line,
        "interesting_count": interesting_count,
        "risky_count": risky_count,
        "trigger_counts": trigger_counts,
        "research_snaps": research_snaps,
        "picks_df": picks_df,
        "tracking_df": tracking_df,
        "phases": phases,
        "pl_summary": pl_summary,
        "api_requests": api_requests,
        "symbols_scanned": symbols_scanned,
        "today_utc": today_utc,
        "waiting_for_market": waiting,
        "watch_error_message": (
            str(watch_run.get("latest_error_message") or "").strip() if watch_run else ""
        ),
    }


def render_home(repo: ScannerRepository, results: pd.DataFrame) -> None:
    """Home — executive briefing (short); full picker lives on Tony Picks."""
    inject_tony_theme()
    ctx = _dashboard_context(repo, results)
    render_hero(real_data_only=ctx["real_only"])

    tony_status = tony_status_home_message(
        ctx["beginner_status"],
        ctx["wsr_label"],
        waiting_for_market=ctx["waiting_for_market"],
        has_data_issues=bool(ctx["missing_symbols"]),
        watch_error_message=ctx.get("watch_error_message"),
    )
    last_scan = event_age_label(ctx["latest_scan_ts"]) if ctx["latest_scan_ts"] else "No scan yet"
    watchlist_count = len(ctx["picks_df"]) + len(ctx["tracking_df"])
    render_stat_grid([
        ("Tony Status", tony_status, "purple", None),
        ("Real Data Only", "Yes" if ctx["real_only"] else "No", "blue", None),
        ("Tony Watchlist", str(watchlist_count), "info", "Picks + active tracking"),
        ("Active Tracking", str(len(ctx["tracking_df"])), "purple", "Triggered setups"),
        ("Waiting Alerts", str(ctx["trigger_counts"]["pending_alerts"]), "amber", None),
        ("Last Scan", last_scan, "neutral", None),
    ])

    briefing_line(ctx["market_line"] or "No market read yet — Tony will update after the next scan.")

    section_header("Top 3 Tony Picks")
    home_picks = select_home_preview_picks(ctx["picks_df"], limit=3)
    if home_picks.empty:
        st.info("No Tony Picks yet. Open Tony Picks after the next watch cycle.")
    else:
        for _, row in home_picks.iterrows():
            render_pick_preview_card(build_pick_card_model(row))

    section_header("Top 3 Active Tracking")
    home_tracking = select_home_tracking_rows(ctx["tracking_df"], limit=3)
    if home_tracking.empty:
        st.info("No active tracked setups right now.")
    else:
        for _, row in home_tracking.iterrows():
            render_tracking_preview_card(build_tracked_setup_card_model(row))

    section_header("What to review today")
    review_lines = "\n".join(
        f"- {item}"
        for item in home_briefing_review_items(
            interesting_count=ctx["interesting_count"],
            risky_count=ctx["risky_count"],
            pending_triggers=ctx["trigger_counts"]["pending_alerts"],
            missing_symbols=ctx["missing_symbols"],
        )
    )
    st.markdown(review_lines)


def render_tony_watchlist(repo: ScannerRepository, results: pd.DataFrame) -> None:
    """Tony Watchlist — unified Picks + Active Tracking in one tab."""
    inject_tony_theme()
    ctx = _dashboard_context(repo, results)
    section_header("Tony Watchlist")
    st.caption(
        "All symbols Tony is currently watching or tracking. "
        "Watching/waiting cards show the entry trigger; active cards show live research P/L. "
        "Research only — no trades placed."
    )
    st.caption(risk_reward_definition_text())

    watchlist = build_tony_watchlist_rows(ctx["research_snaps"])

    if watchlist.empty:
        st.info("Tony Watchlist is empty. Run a scan and watch cycle to populate.")
        return

    filter_cols = st.columns(2)
    lifecycle_filter = filter_cols[0].selectbox(
        "Show",
        ["All", "Watching", "Waiting for trigger", "Active", "Weakening"],
        key="watchlist_lifecycle_filter",
    )
    sort_choice = filter_cols[1].selectbox(
        "Sort by", ["Newest", "Symbol"], key="watchlist_sort"
    )

    rows_to_show = watchlist.copy()
    if lifecycle_filter != "All":
        state_map = {
            "Watching": "watching",
            "Waiting for trigger": "waiting_for_trigger",
            "Active": "active",
            "Weakening": "weakening",
        }
        state = state_map.get(lifecycle_filter)
        if state and "lifecycle_state" in rows_to_show.columns:
            rows_to_show = rows_to_show[rows_to_show["lifecycle_state"].eq(state)].copy()

    if sort_choice == "Symbol":
        rows_to_show = rows_to_show.sort_values("symbol")

    if rows_to_show.empty:
        st.info(f"No symbols in '{lifecycle_filter}' state right now.")
        return

    for _, row in rows_to_show.iterrows():
        lifecycle = str(row.get("lifecycle_state") or "watching")
        if lifecycle in ("active", "weakening"):
            render_tracking_position_card(build_tracked_setup_card_model(row))
        else:
            render_pick_signal_card(build_pick_card_model(row))


def render_tony_picks(repo: ScannerRepository, results: pd.DataFrame) -> None:
    """Tony Picks — full stock-picker / watchlist."""
    inject_tony_theme()
    ctx = _dashboard_context(repo, results)
    section_header("Tony Picks")
    st.caption("Here are the current Tony Picks. Entry trigger means the price/confirmation Tony still needs before tracking starts. Research only — no trades placed.")
    st.caption(risk_reward_definition_text())

    if ctx["picks_df"].empty:
        st.info("No Tony Picks on the watchlist right now.")
        return

    filter_cols = st.columns(2)
    filter_choice = filter_cols[0].selectbox(
        "Filter", ["All", "Waiting for alert", "Tony Pick"], key="picks_filter"
    )
    sort_choice = filter_cols[1].selectbox("Sort by", ["Newest", "Tony rating", "Symbol"], key="picks_sort")

    cards: list[dict[str, str]] = []
    for _, row in ctx["picks_df"].iterrows():
        card = build_pick_card_model(row)
        if filter_choice == "Waiting for alert" and card["phase"] != "waiting_alert":
            continue
        if filter_choice == "Tony Pick" and card["phase"] != "pick":
            continue
        cards.append(card)

    if sort_choice == "Symbol":
        cards.sort(key=lambda item: item["symbol"])
    elif sort_choice == "Tony rating":
        cards.sort(key=lambda item: item["tony_rating"])

    for card in cards:
        render_pick_signal_card(card)


def render_active_tracking(repo: ScannerRepository, results: pd.DataFrame) -> None:
    """Active Tracking — post-trigger research position cards."""
    inject_tony_theme()
    ctx = _dashboard_context(repo, results)
    section_header("Active Tracking")
    st.caption("Research position cards after an entry alert triggers. Not live trading.")
    st.caption(risk_reward_definition_text())

    if ctx["tracking_df"].empty:
        st.info("No active tracked setups. Tony moves symbols here after a planned entry alert triggers.")
        return

    for _, row in ctx["tracking_df"].iterrows():
        render_tracking_position_card(build_tracked_setup_card_model(row))


def _results_prepared_for_period(repo: ScannerRepository, period: str) -> pd.DataFrame:
    snaps = repo.list_snapshots_for_analytics(include_seeded_demo=False, limit=5000)
    analytics = OutcomeAnalytics(snaps, include_seeded_demo=False, real_only=True)
    prepared = filter_research_snapshots(analytics.prepared())
    if prepared.empty or "snapshot_time" not in prepared.columns:
        return prepared
    dates = prepared["snapshot_time"].fillna("").astype(str).str.slice(0, 10)
    if period == "Today":
        today = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
        return prepared[dates.eq(today)].copy()
    if period == "This week":
        cutoff = (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=7)).strftime("%Y-%m-%d")
        return prepared[dates.ge(cutoff)].copy()
    return prepared


def render_results(repo: ScannerRepository) -> None:
    """Results — plain-English research performance."""
    inject_tony_theme()
    section_header("Results")
    st.caption("What happened after Tony noticed each setup.")

    period = st.radio("Period", ["Today", "This week", "All time"], horizontal=True, key="results_period")
    prepared = _results_prepared_for_period(repo, period)
    active_tracking_rows = build_active_tracking_product_rows(prepared)
    result_rows = build_results_product_rows(prepared)
    summary = summarize_results_plain_english(
        prepared,
        period_label=period,
        active_tracking_rows=active_tracking_rows,
    )
    summary.update(summarize_results_product_counts(result_rows))
    avg_pl = avg_research_pl_from_prepared(prepared)
    render_results_performance(summary, avg_pl=avg_pl, period=period)
    st.caption(risk_reward_definition_text())

    filter_name = st.radio("Result filter", RESULTS_FILTERS, horizontal=True, key="results_filter")
    filtered_rows = filter_results_product_rows(result_rows, filter_name)
    if filtered_rows.empty:
        st.info("No result cards match this filter yet.")
        return
    for _, row in filtered_rows.iterrows():
        render_result_card(build_result_card_model(row))


def render_system_health(repo: ScannerRepository, results: pd.DataFrame) -> None:
    """Settings / System Health — technical and legacy developer views."""
    ctx = _dashboard_context(repo, results)
    settings = ctx["settings"]
    watch_config = settings.scheduled_watch or {}

    health = summarize_system_health(
        watch_status=ctx["wsr_label"],
        beginner_status=ctx["beginner_status"],
        real_data_only=ctx["real_only"],
        provider=ctx["effective_provider"],
        demo_blocked=ctx["demo_blocked"],
        missing_symbols=ctx["missing_symbols"],
        quarantined_symbols=ctx["quarantined_symbols"],
        last_scan_age=event_age_label(ctx["latest_scan_ts"]) if ctx["latest_scan_ts"] else "No scan yet",
        api_requests=ctx["api_requests"],
        symbols_scanned=ctx["symbols_scanned"],
        rate_limit_count=ctx["rate_limit_count"],
        health_issues=ctx["health_issues"],
    )

    st.subheader("Settings / System Health")
    st.caption("Technical details and debug views. Main Tony tabs stay simple.")

    st.markdown("#### Data & safety")
    cols = st.columns(4)
    cols[0].metric("Real data only", "Yes" if health["real_data_only"] else "No")
    cols[1].metric("Provider", health["provider"])
    cols[2].metric("Demo blocked", "Yes" if health["demo_blocked"] else "No")
    cols[3].metric("Tony status", health["tony_status"])
    st.caption(f"**Missing real data:** {summarize_symbol_list(health['missing_symbols'])}")
    st.caption(f"**Quarantined:** {summarize_symbol_list(health['quarantined_symbols'])}")

    st.markdown("#### Operations")
    ops = st.columns(4)
    ops[0].metric("Watch status", health["watch_status"])
    ops[1].metric("Last scan", health["last_scan_age"])
    ops[2].metric("API requests (last batch)", health["api_requests"] if health["api_requests"] is not None else "—")
    ops[3].metric("Symbols scanned", health["symbols_scanned"] if health["symbols_scanned"] is not None else "—")
    if health["rate_limit_count"]:
        st.warning(f"{health['rate_limit_count']} rate-limit warning(s) in recent events.")
    if health["health_issues"]:
        for issue in health["health_issues"]:
            st.warning(issue)

    stop_file_path = Path(str(watch_config.get("stop_file", "data/STOP_WATCH_MODE")))
    if not stop_file_path.is_absolute():
        stop_file_path = Path.cwd() / stop_file_path
    st.caption(f"Watch stop file: `{stop_file_path}`")

    reconciliation = summarize_product_reconciliation(ctx["research_snaps"])
    st.markdown("#### Reconciliation")
    rec = st.columns(4)
    rec[0].metric("Raw snapshot rows", reconciliation["raw_snapshot_rows"])
    rec[1].metric("Visible product symbols", reconciliation["product_visible_symbols"])
    rec[2].metric("Incomplete hidden", reconciliation["incomplete_rows_hidden_from_product_views"])
    rec[3].metric("History hidden", reconciliation["history_rows_hidden_from_product_views"])
    st.caption("Dashboard dedupe and hiding change visibility only. Raw candidate snapshot history remains in `data/trading_bot.db` and legacy developer views.")

    with st.expander("Legacy developer views (tables, charts, raw events)", expanded=False):
        st.caption("Developer/debug only. Not part of the main Tony product flow.")
        legacy_tab = st.tabs([
            "Overview",
            "Ranked Stocks",
            "Stock Detail",
            "Snapshots",
            "Outcome Analytics",
            "Tony Events",
            "Manual Picks",
            "Paper Journal",
            "Performance",
            "Command Center (V15.5)",
        ])
        with legacy_tab[0]:
            render_overview(repo, results)
            render_data_provider_status(repo)
        with legacy_tab[1]:
            render_ranked(results)
        with legacy_tab[2]:
            render_detail(results)
        with legacy_tab[3]:
            render_candidate_snapshots(repo)
        with legacy_tab[4]:
            render_outcome_analytics(repo)
        with legacy_tab[5]:
            render_tony_stocks(repo)
        with legacy_tab[6]:
            render_manual_picks(repo, results)
        with legacy_tab[7]:
            render_paper_journal(repo)
        with legacy_tab[8]:
            render_performance(repo)
        with legacy_tab[9]:
            render_command_center_legacy(repo, results, ctx)

    with st.expander("Watch health & data quality panels", expanded=False):
        render_watch_health(repo)
        render_data_quality_panel(repo)
        render_market_day_review(repo)
        render_outcome_snapshot_panel(repo)
        render_tony_learning_panel(repo)


def render_command_center_legacy(
    repo: ScannerRepository,
    results: pd.DataFrame,
    ctx: dict | None = None,
) -> None:
    """V15.5 Command Center preserved for power users under System Health."""
    if ctx is None:
        ctx = _dashboard_context(repo, results)
    settings = ctx["settings"]
    watch_run = ctx["watch_run"]
    wsr_label = ctx["wsr_label"]
    beginner_status = ctx["beginner_status"]
    real_only = ctx["real_only"]
    demo_blocked = ctx["demo_blocked"]
    effective_provider = ctx["effective_provider"]
    events = ctx["events"]
    analyst_events = ctx["analyst_events"]
    latest_scan_ts = ctx["latest_scan_ts"]
    health_issues = ctx["health_issues"]
    missing_symbols = ctx["missing_symbols"]
    quarantined_symbols = ctx["quarantined_symbols"]
    trigger_counts = ctx["trigger_counts"]
    today_utc = ctx["today_utc"]

    snaps_today = snapshots_today_dataframe(repo)
    snap_lookup = snapshot_symbol_lookup(snaps_today)
    interesting_count, risky_count = ctx["interesting_count"], ctx["risky_count"]
    outcome_today = eod_outcome_summary_today(snaps_today)
    updated_today = 0
    if not snaps_today.empty and "last_checked_at" in snaps_today.columns:
        updated_today = int(
            snaps_today["last_checked_at"].fillna("").astype(str).str.slice(0, 10).eq(today_utc).sum()
        )

    review_items = human_review_items(
        interesting_count=interesting_count,
        risky_count=risky_count,
        pending_triggers=trigger_counts["pending_alerts"],
        missing_symbols=missing_symbols,
        quarantined_symbols=quarantined_symbols,
        health_issues=health_issues,
    )

    st.caption("Legacy Command Center (V15.5). Use Home tab for the daily briefing.")
    st.markdown("### A. Tony Status")
    status_cols = st.columns(4)
    status_cols[0].metric("Is Tony running?", beginner_status)
    status_cols[1].metric("Heartbeat", event_age_label(watch_run.get("last_heartbeat_at")) if watch_run else "—")
    status_cols[2].metric("Last scan", event_age_label(latest_scan_ts) if latest_scan_ts else "No scan yet")
    status_cols[3].metric("Research-only", "Yes — no trades")

    st.markdown("### D. Tony's Top Watches")
    top_rows = build_top_watch_rows(analyst_events, snap_lookup, limit=10)
    if top_rows:
        st.dataframe(pd.DataFrame(top_rows), hide_index=True, use_container_width=True)

    st.markdown("### What you should review")
    for item in review_items:
        st.markdown(f"- {item}")

    rate_limit_count = ctx["rate_limit_count"]
    with st.expander("Advanced technical details", expanded=False):
        watch_config = settings.scheduled_watch or {}
        batch_event = latest_event_of_type(events, "batch_fetch_summary")
        api_requests = ctx["api_requests"]
        symbols_scanned = ctx["symbols_scanned"]
        latest_watch_ts = _latest_event_time(events, "watch_cycle_completed")
        pri_counts = count_hypothesis_by_priority(analyst_events)
        adv1 = st.columns(4)
        adv1[0].metric("Internal watch status", wsr_label)
        adv1[1].metric("Provider", effective_provider)
        adv1[2].metric("API requests", api_requests if api_requests is not None else "—")
        adv1[3].metric("Rate-limit warnings", rate_limit_count)
        _cc_hypothesis_cards(analyst_events, limit=8)


def render_tony_learning_panel(repo: ScannerRepository) -> None:
    """Compact Tony Learning section — early tracking of hypothesis-to-outcome patterns."""
    with st.expander("Tony Learning — Early Hypothesis Tracking", expanded=False):
        st.caption(
            "Early tracking only. Not enough history yet to draw conclusions. "
            "Research mode — not evidence of real market edge. "
            "Seeded demo fixtures excluded."
        )
        try:
            snapshots = repo.list_snapshots_for_analytics(include_seeded_demo=False, limit=2000)
            analytics = OutcomeAnalytics(snapshots, include_seeded_demo=False, real_only=True)
            prepared = analytics.prepared()
        except Exception:
            st.info("Tony Learning data not available yet.")
            return

        if prepared.empty:
            st.info("No real-data snapshots yet. Run watch mode to collect snapshots.")
            return

        has_tony = (
            "tony_analysis_version" in prepared.columns
            and prepared["tony_analysis_version"].notna().any()
        )
        analyzed_count = (
            int(prepared["tony_analysis_version"].notna().sum())
            if "tony_analysis_version" in prepared.columns
            else 0
        )
        st.caption(
            f"{len(prepared)} real-data snapshot(s) reviewed. "
            f"{analyzed_count} have Tony analysis attached."
        )

        if not has_tony:
            st.info(
                "No snapshots with Tony analysis yet. "
                "Watch mode attaches Tony reads to new snapshots going forward."
            )
            return

        _tony_learning_compact_cols = [
            "total_snapshots", "target_hit_count", "stop_hit_count",
            "target_hit_rate", "failure_rate", "insufficient_future_data_count",
        ]

        pri_table = analytics.grouped_by("tony_priority_label")
        if not pri_table.empty and "tony_priority_label" in pri_table.columns:
            st.markdown("**By Tony Priority Label**")
            display_cols = ["tony_priority_label"] + [c for c in _tony_learning_compact_cols if c in pri_table.columns]
            st.dataframe(pri_table[display_cols], hide_index=True)

        action_table = analytics.grouped_by("tony_recommended_action")
        if not action_table.empty and "tony_recommended_action" in action_table.columns:
            st.markdown("**By Recommended Action**")
            display_cols = ["tony_recommended_action"] + [c for c in _tony_learning_compact_cols if c in action_table.columns]
            st.dataframe(action_table[display_cols], hide_index=True)

        setup_table = analytics.grouped_by("tony_setup_read")
        if not setup_table.empty and "tony_setup_read" in setup_table.columns:
            st.markdown("**By Setup Read**")
            display_cols = ["tony_setup_read"] + [c for c in _tony_learning_compact_cols if c in setup_table.columns]
            st.dataframe(setup_table[display_cols], hide_index=True)

        risk_table = analytics.grouped_by("tony_risk_read")
        if not risk_table.empty and "tony_risk_read" in risk_table.columns:
            st.markdown("**By Risk Read**")
            display_cols = ["tony_risk_read"] + [c for c in _tony_learning_compact_cols if c in risk_table.columns]
            st.dataframe(risk_table[display_cols], hide_index=True)


def main() -> None:
    repo = repository()
    results = latest_results(repo)
    inject_tony_theme()
    st.title("Tony Stocks")
    tabs = st.tabs([
        "Home",
        "Tony Watchlist",
        "Results",
        "Settings / System Health",
    ])
    with tabs[0]:
        render_home(repo, results)
    with tabs[1]:
        render_tony_watchlist(repo, results)
    with tabs[2]:
        render_results(repo)
    with tabs[3]:
        render_system_health(repo, results)


if __name__ == "__main__":
    main()
