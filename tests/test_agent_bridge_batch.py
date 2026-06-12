import trading_bot.agent_bridge as ab


def test_batch_append_and_dedup(tmp_path, monkeypatch):
    f = tmp_path / "agent_insights.json"
    monkeypatch.setenv("TONY_INSIGHTS_FILE", str(f))
    rows = [{"category": "setup_edge", "insight": "Momentum edge", "confidence": "high", "symbols": []},
            {"category": "regime", "insight": "3-win streak", "confidence": "low", "symbols": []}]
    assert ab.record_agent_insights_batch(rows, on_date="2026-06-04") == 2
    assert len(ab.load_agent_insights()) == 2
    # re-running the same date+insight must not duplicate
    assert ab.record_agent_insights_batch(rows, on_date="2026-06-04") == 0
    assert len(ab.load_agent_insights()) == 2
    # a new insight on the same date appends
    assert ab.record_agent_insights_batch(
        [{"category": "sector_signal", "insight": "energy weak", "confidence": "med", "symbols": []}],
        on_date="2026-06-04") == 1
    assert len(ab.load_agent_insights()) == 3


def test_insights_file_env_override(tmp_path, monkeypatch):
    f = tmp_path / "staging" / "agent_insights.json"
    monkeypatch.setenv("TONY_INSIGHTS_FILE", str(f))
    ab.record_agent_insight("staging twin writes here", category="test")
    assert f.exists()
    assert ab.load_agent_insights()[-1]["insight"] == "staging twin writes here"
    monkeypatch.delenv("TONY_INSIGHTS_FILE")
    assert ab._insights_file().name == "agent_insights.json"
    assert "reports" in str(ab._insights_file())
