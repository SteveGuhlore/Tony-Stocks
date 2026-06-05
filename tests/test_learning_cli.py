import json
from pathlib import Path

from trading_bot.cli import run_learn, build_parser


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
