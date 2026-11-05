param([switch]$SkipFrontend)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
function Assert-Exit([string]$step) { if ($LASTEXITCODE -ne 0) { throw "$step failed (exit $LASTEXITCODE)" } }
python -m venv .venv
Assert-Exit 'Create virtual environment'
& "$projectRoot\.venv\Scripts\python.exe" -m pip install -r requirements.txt
Assert-Exit 'Install Python dependencies'
if (-not $SkipFrontend) {
    Push-Location -LiteralPath "$projectRoot\frontend"
    try {
        if (Test-Path -LiteralPath 'package-lock.json') { npm ci } else { npm install }
        Assert-Exit 'Install frontend dependencies'
        npm run build
        Assert-Exit 'Build frontend'
    } finally { Pop-Location }
}
Write-Host 'Ready. Run .\start.bat, then open http://127.0.0.1:8000' -ForegroundColor Green
