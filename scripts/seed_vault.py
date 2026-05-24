"""One-time backfill: write vault notes for all existing candidate snapshots.

Usage:
    python scripts/seed_vault.py [--days-back 60] [--config config/default_config.yaml]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import pandas as pd

from trading_bot.settings import load_scanner_settings
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.vault import (
    update_vault_index,
    upsert_ticker_page,
    write_bridge_export,
    write_daily_note,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill Obsidian vault from existing candidate snapshots.")
    parser.add_argument("--days-back", type=int, default=60, help="How many days of history to backfill (default: 60).")
    parser.add_argument("--config", default="config/default_config.yaml", help="Path to scanner YAML config.")
    args = parser.parse_args()

    settings = load_scanner_settings(args.config)
    vault_cfg = settings.vault or {}
    if not vault_cfg.get("enabled", False):
        print("Vault not enabled in config (vault.enabled = false). Exiting.")
        return

    vault_dir = vault_cfg.get("vault_dir", "vault")
    command_center_dir = vault_cfg.get("command_center_dir", "")
    bridge_enabled = vault_cfg.get("bridge_enabled", False)

    repo = ScannerRepository(settings.database_path)
    df = repo.list_snapshots_for_analytics(days=args.days_back)

    if df.empty:
        print("No snapshots found. Nothing to seed.")
        return

    df["_date"] = pd.to_datetime(df["snapshot_time"], utc=True).dt.date
    df["_date_str"] = df["_date"].astype(str)

    days_active_map: dict[str, int] = df.groupby("symbol")["_date"].nunique().to_dict()

    all_dates = sorted(df["_date_str"].unique())
    total_ticker_files = 0

    for date_str in all_dates:
        day_df = df[df["_date_str"] == date_str]
        latest_per_sym = day_df.sort_values("snapshot_time", ascending=False).drop_duplicates(subset=["symbol"])

        snapshots = []
        for _, row in latest_per_sym.iterrows():
            sym = str(row.get("symbol", ""))
            snapshots.append({
                "symbol": sym,
                "score": row.get("total_score"),
                "setup_category": row.get("setup_category", ""),
                "status": row.get("outcome_label", ""),
                "days_active": days_active_map.get(sym, 1),
                "latest_close": row.get("close"),
                "target_price": row.get("target"),
                "stop_price": row.get("stop"),
            })

        write_daily_note(date_str, {}, vault_dir, snapshots=snapshots)

        for snap in snapshots:
            upsert_ticker_page(date_str, snap, vault_dir)
            total_ticker_files += 1

        if bridge_enabled and command_center_dir:
            write_bridge_export(date_str, {}, command_center_dir, snapshots=snapshots)

        print(f"  {date_str}: {len(snapshots)} snapshots")

    latest_date = all_dates[-1]
    latest_day_df = df[df["_date_str"] == latest_date]
    latest_per_sym = latest_day_df.sort_values("snapshot_time", ascending=False).drop_duplicates(subset=["symbol"])
    current_snapshots = [
        {
            "symbol": str(row.get("symbol", "")),
            "score": row.get("total_score"),
            "setup_category": row.get("setup_category", ""),
            "status": row.get("outcome_label", ""),
            "days_active": days_active_map.get(str(row.get("symbol", "")), 1),
            "latest_close": row.get("close"),
            "target_price": row.get("target"),
            "stop_price": row.get("stop"),
        }
        for _, row in latest_per_sym.iterrows()
    ]
    update_vault_index(latest_date, current_snapshots, vault_dir)

    # Write bridge index linking all dated briefs
    if bridge_enabled and command_center_dir:
        bridge_index_path = Path(command_center_dir) / "bridge" / "tony-stocks" / "index.md"
        brief_links = " | ".join(f"[[bridge/tony-stocks/{d}]]" for d in all_dates)
        bridge_index_path.write_text(
            "# Tony Stocks Bridge — Index\n\n"
            f"*Last updated: {all_dates[-1]}*\n\n"
            "## All Daily Briefs\n\n"
            f"{brief_links}\n",
            encoding="utf-8",
        )
        print(f"  Bridge index written: {bridge_index_path}")

    print(f"\nSeed complete.")
    print(f"  Dates processed: {len(all_dates)}")
    print(f"  Ticker pages written: {total_ticker_files}")
    print(f"  Vault dir: {vault_dir}")
    if bridge_enabled:
        print(f"  Bridge dir: {command_center_dir}/bridge/tony-stocks/")


if __name__ == "__main__":
    main()
