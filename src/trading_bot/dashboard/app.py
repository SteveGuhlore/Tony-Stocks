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
from trading_bot.data.universe import load_universe_metadata
from trading_bot.analytics import OutcomeAnalytics
from trading_bot.indicators import simple_moving_average
from trading_bot.settings import load_scanner_settings, resolve_effective_provider
from trading_bot.storage.repositories import ScannerRepository


st.set_page_config(page_title="Trading Bot Scanner", layout="wide")


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

            rotation_cfg = settings.watch_universe_rotation or {}
            if rotation_cfg.get("enabled", False):
                rot_cols = st.columns(4)
                rot_cols[0].metric("Rotation", "enabled")
                rot_cols[1].metric("Max/Cycle", str(rotation_cfg.get("max_symbols_per_cycle", 175)))
                rot_cols[2].metric("Core Max", str(rotation_cfg.get("core_max_symbols", 50)))
                rot_cols[3].metric("Bucket Size", str(rotation_cfg.get("rotating_bucket_size", 125)))

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

    cols = st.columns(6)
    cols[0].metric("Snapshots Today", today_count)
    cols[1].metric("Open/Watch", open_count)
    cols[2].metric("Triggered", triggered_count)
    cols[3].metric("Target Hit", _count_outcome(outcome_counts, ["target_hit", "target_before_stop"]))
    cols[4].metric("Stop Hit", _count_outcome(outcome_counts, ["stop_hit", "stop_before_target"]))
    cols[5].metric("Insufficient Data", _count_outcome(outcome_counts, ["insufficient_future_data"]))

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
        st.write("Tags", row["tags_list"])
        st.write(
            {
                "snapshot_time": row["snapshot_time"],
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
            }
        )
        st.write("Reasons", json.loads(row["reasons_json"] or "[]"))
        st.write("Warnings", json.loads(row["warnings_json"] or "[]"))
        st.write("Candidate Summary", row["candidate_summary"])


def render_tony_stocks(repo: ScannerRepository) -> None:
    st.subheader("Tony Stocks")
    settings = load_scanner_settings()
    tony_config = settings.tony_stocks or {}
    st.info("Tony Stocks is currently watcher/analyst only. No paper trades, broker orders, or live trades are placed.")
    events = repo.list_tony_events(limit=500)
    status_cols = st.columns(5)
    status_cols[0].metric("Tony Mode", str(tony_config.get("mode", "watcher")))
    latest_scan = _latest_event_time(events, "scan_completed")
    latest_watch = _latest_event_time(events, "watch_cycle_completed")
    status_cols[1].metric("Latest Scan Event", latest_scan or "None")
    status_cols[2].metric("Latest Watch Event", latest_watch or "None")
    status_cols[3].metric("Warnings", repo.count_tony_events(severity="warning"))
    status_cols[4].metric("High-Score Events", repo.count_tony_events(event_type="high_score_candidate"))
    if events.empty:
        st.info("No Tony Stocks events yet. Run a scan, snapshot update, or watch cycle.")
        return

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


def main() -> None:
    repo = repository()
    results = latest_results(repo)
    st.title("Trading Bot Scanner")
    tabs = st.tabs(["Overview", "Ranked Stocks", "Stock Detail", "Candidate Snapshots", "Outcome Analytics", "Tony Stocks", "Manual Picks", "Paper Journal", "Performance"])
    with tabs[0]:
        render_overview(repo, results)
    with tabs[1]:
        render_ranked(results)
    with tabs[2]:
        render_detail(results)
    with tabs[3]:
        render_candidate_snapshots(repo)
    with tabs[4]:
        render_outcome_analytics(repo)
    with tabs[5]:
        render_tony_stocks(repo)
    with tabs[6]:
        render_manual_picks(repo, results)
    with tabs[7]:
        render_paper_journal(repo)
    with tabs[8]:
        render_performance(repo)


if __name__ == "__main__":
    main()
