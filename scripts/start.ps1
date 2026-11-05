param([switch]$SystemPython)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExecutable = if ((Test-Path -LiteralPath "$projectRoot\.venv\Scripts\python.exe") -and -not $SystemPython) { "$projectRoot\.venv\Scripts\python.exe" } else { 'python' }
if (-not (Test-Path -LiteralPath "$projectRoot\frontend\dist\index.html")) {
    throw 'Frontend has not been built. Run setup.bat first, or npm install and npm run build inside frontend.'
}
Write-Host 'Distributed Systems - Fault Tolerance Lab' -ForegroundColor Cyan
$labPort = if ($env:LAB_PORT) { $env:LAB_PORT } else { '8000' }
Write-Host "Open http://127.0.0.1:$labPort. Ctrl+C stops all child processes."
& $pythonExecutable -m backend
exit $LASTEXITCODE
