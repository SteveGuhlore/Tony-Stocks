Write-Host "=== Trading Bot Agent Start Check ==="
Write-Host "Current folder: $(Get-Location)"
Write-Host ""
Write-Host "--- Git status ---"
git status --short
Write-Host ""
Write-Host "--- Important files ---"
Get-ChildItem AGENTS.md, AGENT_STATE.md, CURRENT_STATUS.md, ROADMAP.md, TESTING_CHECKLIST.md -ErrorAction SilentlyContinue | Select-Object Name, Length, LastWriteTime
Write-Host ""
Write-Host "Paste this output into the current AI agent before it edits files."
