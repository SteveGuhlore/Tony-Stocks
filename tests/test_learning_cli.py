import json
from pathlib import Path

import trading_bot.cli as cli
from trading_bot.cli import run_learn, build_parser
from trading_bot.analytics.nightly_learning import build_nightly_facts


def _seed(reports: Path):
    reports.mkdir(parents=True, exist_ok=True)
    (reports / "tony_stocks_outcomes.json").write_text(json.dumps([
        {"symbol": "MARA", "pick_date": "2026-06-01", "result": "target_hit", "return_pct": 12,
         "setup_category": "Momentum / Buy", "total_score": 80, "days_held": 4,
         "entry": 13.7, "stop": 12.2, "exit": 16.3},
        {"symbol": "CVS", "pick_date": "2026-06-01", "result": "stop_hit", "return_pct": -4,
         "setup_category": "Pullback / Buy", "total_score": 55, "days_held": 2,
         "entry": 60, "stop": 58, "exit": 58},
    ]), encoding="utf-8")


def test_run_learn_produces_all_sinks(tmp_path):
    reports = tmp_path / "reports"
    _seed(reports)
    vault = tmp_path / "vault"
    cc = tmp_path / "CC"
    args = build_parser().parse_args([
        "learn", "--config", "config/default_config.yaml", "--date", "2026-06-04",
        "--no-llm", "--min-sample", "1", "--reports-dir", str(reports), "--vault-dir", str(vault),
        "--command-center-dir", str(cc),
    ])
    rc = run_learn(args)
    assert rc == 0
    assert (vault / "learning" / "2026-06-04.md").exists()
    assert (vault / "learning" / "_knowledge.md").exists()
    assert (reports / "learning_knowledge.json").exists()
    assert (reports / "agent_insights.json").exists()
    assert (cc / "bridge" / "tony-stocks" / "learning" / "2026-06-04.md").exists()


def test_run_learn_survives_missing_inputs(tmp_path):
    reports = tmp_path / "reports"  # nothing seeded
    args = build_parser().parse_args([
        "learn", "--config", "config/default_config.yaml", "--date", "2026-06-04",
        "--no-llm", "--min-sample", "1", "--reports-dir", str(reports), "--vault-dir", str(tmp_path / "v"),
        "--no-bridge",
    ])
    assert run_learn(args) == 0  # fail-quiet, still exits clean


_FUNNEL_FIXTURE = {
    "research_only": True,
    "total_picks": 12,
    "stages": [
        {"stage": "recommendation_rank", "verdict": "helps",
         "kept_win_rate": 0.7, "dropped_win_rate": 0.2},
        {"stage": "earnings_blackout", "verdict": "neutral",
         "kept_win_rate": 0.5, "dropped_win_rate": 0.5},
    ],
}


def test_nightly_facts_incorporate_funnel_eval_report():
    """When a funnel_eval report is present, the funnel_value dimension reflects it."""
    facts = build_nightly_facts(
        [{"symbol": "MARA", "result": "target_hit", "return_pct": 10}],
        teaching=None, funnel_report=_FUNNEL_FIXTURE, closed_paper=None,
        as_of="2026-06-04", min_sample=1)
    fv = facts.dimension("funnel_value")
    assert fv is not None
    assert any(r["stage"] == "recommendation_rank" and r["verdict"] == "helps"
               for r in fv.rows)
    assert "recommendation_rank" in fv.headline


def test_run_learn_refreshes_funnel_eval_and_consumes_it(tmp_path, monkeypatch):
    """End-to-end: run_learn calls the funnel-eval refresh (which writes
    reports/funnel_eval.json) and then feeds it into build_nightly_facts."""
    reports = tmp_path / "reports"
    _seed(reports)

    # Stub the refresh step to drop a known funnel_eval.json (decoupled from the DB),
    # proving run_learn writes *into the path it reads* and the fixture flows through.
    def _fake_refresh(reports_dir, config_path, *, days, min_sample):
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "funnel_eval.json").write_text(
            json.dumps(_FUNNEL_FIXTURE), encoding="utf-8")
        return True

    captured = {}
    import trading_bot.analytics.nightly_learning as nl
    orig = nl.build_nightly_facts

    def _spy(outcomes, teaching, funnel_report, closed_paper, **kw):
        captured["funnel"] = funnel_report
        return orig(outcomes, teaching, funnel_report, closed_paper, **kw)

    monkeypatch.setattr(cli, "_refresh_funnel_eval_for_learning", _fake_refresh)
    monkeypatch.setattr(nl, "build_nightly_facts", _spy)

    args = build_parser().parse_args([
        "learn", "--config", "config/default_config.yaml", "--date", "2026-06-04",
        "--no-llm", "--min-sample", "1", "--reports-dir", str(reports),
        "--vault-dir", str(tmp_path / "v"), "--no-bridge",
    ])
    assert run_learn(args) == 0
    assert (reports / "funnel_eval.json").exists()
    assert captured["funnel"] == _FUNNEL_FIXTURE  # the report fed the learner


def test_run_learn_survives_broken_funnel_eval(tmp_path, monkeypatch):
    """A corrupt funnel_eval.json must not crash the run (fail-quiet)."""
    reports = tmp_path / "reports"
    _seed(reports)
    (reports / "funnel_eval.json").write_text("{not valid json", encoding="utf-8")
    # Skip the real refresh so the broken file survives to the read step.
    monkeypatch.setattr(cli, "_refresh_funnel_eval_for_learning",
                        lambda *a, **k: False)
    args = build_parser().parse_args([
        "learn", "--config", "config/default_config.yaml", "--date", "2026-06-04",
        "--no-llm", "--min-sample", "1", "--reports-dir", str(reports),
        "--vault-dir", str(tmp_path / "v"), "--no-bridge",
    ])
    assert run_learn(args) == 0  # broken funnel report -> treated as absent, still clean
