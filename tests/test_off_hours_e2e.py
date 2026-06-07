"""End-to-end sandbox test for the off-hours research engine (Task 9).

Verifies:
  1. All four sinks are written into the sandbox dirs.
  2. The JSON artifact matches the MorningPrep contract shape.
  3. Re-running run_off_hours_prep is idempotent (no crash; overwrites cleanly).
  4. Zero real-workspace mutation: real vault/ and reports/ dirs are byte-for-byte
     unchanged before and after the test (fingerprinted via sha256).

The single most important assertion is (4): the engine must ONLY write into the
sandbox dirs supplied via config, never into the real repo vault/ or reports/.

Fingerprint approach mirrors test_learning_e2e.py.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

# ---------------------------------------------------------------------------
# Paths to the REAL workspace dirs that must never be mutated.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).parent.parent
_REAL_VAULT = _REPO_ROOT / "vault"
_REAL_REPORTS = _REPO_ROOT / "reports"


# ---------------------------------------------------------------------------
# Fingerprint helper (sha256 over all file paths + contents, sorted)
# ---------------------------------------------------------------------------

def _fingerprint(directory: Path) -> str:
    """Return a sha256 digest of all file paths and contents under directory.

    Paths are recorded relative to the directory root and sorted to give a
    deterministic ordering. If the directory does not exist the digest is over
    the empty string — still a stable value.
    """
    h = hashlib.sha256()
    if not directory.exists():
        return h.hexdigest()
    for p in sorted(directory.rglob("*")):
        if p.is_file():
            h.update(p.relative_to(directory).as_posix().encode())
            h.update(p.read_bytes())
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Sandbox config builder (mirrors test_off_hours_cli.py)
# ---------------------------------------------------------------------------

def _make_sandbox_config(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Create a minimal sandbox YAML config that redirects all dirs to tmp_path.

    Returns (cfg_path, vault_dir, reports_dir, cc_dir).
    """
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
    return cfg, vault, reports, cc


def _frozen_post_close_et() -> datetime:
    """A fixed weekday post-close ET datetime — deterministic phase forcing."""
    # 2026-06-05 is a Friday; 16:45 ET = post_close phase.
    return datetime(2026, 6, 5, 16, 45, 0, tzinfo=ZoneInfo("America/New_York"))


def _make_args(cfg: Path, reports: Path, vault: Path, cc: Path,
               phase: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        config=str(cfg),
        phase=phase,
        reports_dir=str(reports),
        vault_dir=str(vault),
        command_center_dir=str(cc),
    )


# ---------------------------------------------------------------------------
# Main e2e test
# ---------------------------------------------------------------------------

