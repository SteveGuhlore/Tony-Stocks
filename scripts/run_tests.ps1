Write-Host "Trading Bot Project - tests"

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv..."
    . .\.venv\Scripts\Activate.ps1
}

# Keep pytest temp outside the repo. Project-local .pytest_tmp paths are often
# locked on Windows (IDE sync, WSL cross-mount, stale partial deletes).
$sessionId = [System.DateTime]::Now.ToString("yyyyMMdd_HHmmss")
if ($env:LOCALAPPDATA) {
    $testRoot = Join-Path $env:LOCALAPPDATA "TradingBotTests"
} else {
    $testRoot = Join-Path $env:TEMP "TradingBotTests"
}
$pytestBase = Join-Path (Join-Path $testRoot "pytest") $sessionId
$processTemp = Join-Path (Join-Path $testRoot "tmp") $sessionId
New-Item -ItemType Directory -Force $pytestBase | Out-Null
New-Item -ItemType Directory -Force $processTemp | Out-Null
$env:TMP = $processTemp
$env:TEMP = $processTemp

# Prune pytest/tmp sessions older than 2 hours (ignore locks on stale dirs)
$pruneTargets = @(
    (Join-Path $testRoot "pytest"),
    (Join-Path $testRoot "tmp")
)
foreach ($target in $pruneTargets) {
    if (-not (Test-Path $target)) { continue }
    Get-ChildItem -Path $target -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-2) } |
        ForEach-Object {
            Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
        }
}

Write-Host "Pytest basetemp: $pytestBase"
Write-Host "Process TMP/TEMP: $processTemp"
Write-Host "Running compile check..."
$env:PYTHONPATH = "src"
python -m compileall src -q
if ($LASTEXITCODE -ne 0) {
    Write-Error "compileall failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

Write-Host "Running pytest..."
python -m pytest --basetemp $pytestBase
$pytestExit = $LASTEXITCODE
if ($pytestExit -ne 0) {
    Write-Error "pytest failed with exit code $pytestExit"
    exit $pytestExit
}

Write-Host "All tests passed."
exit 0
