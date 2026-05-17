# Trading Bot Project - File Structure

_Last updated: 2026-05-17_

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
        market_data.py
        cache.py
      indicators/
        __init__.py
        technicals.py
      scoring/
        __init__.py
        score_engine.py
        score_models.py
      snapshots/
        __init__.py
        followup.py
        seeding.py
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
```
