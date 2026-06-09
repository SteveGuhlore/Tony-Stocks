"""Comprehensive tandem dress-rehearsal for the nightly self-learning loop.

Runs the whole pipeline through the `learn` CLI against an isolated temp vault + temp
CC dir (never the live ones), asserting: all four sinks, the CC bridge contract bytes,
idempotency, and — crucially — that the knowledge base EVOLVES across nights
(an edge promotes then demotes). Deterministic (LLM forced off).
"""
import json

from trading_bot.cli import run_learn, build_parser


def _args(reports, vault, cc, date, no_bridge=False):
    a = ["learn", "--config", "config/default_config.yaml", "--date", date, "--no-llm",
         "--reports-dir", str(reports), "--vault-dir", str(vault),
         "--command-center-dir", str(cc)]
    if no_bridge:
        a.append("--no-bridge")
    return build_parser().parse_args(a)


def _seed(reports, day, momentum_results):
    """momentum_results: list of 'target_hit'/'stop_hit' for the Momentum / Buy setup."""
    reports.mkdir(parents=True, exist_ok=True)
    rows = []
    for i, res in enumerate(momentum_results):
        ret = 10 if res == "target_hit" else -4
        rows.append({"symbol": f"M{i}", "pick_date": day, "result": res, "return_pct": ret,
                     "setup_category": "Momentum / Buy", "total_score": 78, "days_held": 3,
                     "entry": 100, "stop": 96, "exit": 110 if ret > 0 else 96})
    (reports / "tony_stocks_outcomes.json").write_text(json.dumps(rows), encoding="utf-8")
    (reports / "tony_teaching_log.json").write_text(json.dumps(
        {"agreement": {"agreed_right": 5, "agreed_wrong": 1,
                       "cc_overrode_saved": 3, "cc_overrode_missed": 1}}), encoding="utf-8")


def test_full_tandem_loop_with_evolution(tmp_path):
    reports, vault, cc = tmp_path / "reports", tmp_path / "vault", tmp_path / "CC"

    # NIGHT 1 — strong momentum edge
    _seed(reports, "2026-06-01", ["target_hit"] * 10 + ["stop_hit"] * 2)
    assert run_learn(_args(reports, vault, cc, "2026-06-01")) == 0

    assert (vault / "learning" / "2026-06-01.md").exists()
    assert (vault / "learning" / "_knowledge.md").exists()
    insights = json.loads((reports / "agent_insights.json").read_text())
    assert any(i["category"] == "setup_edge" for i in insights)

    bridge = cc / "bridge" / "tony-stocks" / "learning" / "2026-06-01.md"
    assert bridge.exists()
    btxt = bridge.read_text(encoding="utf-8")
    assert "export_type: bot-self-learning" in btxt and "source: trading-bot" in btxt

    kb1 = json.loads((reports / "learning_knowledge.json").read_text())
    mom1 = next(i for i in kb1["items"] if i["key"] == "setup:momentum / buy")
    assert mom1["win_rate"] >= 0.8

    # idempotency: re-run night 1 -> no insight dupes, bridge unchanged
    n_before = len(insights)
    bridge_mtime = bridge.stat().st_mtime_ns
    assert run_learn(_args(reports, vault, cc, "2026-06-01")) == 0
    assert len(json.loads((reports / "agent_insights.json").read_text())) == n_before
    assert bridge.stat().st_mtime_ns == bridge_mtime

    # NIGHT 2 (a week later) — edge collapses -> must DEMOTE + trend down
    _seed(reports, "2026-06-08", ["stop_hit"] * 10 + ["target_hit"] * 2)
    assert run_learn(_args(reports, vault, cc, "2026-06-08")) == 0
    kb2 = json.loads((reports / "learning_knowledge.json").read_text())
    mom2 = next(i for i in kb2["items"] if i["key"] == "setup:momentum / buy")
    assert mom2["first_seen"] == "2026-06-01"          # memory persisted
    assert mom2["status"] in {"decaying", "rejected"}  # evolved
    assert mom2["trend"] == "down"
    assert len(mom2["history"]) == 2                   # compounding


def test_missing_cc_dir_completes_local_sinks_but_fails_loud(tmp_path):
    # Reliability contract: a broken CC bridge must NOT silently pass (rc=0 used to hide
    # a dead handoff for days) — local sinks still complete, but the run exits non-zero
    # so the systemd timer flags it.
    reports, vault = tmp_path / "reports", tmp_path / "vault"
    _seed(reports, "2026-06-01", ["target_hit"] * 6 + ["stop_hit"] * 2)
    blocker = tmp_path / "blocker"
    blocker.write_text("x")  # CC path under a file -> unwritable
    assert run_learn(_args(reports, vault, blocker / "CC", "2026-06-01")) == 1
    assert (vault / "learning" / "2026-06-01.md").exists()  # local sinks still done
