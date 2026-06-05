"""Activation gate tests for divergence calibration (Key 2 — the sole apply path).

Spec: docs/superpowers/specs/2026-06-05-divergence-calibration-design.md (A1-A6).
Seeds synthetic scoring_config.yaml + approval_package.json + suggestion_decisions.json
under tmp_path; never touches the real repo config.
"""
from __future__ import annotations

import argparse
import json

import yaml

from trading_bot.cli import _suggestion_key, run_activate_strategy_version

_BASE = {
    "trend_weight": 0.22,
    "momentum_weight": 0.28,
    "volume_weight": 0.18,
    "risk_weight": 0.14,
    "setup_quality_weight": 0.18,
}
_NEW = {  # sums to 1.0, like real apply_nudge output
    "trend_weight": 0.2243,
    "momentum_weight": 0.25,
    "volume_weight": 0.1835,
    "risk_weight": 0.1422,
    "setup_quality_weight": 0.20,
}
_SUGG = "Calibration: lower the momentum weight. Tony's overrides on setup_category='Momentum Continuation'..."


def _ns(**kw) -> argparse.Namespace:
    base = dict(output_dir=None, config_dir=None, date="2026-06-05", key=None, revert=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _seed(tmp_path, *, approved: bool):
    reports = tmp_path / "reports"
    (reports / "2026-06-05").mkdir(parents=True)
    cfg = tmp_path / "config"
    cfg.mkdir(parents=True)
    scoring = cfg / "scoring_config.yaml"
    scoring.write_text(yaml.safe_dump({"weights": dict(_BASE)}, sort_keys=False), encoding="utf-8")

    pkg = {
        "suggestions": [
            {
                "suggestion": _SUGG,
                "strategy_version": "v1",
                "confidence": "medium",
                "status": "approved" if approved else "needs_review",
                "kind": "weight_calibration",
                "new_weights": dict(_NEW),
                "target_component": "momentum",
                "cohort": "Momentum Continuation",
                "rationale": _SUGG,
            }
        ]
    }
    (reports / "2026-06-05" / "approval_package.json").write_text(json.dumps(pkg), encoding="utf-8")

    decisions = [
        {
            "suggestion_key": _suggestion_key(_SUGG, "v1"),
            "suggestion": _SUGG,
            "strategy_version": "v1",
            "status": "approved" if approved else "needs_review",
            "date": "2026-06-05",
        }
    ]
    (reports / "suggestion_decisions.json").write_text(json.dumps(decisions), encoding="utf-8")
    return scoring, str(reports), str(cfg)


def _weights(scoring) -> dict:
    return yaml.safe_load(scoring.read_text(encoding="utf-8"))["weights"]


def test_A1_refuses_without_approval(tmp_path):
    scoring, reports, cfg = _seed(tmp_path, approved=False)
    res = run_activate_strategy_version(_ns(output_dir=reports, config_dir=cfg))
    assert res.get("error") == "no_approved_calibration"
    assert _weights(scoring)["momentum_weight"] == 0.28  # untouched


def test_A2_refuses_when_payload_missing(tmp_path):
    scoring, reports, cfg = _seed(tmp_path, approved=True)
    # Strip new_weights from the package -> approved decision can't be matched to a payload.
    pkg_path = tmp_path / "reports" / "2026-06-05" / "approval_package.json"
    pkg = json.loads(pkg_path.read_text())
    pkg["suggestions"][0].pop("new_weights")
    pkg_path.write_text(json.dumps(pkg), encoding="utf-8")
    res = run_activate_strategy_version(_ns(output_dir=reports, config_dir=cfg))
    assert res.get("error") == "no_approved_calibration"
    assert _weights(scoring)["momentum_weight"] == 0.28


def test_A3_A4_applies_and_records(tmp_path):
    scoring, reports, cfg = _seed(tmp_path, approved=True)
    res = run_activate_strategy_version(_ns(output_dir=reports, config_dir=cfg))
    assert res["version"] == "v2" and res["predecessor"] == "v1"
    w = _weights(scoring)
    assert abs(w["momentum_weight"] - 0.25) < 1e-9
    assert abs(sum(w.values()) - 1.0) < 1e-9
    ledger = json.loads((tmp_path / "reports" / "strategy_versions.json").read_text())
    assert ledger[-1]["version"] == "v2" and ledger[-1]["predecessor"] == "v1"
    assert ledger[-1]["previous_weights"]["momentum_weight"] == 0.28
    assert (tmp_path / "config" / "strategy_versions" / "v2.yaml").exists()


def test_A5_revert_restores_predecessor(tmp_path):
    scoring, reports, cfg = _seed(tmp_path, approved=True)
    run_activate_strategy_version(_ns(output_dir=reports, config_dir=cfg))
    assert abs(_weights(scoring)["momentum_weight"] - 0.25) < 1e-9
    run_activate_strategy_version(_ns(output_dir=reports, config_dir=cfg, revert=True))
    assert abs(_weights(scoring)["momentum_weight"] - 0.28) < 1e-9  # back to v1 baseline


def test_A6_idempotent_reactivation(tmp_path):
    scoring, reports, cfg = _seed(tmp_path, approved=True)
    run_activate_strategy_version(_ns(output_dir=reports, config_dir=cfg))
    res2 = run_activate_strategy_version(_ns(output_dir=reports, config_dir=cfg))
    assert res2.get("noop") is True
    ledger = json.loads((tmp_path / "reports" / "strategy_versions.json").read_text())
    assert len([e for e in ledger if e["version"] == "v2"]) == 1  # no double-append
