# test-all.ps1 — Run the full test suite (backend + frontend) in CI.
# Usage: pwsh scripts/test-all.ps1
# Exits with a non-zero exit code if any step fails.

$ErrorActionPreference = 'Stop'

$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir    = Split-Path -Parent $ScriptDir

$BackendFailed  = $false
$FrontendFailed = $false

Write-Host "=============================="
Write-Host "  Running backend tests (pytest + hypothesis)"
Write-Host "=============================="
Push-Location "$RootDir\backend"
try {
    poetry run pytest tests/ --tb=short -q
} catch {
    $BackendFailed = $true
    Write-Host "Backend tests FAILED: $_"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=============================="
Write-Host "  Running frontend tests (Vitest)"
Write-Host "=============================="
Push-Location "$RootDir\frontend"
try {
    npm run test
} catch {
    $FrontendFailed = $true
    Write-Host "Frontend tests FAILED: $_"
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "=============================="
Write-Host "  Test summary"
Write-Host "=============================="

if ($BackendFailed)  { Write-Host "FAILED: backend tests" }
if ($FrontendFailed) { Write-Host "FAILED: frontend tests" }

if ($BackendFailed -or $FrontendFailed) {
    Write-Host ""
    Write-Host "One or more test suites failed."
    exit 1
}

Write-Host "All tests passed."
exit 0
