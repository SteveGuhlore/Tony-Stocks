# Trading Bot Project - File Structure

_Last updated: 2026-05-19 (V15.8)_

```text
TradingBotAgentProject/
  AGENTS.md
  AGENT_STATE.md
  CURRENT_STATUS.md
  ROADMAP.md
  KNOWN_BACKLOG.md
  ARCHITECTURE_RULES.md
  DESIGN_RULES.md
  TESTING_CHECKLIST.md
  FILE_STRUCTURE.md
  README.md
  requirements.txt
  .env.example

  config/
    default_config.yaml
    scoring_config.yaml
    universe_config.yaml
    universe_swing_research_config.yaml

  configs/
    default_config.yaml              legacy backtest config

  data/
    .gitkeep
    cache/
      .gitkeep

  outputs/
    .gitkeep

  logs/
    .gitkeep

  docs/
    AGENT_ROTATION_WORKFLOW.md
    AI_INTEGRATION.md
    BROKER_SETUP.md
    DATA_SOURCES.md
    LEGAL_AND_RISK.md
    PROFITABILITY_RESEARCH_PLAN.md
    RESEARCH_REPORT.md
    SETUP_CLI.md
    STRATEGY_GUIDELINES.md
    STRATEGY_REVIEW_TEMPLATE.md

  scripts/
    agent_start_check.ps1
    run_backtest_sample.ps1
    run_tests.ps1
    run_scanner.ps1
    run_seed_demo_snapshots.ps1
    run_snapshot_update.ps1
    run_watch_mode.ps1
    run_dashboard.ps1

  src/
    main.py
    trading_bot/
      __init__.py
      cli.py
      settings.py
      logging_config.py
      backtester.py
      config.py
      metrics.py
      risk.py
      data/
        __init__.py
        universe.py
        symbol_quarantine.py
        market_data.py
        universe_rotation.py
        cache.py
      indicators/
        __init__.py
        technicals.py
      intraday/
        __init__.py
        features.py
      analytics/
        __init__.py
        outcomes.py
      scoring/
        __init__.py
        score_engine.py
        score_models.py
      snapshots/
        __init__.py
        active_tracking.py
        entry_triggers.py
        followup.py
        seeding.py
      tony/
        __init__.py
        events.py
      storage/
        __init__.py
        database.py
        repositories.py
      paper/
        __init__.py
        paper_journal.py
      dashboard/
        __init__.py
        app.py
        helpers.py
        theme.py
      utils/
        __init__.py
        time_utils.py
        validation.py
      strategies/
        base.py
        moving_average_crossover.py
      execution/
        paper.py

  tests/
    test_backtester.py
    test_risk.py
    test_indicators.py
    test_score_engine.py
    test_universe.py
    test_database.py
    test_scanner_smoke.py
    test_snapshot_followup.py
    test_intraday_features.py
    test_outcome_analytics.py
    test_alpaca_provider.py
    test_v9_scaling.py
    test_tony_analyst.py
    test_dashboard_helpers.py     (V11) 50 tests for dashboard pure helpers
    test_watch_run.py             (V12) 52 tests for watch run CRUD + helpers
    test_v13_tony_learning.py     (V13) 39 tests for Tony hypothesis-to-outcome tracking
```
