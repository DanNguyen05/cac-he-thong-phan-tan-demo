param([switch]$Offline, [switch]$Browser)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExecutable = if (Test-Path -LiteralPath "$projectRoot\.venv\Scripts\python.exe") { "$projectRoot\.venv\Scripts\python.exe" } else { 'python' }
New-Item -ItemType Directory -Force -Path "$projectRoot\test-results" | Out-Null
& $pythonExecutable -m pytest tests -q --basetemp test-results/pytest --junitxml=test-results/backend.xml
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Push-Location -LiteralPath "$projectRoot\frontend"
try {
    if ($Offline) { npm run build:offline } else { npm run build }
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    if ($Browser) {
        npx playwright test
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }
} finally { Pop-Location }
