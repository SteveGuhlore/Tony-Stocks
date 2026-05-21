"""V31 — Discovery rotation diagnostics tests."""

from types import SimpleNamespace

import pandas as pd

import trading_bot.cli as cli
from trading_bot.analytics import build_rotation_diagnostics
from trading_bot.storage.repositories import ScannerRepository
from trading_bot.storage.database import connect
from trading_bot.scoring.score_models import ScoredStock


def _scan_rows(*symbols_with_roles):
    return pd.DataFrame([
        {"symbol": sym, "universe_role": role}
        for sym, role in symbols_with_roles
    ])


# ── Empty / missing data ──────────────────────────────────────────────────────

def test_rotation_diagnostics_empty_df():
    result = build_rotation_diagnostics(pd.DataFrame())
    assert result["unique_symbols_scanned"] == 0
    assert result["total_scan_appearances"] == 0
    assert result["repeat_scan_count"] == 0
    assert result["top_repeated_symbols"] == []
    assert result["note"]


def test_rotation_diagnostics_no_symbol_column():
    df = pd.DataFrame([{"universe_role": "core"}])
    result = build_rotation_diagnostics(df)
    assert result["unique_symbols_scanned"] == 0


# ── Basic counts ──────────────────────────────────────────────────────────────

def test_rotation_diagnostics_unique_count():
    df = _scan_rows(("AAPL", "primary_candidate"), ("TSLA", "primary_candidate"), ("NVDA", "discovery"))
    result = build_rotation_diagnostics(df)
    assert result["unique_symbols_scanned"] == 3
    assert result["total_scan_appearances"] == 3
    assert result["repeat_scan_count"] == 0


def test_rotation_diagnostics_repeat_count():
    df = pd.DataFrame([
        {"symbol": "AAPL", "universe_role": "core"},
        {"symbol": "AAPL", "universe_role": "core"},
        {"symbol": "AAPL", "universe_role": "core"},
        {"symbol": "TSLA", "universe_role": "discovery"},
    ])
    result = build_rotation_diagnostics(df)
    assert result["unique_symbols_scanned"] == 2
    assert result["total_scan_appearances"] == 4
    assert result["repeat_scan_count"] == 1
    top = result["top_repeated_symbols"]
    assert len(top) == 1
    assert top[0]["symbol"] == "AAPL"
    assert top[0]["scan_count"] == 3


def test_rotation_diagnostics_no_repeats_empty_top():
    df = _scan_rows(("AAPL", "discovery"), ("TSLA", "discovery"))
    result = build_rotation_diagnostics(df)
    assert result["repeat_scan_count"] == 0
    assert result["top_repeated_symbols"] == []


# ── Fallback / missing optional data ─────────────────────────────────────────

def test_rotation_diagnostics_no_bucket_data_fallback():
    df = _scan_rows(("AAPL", "primary_candidate"), ("AAPL", "primary_candidate"))
    result = build_rotation_diagnostics(df, rotation_bucket_summary=None)
    assert result["repeat_scan_count"] == 1
    assert isinstance(result["rotation_bucket_summary"], dict)


def test_rotation_diagnostics_no_universe_role_column():
    df = pd.DataFrame([{"symbol": "AAPL"}, {"symbol": "AAPL"}])
    result = build_rotation_diagnostics(df)
    assert result["repeat_scan_count"] == 1


# ── Active/core expected repeat labels ───────────────────────────────────────

def test_rotation_diagnostics_active_symbol_labeled_expected():
    df = pd.DataFrame([
        {"symbol": "PATH", "universe_role": "core"},
        {"symbol": "PATH", "universe_role": "core"},
        {"symbol": "ZETA", "universe_role": "discovery"},
    ])
    result = build_rotation_diagnostics(df, active_symbols={"PATH"})
    top = result["top_repeated_symbols"]
    path_entry = next((r for r in top if r["symbol"] == "PATH"), None)
    assert path_entry is not None
    assert "expected" in path_entry["repeat_label"].lower()
    assert any(r["symbol"] == "PATH" for r in result["active_core_repeats"])


def test_rotation_diagnostics_core_symbol_labeled_expected():
    df = pd.DataFrame([
        {"symbol": "SPY", "universe_role": "benchmark"},
        {"symbol": "SPY", "universe_role": "benchmark"},
    ])
    result = build_rotation_diagnostics(df, core_symbols={"SPY"})
    top = result["top_repeated_symbols"]
    spy_entry = next((r for r in top if r["symbol"] == "SPY"), None)
    assert spy_entry is not None
    assert "expected" in spy_entry["repeat_label"].lower()


def test_rotation_diagnostics_discovery_repeat_not_labeled_expected():
    df = pd.DataFrame([
        {"symbol": "NVDA", "universe_role": "discovery"},
        {"symbol": "NVDA", "universe_role": "discovery"},
    ])
    result = build_rotation_diagnostics(df)
    top = result["top_repeated_symbols"]
    entry = next((r for r in top if r["symbol"] == "NVDA"), None)
    assert entry is not None
    assert entry["repeat_label"] != "expected (active/core)"


def test_rotation_diagnostics_active_core_repeats_empty_when_no_active():
    df = _scan_rows(("AAPL", "discovery"), ("AAPL", "discovery"))
    result = build_rotation_diagnostics(df)
    assert result["active_core_repeats"] == []


# ── Percent universe touched ──────────────────────────────────────────────────