class TestOffHoursE2ESandbox:
    """Full integration test with sandbox isolation + real-workspace fingerprint."""

    def test_all_sinks_written_and_isolation(self, tmp_path):
        """Step 1: all four sinks exist and real workspace is unchanged."""
        cfg, vault, reports, cc = _make_sandbox_config(tmp_path)
        args = _make_args(cfg, reports, vault, cc)

        et_now = _frozen_post_close_et()
        date_str = et_now.strftime("%Y-%m-%d")

        # Fingerprint real workspace BEFORE
        fp_vault_before = _fingerprint(_REAL_VAULT)
        fp_reports_before = _fingerprint(_REAL_REPORTS)

        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            result = cli.run_off_hours_prep(args)

        # Fingerprint real workspace AFTER
        fp_vault_after = _fingerprint(_REAL_VAULT)
        fp_reports_after = _fingerprint(_REAL_REPORTS)

        # --- Zero real-workspace mutation (most important assertion) ---
        assert fp_vault_before == fp_vault_after, (
            "ISOLATION FAILURE: real vault/ was mutated during run_off_hours_prep. "
            f"Before={fp_vault_before[:16]}… After={fp_vault_after[:16]}…"
        )
        assert fp_reports_before == fp_reports_after, (
            "ISOLATION FAILURE: real reports/ was mutated during run_off_hours_prep. "
            f"Before={fp_reports_before[:16]}… After={fp_reports_after[:16]}…"
        )

        # --- All four artifacts exist in the sandbox ---
        json_path = reports / "morning_prep" / f"{date_str}.json"
        md_report_path = reports / "morning_prep" / f"{date_str}.md"
        vault_note_path = vault / "morning_prep" / f"{date_str}.md"
        bridge_path = cc / "bridge" / "tony-stocks" / "morning-prep" / f"{date_str}.md"

        assert json_path.exists(), (
            f"Missing JSON report at {json_path}; "
            f"sinks_written={result.get('sinks_written')}, errors={result.get('errors')}"
        )
        assert md_report_path.exists(), (
            f"Missing MD report sidecar at {md_report_path}; "
            f"sinks_written={result.get('sinks_written')}"
        )
        assert vault_note_path.exists(), (
            f"Missing vault note at {vault_note_path}; "
            f"sinks_written={result.get('sinks_written')}"
        )
        assert bridge_path.exists(), (
            f"Missing CC bridge at {bridge_path}; "
            f"sinks_written={result.get('sinks_written')}"
        )

    def test_json_matches_morningprep_contract(self, tmp_path):
        """Step 1b: JSON parses and matches the MorningPrep contract shape."""
        cfg, vault, reports, cc = _make_sandbox_config(tmp_path)
        args = _make_args(cfg, reports, vault, cc)

        et_now = _frozen_post_close_et()
        date_str = et_now.strftime("%Y-%m-%d")

        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            cli.run_off_hours_prep(args)

        json_path = reports / "morning_prep" / f"{date_str}.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))

        # Required top-level contract keys
        for key in ("generated_at", "et_date", "phase", "shortlist",
                    "what_changed_overnight", "plan_for_open"):
            assert key in data, f"MorningPrep contract key '{key}' missing from JSON"

        # Type checks
        assert isinstance(data["shortlist"], list)
        assert isinstance(data["what_changed_overnight"], str)
        assert isinstance(data["plan_for_open"], str)
        assert data["et_date"] == date_str

    def test_idempotent_rerun(self, tmp_path):
        """Step 1c: re-running run_off_hours_prep does not crash and overwrites cleanly."""
        cfg, vault, reports, cc = _make_sandbox_config(tmp_path)
        args = _make_args(cfg, reports, vault, cc)

        et_now = _frozen_post_close_et()
        date_str = et_now.strftime("%Y-%m-%d")

        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli

            # First run
            result1 = cli.run_off_hours_prep(args)
            assert isinstance(result1, dict), "First run must return a dict"

            # Second run — idempotent: no exception, artifacts still present
            result2 = cli.run_off_hours_prep(args)
            assert isinstance(result2, dict), "Second run must return a dict"

        json_path = reports / "morning_prep" / f"{date_str}.json"
        vault_note_path = vault / "morning_prep" / f"{date_str}.md"
        bridge_path = cc / "bridge" / "tony-stocks" / "morning-prep" / f"{date_str}.md"

        assert json_path.exists(), "JSON report must exist after idempotent re-run"
        assert vault_note_path.exists(), "Vault note must exist after idempotent re-run"
        assert bridge_path.exists(), "CC bridge must exist after idempotent re-run"

    def test_et_date_matches_frozen_clock(self, tmp_path):
        """The et_date in all artifacts matches the frozen ET date."""
        cfg, vault, reports, cc = _make_sandbox_config(tmp_path)
        args = _make_args(cfg, reports, vault, cc)

        et_now = _frozen_post_close_et()
        expected_date = et_now.strftime("%Y-%m-%d")  # "2026-06-05"

        with patch("trading_bot.cli._now_et", return_value=et_now):
            import trading_bot.cli as cli
            result = cli.run_off_hours_prep(args)

        assert result["et_date"] == expected_date

        json_path = reports / "morning_prep" / f"{expected_date}.json"
        data = json.loads(json_path.read_text(encoding="utf-8"))
        assert data["et_date"] == expected_date


