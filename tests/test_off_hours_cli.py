"""Tests for off-hours CLI orchestration (Task 8).

Tests:
  (a) run_off_hours_prep on a sandbox config produces reports/morning_prep/<date>.json
      and returns a summary dict.
  (b) A sink that raises does NOT cause run_off_hours_prep to raise — fail-quiet
      and still returns a summary dict.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_sandbox_config(tmp_path: Path) -> Path:
    """Write a minimal sandbox YAML config that redirects all dirs to tmp_path."""
    db = tmp_path / "scan.db"
    vault = tmp_path / "vault"
    reports = tmp_path / "reports"
    cc = tmp_path / "cc"
    for d in (vault, reports, cc):
        d.mkdir(parents=True, exist_ok=True)

    cfg = tmp_path / "sandbox.yaml"
    cfg.write_text(
        f"database_path: {db.as_posix()}\n"
        f"vault:\n"
        f"  enabled: true\n"
        f"  vault_dir: {vault.as_posix()}\n"
        f"  command_center_dir: {cc.as_posix()}\n"
        f"  bridge_enabled: true\n"
        f"off_hours:\n"
        f"  enabled: true\n"
        f"  cadence_minutes: 30\n"
        f"  earnings_blackout_days: 5\n"
        f"  shortlist_size: 5\n"
        f"  full_universe_scan: false\n"
        f'  premarket_provider: "null"\n'
        f"  enrich_budget: 0\n",
        encoding="utf-8",
    )
    return cfg


def _frozen_et() -> datetime:
    """Return a fixed ET datetime in PRE_OPEN phase for deterministic tests."""
    return datetime(2026, 6, 6, 7, 0, 0, tzinfo=ZoneInfo("America/New_York"))


# ---------------------------------------------------------------------------
# Test (a): happy-path — produces report file + returns summary dict
# ---------------------------------------------------------------------------

class TestRunOffHoursPrepHappyPath:
    def test_returns_summary_dict(self, tmp_path):
        """run_off_hours_prep returns a dict with required summary keys."""
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            result = cli.run_off_hours_prep(args)

        assert isinstance(result, dict), "run_off_hours_prep must return a dict"
        assert "phase" in result
        assert "et_date" in result
        assert "sinks_written" in result
        assert "errors" in result

    def test_produces_json_report(self, tmp_path):
        """run_off_hours_prep writes reports/morning_prep/<date>.json."""
        cfg = _make_sandbox_config(tmp_path)
        reports_dir = tmp_path / "reports"
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(reports_dir),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            result = cli.run_off_hours_prep(args)

        date_str = et_now.strftime("%Y-%m-%d")
        json_path = reports_dir / "morning_prep" / f"{date_str}.json"
        assert json_path.exists(), f"Expected {json_path} to exist; sinks_written={result.get('sinks_written')}"

        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert "et_date" in data
        assert data["et_date"] == date_str

    def test_et_date_matches_frozen_clock(self, tmp_path):
        """The et_date in the summary matches the frozen ET datetime."""
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            result = cli.run_off_hours_prep(args)

        assert result["et_date"] == "2026-06-06"

    def test_phase_override(self, tmp_path):
        """An explicit --phase arg overrides the clock-derived phase."""
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase="overnight",
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            result = cli.run_off_hours_prep(args)

        assert result["phase"] == "overnight"

    def test_sinks_written_is_list(self, tmp_path):
        """sinks_written must be a list of strings."""
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            result = cli.run_off_hours_prep(args)

        assert isinstance(result["sinks_written"], list)

    def test_shortlist_size_respected(self, tmp_path):
        """The summary includes shortlist_size from config."""
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            result = cli.run_off_hours_prep(args)

        assert "shortlist_size" in result


# ---------------------------------------------------------------------------
# Test (b): fail-quiet — a sink that raises does not bubble up
# ---------------------------------------------------------------------------

class TestRunOffHoursPrepFailQuiet:
    def test_sink_exception_does_not_propagate(self, tmp_path):
        """A sink that raises must NOT cause run_off_hours_prep to raise.

        Monkeypatches write_morning_prep_report to raise RuntimeError; the
        function must still return a summary dict (fail-quiet, mirror run_learn).
        """
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        boom = RuntimeError("synthetic sink failure")

        with patch("trading_bot.cli._now_et", return_value=et_now):
            with patch(
                "trading_bot.vault.morning_prep_writer.write_morning_prep_report",
                side_effect=boom,
            ):
                import trading_bot.cli as cli
                # Must NOT raise:
                result = cli.run_off_hours_prep(args)

        assert isinstance(result, dict), "Must still return summary dict even when a sink raises"

    def test_sink_exception_recorded_in_errors(self, tmp_path):
        """A failing sink error is recorded in the errors list of the summary."""
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        boom = RuntimeError("synthetic sink failure")

        with patch("trading_bot.cli._now_et", return_value=et_now):
            with patch(
                "trading_bot.vault.morning_prep_writer.write_morning_prep_report",
                side_effect=boom,
            ):
                import trading_bot.cli as cli
                result = cli.run_off_hours_prep(args)

        # errors list must exist and contain mention of the failure
        errors = result.get("errors", [])
        assert isinstance(errors, list)
        assert len(errors) > 0, "Expected at least one error entry when a sink fails"

    def test_note_sink_exception_does_not_propagate(self, tmp_path):
        """A write_morning_prep_note failure is also fail-quiet."""
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        boom = RuntimeError("vault note failure")

        with patch("trading_bot.cli._now_et", return_value=et_now):
            with patch(
                "trading_bot.vault.morning_prep_writer.write_morning_prep_note",
                side_effect=boom,
            ):
                import trading_bot.cli as cli
                result = cli.run_off_hours_prep(args)

        assert isinstance(result, dict)

    def test_all_sinks_fail_still_returns_summary(self, tmp_path):
        """Even when all four sinks fail, a summary dict is returned."""
        cfg = _make_sandbox_config(tmp_path)
        args = SimpleNamespace(
            config=str(cfg),
            phase=None,
            reports_dir=str(tmp_path / "reports"),
            vault_dir=str(tmp_path / "vault"),
            command_center_dir=str(tmp_path / "cc"),
        )

        et_now = _frozen_et()
        boom = RuntimeError("all sinks broken")

        with patch("trading_bot.cli._now_et", return_value=et_now):
            with patch("trading_bot.vault.morning_prep_writer.write_morning_prep_report", side_effect=boom):
                with patch("trading_bot.vault.morning_prep_writer.write_morning_prep_note", side_effect=boom):
                    with patch("trading_bot.vault.morning_prep_writer.write_morning_prep_bridge", side_effect=boom):
                        import trading_bot.cli as cli
                        result = cli.run_off_hours_prep(args)

        assert isinstance(result, dict)
        assert "errors" in result
        # Should have errors from each failed sink
        assert len(result["errors"]) >= 3