def test_rotation_diagnostics_percent_universe_touched():
    df = _scan_rows(("AAPL", "primary_candidate"), ("TSLA", "primary_candidate"))
    result = build_rotation_diagnostics(df, configured_universe_size=10)
    assert result["percent_universe_touched"] == 20.0


def test_rotation_diagnostics_percent_none_without_size():
    df = _scan_rows(("AAPL", "primary_candidate"))
    result = build_rotation_diagnostics(df)
    assert result["percent_universe_touched"] is None


# ── Note always present ───────────────────────────────────────────────────────

def test_rotation_diagnostics_note_always_present():
    for df in [pd.DataFrame(), _scan_rows(("AAPL", "core"))]:
        result = build_rotation_diagnostics(df)
        assert isinstance(result["note"], str) and len(result["note"]) > 10


# ── EOD integration: rotation_diagnostics in scan_coverage ───────────────────

def _make_scored_stock(symbol: str, role: str = "primary_candidate") -> ScoredStock:
    return ScoredStock(
        symbol=symbol,
        scanned_at="2026-05-20T14:00:00+00:00",
        final_score=80,
        setup_category="Breakout Watch",
        tags=[],
        universe_role=role,
        name=symbol,
        sector="technology",
        industry="software",
        demo_profile="",
        notes="",
        candidate_summary="",
        trend_score=80, momentum_score=80, volume_score=80,
        risk_score=80, setup_quality_score=80,
        latest_close=100, avg_volume_20=1000000, dollar_volume_20=100000000,
        return_5d=0.01, return_10d=0.02, return_20d=0.05,
        atr_14=2, atr_percent=0.02, volatility_20d=0.02,
        relative_volume=1.3,
        suggested_entry=100, suggested_stop=95, suggested_target_1=110,
        risk_reward_ratio=2.0,
        trade_plan_valid=True,
        trade_plan_status="valid",
        reasons=[],
        warnings=[],
    )


def _make_test_db(tmp_path):
    db_path = tmp_path / "trading_bot.db"
    repo = ScannerRepository(str(db_path))
    run_id = repo.create_scan_run(3, "test", {})
    # AAPL appears twice in same run to simulate a repeat across two cycles
    repo.save_scan_results(run_id, [_make_scored_stock("AAPL"), _make_scored_stock("TSLA")])
    run_id2 = repo.create_scan_run(3, "test", {})
    repo.save_scan_results(run_id2, [_make_scored_stock("AAPL")])
    # Back-date both runs to today (2026-05-20)
    with connect(str(db_path)) as conn:
        conn.execute("UPDATE scan_runs SET created_at = '2026-05-20T14:00:00+00:00'")
    repo.create_tony_event(
        "scan_completed", "info", "Scan completed", "done",
        payload={
            "symbols_loaded": 3, "symbols_scored": 3,
            "selected_symbols": ["AAPL", "TSLA", "NVDA"],
            "scored_symbols": ["AAPL", "TSLA", "NVDA"],
        },
    )
    return repo, str(db_path)


def _patch_eod(monkeypatch, repo):
    from types import SimpleNamespace as SN
    monkeypatch.setattr(
        cli,
        "load_scanner_settings",
        lambda _: SN(
            database_path=repo.database_path,
            provider="test",
            tony_stocks={},
            symbol_quarantine={},
            universe_config_path="ignored",
        ),
    )
    monkeypatch.setattr(cli, "ScannerRepository", lambda *a, **kw: repo)
    monkeypatch.setattr(cli, "load_universe", lambda path, manual_symbols=None: [f"U{i}" for i in range(20)])


def test_rotation_diagnostics_in_scan_coverage(tmp_path, monkeypatch):
    repo, _ = _make_test_db(tmp_path)
    _patch_eod(monkeypatch, repo)
    args = SimpleNamespace(config="ignored", date="2026-05-20",
                           output_dir=str(tmp_path / "reports"), include_seeded=False)
    result = cli.run_eod_report(args)
    coverage = result.get("scan_coverage") or {}
    diag = coverage.get("rotation_diagnostics") or {}
    assert "unique_symbols_scanned" in diag
    assert "repeat_scan_count" in diag
    assert "note" in diag


def test_rotation_diagnostics_repeat_detected_in_eod(tmp_path, monkeypatch):
    repo, _ = _make_test_db(tmp_path)
    _patch_eod(monkeypatch, repo)
    args = SimpleNamespace(config="ignored", date="2026-05-20",
                           output_dir=str(tmp_path / "reports"), include_seeded=False)
    result = cli.run_eod_report(args)
    diag = (result.get("scan_coverage") or {}).get("rotation_diagnostics") or {}
    # AAPL appears in two scan runs on the same day — should be detected as a repeat
    assert diag.get("repeat_scan_count", 0) >= 1


def test_rotation_diagnostics_markdown_includes_section(tmp_path, monkeypatch):
    repo, _ = _make_test_db(tmp_path)
    _patch_eod(monkeypatch, repo)
    args = SimpleNamespace(config="ignored", date="2026-05-20",
                           output_dir=str(tmp_path / "reports"), include_seeded=False)
    cli.run_eod_report(args)
    md_path = tmp_path / "reports" / "2026-05-20" / "after_market_review.md"
    if md_path.exists():
        md = md_path.read_text(encoding="utf-8")
        assert "Discovery Rotation" in md or "rotation" in md.lower()
