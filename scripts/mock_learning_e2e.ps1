# scripts/mock_learning_e2e.ps1
# Full tandem dress rehearsal for the nightly self-learning loop. Runs the test suite,
# then a live deterministic pass into a THROWAWAY temp sandbox (never the live vault/CC),
# optionally one real LLM pass if ANTHROPIC_API_KEY is set, then the full project suite.
$ErrorActionPreference = "Stop"
$env:PYTHONPATH = "src"

Write-Host "== 1) Learner unit + integration + e2e suite ==" -ForegroundColor Cyan
python -m pytest tests/test_nightly_learning.py tests/test_learning_knowledge.py `
  tests/test_learning_narrator.py tests/test_learning_writer.py `
  tests/test_agent_bridge_batch.py tests/test_learning_config.py `
  tests/test_learning_cli.py tests/test_learning_e2e.py -q
if ($LASTEXITCODE -ne 0) { throw "learner suite failed" }

Write-Host "== 2) Live deterministic run into a temp sandbox (no LLM, no live paths) ==" -ForegroundColor Cyan
$sandbox = Join-Path $env:TEMP ("learn_e2e_" + (Get-Date -Format yyyyMMdd_HHmmss))
$reports = Join-Path $sandbox "reports"
New-Item -ItemType Directory -Force -Path $reports | Out-Null
@'
[{"symbol":"MARA","pick_date":"2026-06-01","result":"target_hit","return_pct":12,"setup_category":"Momentum / Buy","total_score":80,"days_held":4,"entry":13.7,"stop":12.2,"exit":16.3},
 {"symbol":"CVS","pick_date":"2026-06-01","result":"stop_hit","return_pct":-4,"setup_category":"Pullback / Buy","total_score":55,"days_held":2,"entry":60,"stop":58,"exit":58}]
'@ | Out-File -Encoding utf8 (Join-Path $reports "tony_stocks_outcomes.json")
python -m trading_bot.cli learn --config config/default_config.yaml --date 2026-06-04 --no-llm --min-sample 1 `
  --reports-dir $reports --vault-dir (Join-Path $sandbox "vault") --command-center-dir (Join-Path $sandbox "CC")
Write-Host "Artifacts in: $sandbox"
Get-ChildItem -Recurse $sandbox | Select-Object FullName

Write-Host "== 3) (optional) one LIVE LLM pass if ANTHROPIC_API_KEY is set ==" -ForegroundColor Cyan
if ($env:ANTHROPIC_API_KEY) {
  python -m trading_bot.cli learn --config config/default_config.yaml --date 2026-06-05 --min-sample 1 `
    --reports-dir $reports --vault-dir (Join-Path $sandbox "vault") --command-center-dir (Join-Path $sandbox "CC")
  Write-Host "LLM narrative -> $sandbox\vault\learning\2026-06-05.md"
} else {
  Write-Host "ANTHROPIC_API_KEY not set - skipped live LLM pass (fallback already proven)."
}

Write-Host "== 4) Full project suite (nothing else broke) ==" -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File .\scripts\run_tests.ps1
