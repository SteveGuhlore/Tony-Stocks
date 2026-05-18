Write-Host "Trading Bot Project - tests"

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    Write-Host "Activating .venv..."
    . .\.venv\Scripts\Activate.ps1
}

# Use a per-session temp dir inside the workspace. Some sandboxed Windows
# sessions cannot create directories under LOCALAPPDATA.
$sessionId   = [System.DateTime]::Now.ToString("yyyyMMdd_HHmmss")
$sessionBase = Join-Path (Get-Location) ".pytest_tmp_sessions"
$sessionTemp = Join-Path $sessionBase $sessionId
New-Item -ItemType Directory -Force $sessionTemp | Out-Null
$env:TMP  = $sessionTemp
$env:TEMP = $sessionTemp

# Prune sessions older than 2 hours (silently — ignore locks)
Get-ChildItem -Path $sessionBase -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddHours(-2) } |
    ForEach-Object {
        Remove-Item $_.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }

Write-Host "Session temp: $sessionTemp"
Write-Host "Running compile check..."
$env:PYTHONPATH = "src"
python -m compileall src -q

Write-Host "Running pytest..."
python -m pytest --basetemp $sessionTemp
