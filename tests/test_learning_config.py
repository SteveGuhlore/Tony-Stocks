from trading_bot.settings import load_scanner_settings


def test_learning_block_loads(tmp_path):
    cfg = tmp_path / "c.yaml"
    cfg.write_text(
        "learning:\n"
        "  enabled: true\n"
        "  use_llm: false\n"
        "  min_sample: 7\n"
        "  model: claude-sonnet-4-6\n"
        "  lookback_days: 90\n"
        "  knowledge_history_cap: 20\n"
        "  bridge_to_cc: true\n",
        encoding="utf-8")
    s = load_scanner_settings(str(cfg))
    assert s.learning["enabled"] is True
    assert s.learning["min_sample"] == 7
    assert s.learning["model"] == "claude-sonnet-4-6"


def test_default_config_has_learning_block():
    s = load_scanner_settings("config/default_config.yaml")
    assert s.learning is not None
    assert s.learning["provider"] == "auto"
    assert s.learning["gemini_model"] == "gemini-2.0-flash"
    assert s.learning["anthropic_model"] == "claude-sonnet-4-6"
    assert s.learning["bridge_to_cc"] is True
