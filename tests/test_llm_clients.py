from trading_bot.analytics.llm_clients import resolve_provider, model_for, make_llm_client


def test_resolve_provider_explicit_wins():
    assert resolve_provider("gemini", env={}) == "gemini"
    assert resolve_provider("anthropic", env={}) == "anthropic"
    assert resolve_provider("none", env={"GEMINI_API_KEY": "x"}) == "none"


def test_resolve_provider_auto_prefers_gemini():
    assert resolve_provider("auto", env={"GEMINI_API_KEY": "x"}) == "gemini"
    assert resolve_provider("auto", env={"GOOGLE_API_KEY": "x"}) == "gemini"
    assert resolve_provider("auto", env={"ANTHROPIC_API_KEY": "x"}) == "anthropic"
    assert resolve_provider("auto", env={}) == "none"
    # both set -> gemini wins (operator's stack)
    assert resolve_provider(None, env={"GEMINI_API_KEY": "g", "ANTHROPIC_API_KEY": "a"}) == "gemini"


def test_model_for_picks_per_provider():
    lcfg = {"gemini_model": "gemini-2.0-flash", "anthropic_model": "claude-sonnet-4-6"}
    assert model_for("gemini", lcfg) == "gemini-2.0-flash"
    assert model_for("anthropic", lcfg) == "claude-sonnet-4-6"
    assert model_for("gemini", {}) == "gemini-2.0-flash"        # default
    assert model_for("anthropic", {}) == "claude-sonnet-4-6"    # default


def test_make_llm_client_is_failsafe():
    assert make_llm_client("none") is None
    # gemini with no key present -> None (no crash), regardless of SDK install state
    assert make_llm_client("gemini", env={}) is None