# ---------------------------------------------------------------------------
# Convenience: run all assertions from a single test entry point
# (mirrors the task spec: "Step 1 — failing test")
# ---------------------------------------------------------------------------

def test_off_hours_e2e_full(tmp_path):
    """Single comprehensive e2e assertion covering all four Step 1 checks.

    This is the primary entry point referenced in the task spec.

    Checks:
      - all four sinks exist in sandbox dirs
      - JSON matches MorningPrep contract shape
      - re-run is idempotent
      - zero real-workspace mutation (sha256 fingerprint on real vault/ + reports/)
    """
    cfg, vault, reports, cc = _make_sandbox_config(tmp_path)
    args = _make_args(cfg, reports, vault, cc)

    et_now = _frozen_post_close_et()
    date_str = et_now.strftime("%Y-%m-%d")

    # Capture real-workspace fingerprint BEFORE
    fp_vault_before = _fingerprint(_REAL_VAULT)
    fp_reports_before = _fingerprint(_REAL_REPORTS)

    with patch("trading_bot.cli._now_et", return_value=et_now):
        import trading_bot.cli as cli

        # --- First run ---
        result = cli.run_off_hours_prep(args)

        # Must return a dict
        assert isinstance(result, dict), "run_off_hours_prep must return a dict"
        assert result["et_date"] == date_str
        assert isinstance(result["sinks_written"], list)
        assert isinstance(result["errors"], list)

        # --- All four artifacts ---
        json_path = reports / "morning_prep" / f"{date_str}.json"
        md_report_path = reports / "morning_prep" / f"{date_str}.md"
        vault_note_path = vault / "morning_prep" / f"{date_str}.md"
        bridge_path = cc / "bridge" / "tony-stocks" / "morning-prep" / f"{date_str}.md"

        assert json_path.exists(), (
            f"Missing {json_path}; sinks={result['sinks_written']}, errors={result['errors']}"
        )
        assert md_report_path.exists(), f"Missing MD sidecar {md_report_path}"
        assert vault_note_path.exists(), f"Missing vault note {vault_note_path}"
        assert bridge_path.exists(), f"Missing CC bridge {bridge_path}"

        # --- JSON matches MorningPrep contract shape ---
        data = json.loads(json_path.read_text(encoding="utf-8"))
        for key in ("generated_at", "et_date", "phase", "shortlist",
                    "what_changed_overnight", "plan_for_open"):
            assert key in data, f"Contract key '{key}' missing from morning prep JSON"
        assert isinstance(data["shortlist"], list)
        assert isinstance(data["what_changed_overnight"], str)
        assert isinstance(data["plan_for_open"], str)
        assert data["et_date"] == date_str

        # --- Idempotent re-run ---
        result2 = cli.run_off_hours_prep(args)
        assert isinstance(result2, dict), "Second run must not crash"
        assert json_path.exists(), "JSON must still exist after idempotent re-run"
        assert vault_note_path.exists(), "Vault note must still exist after idempotent re-run"
        assert bridge_path.exists(), "CC bridge must still exist after idempotent re-run"

    # Fingerprint real workspace AFTER (outside patch context — no monkey-patch in flight)
    fp_vault_after = _fingerprint(_REAL_VAULT)
    fp_reports_after = _fingerprint(_REAL_REPORTS)

    # --- Zero real-workspace mutation (most critical assertion) ---
    assert fp_vault_before == fp_vault_after, (
        "ISOLATION FAILURE: real vault/ was mutated by run_off_hours_prep. "
        f"Before sha256={fp_vault_before[:16]}… After={fp_vault_after[:16]}…"
    )
    assert fp_reports_before == fp_reports_after, (
        "ISOLATION FAILURE: real reports/ was mutated by run_off_hours_prep. "
        f"Before sha256={fp_reports_before[:16]}… After={fp_reports_after[:16]}…"
    )
