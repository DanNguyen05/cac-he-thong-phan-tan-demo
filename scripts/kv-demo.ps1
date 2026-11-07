param(
    [ValidateSet('up','health','reset','stop','start','restart','crash','verify','logs','down')]
    [string]$Action='health',
    [ValidateSet('dashboard','coordinator','rpc','participant-a','participant-b','participant-c')]
    [string]$Service='coordinator'
)
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
$compose=@('compose','--project-name','kv-transaction-lab','--file',(Join-Path $root 'compose.yaml'))
function Invoke-Compose([string[]]$Arguments) {
    & docker @compose @Arguments
    if ($LASTEXITCODE -ne 0) { throw "Docker Compose failed ($LASTEXITCODE)" }
}
switch ($Action) {
    'up' {
        & docker info --format '{{.ServerVersion}}'
        if ($LASTEXITCODE -ne 0) { throw 'Start Docker Desktop (Linux engine) first.' }
        $ids=& docker @compose ps -q
        if (-not $ids) {
            foreach ($port in 19000..19005) {
                if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) { throw "Port $port already occupied; no unrelated app was stopped." }
            }
        }
        Invoke-Compose -Arguments @('up','-d','--build','--wait','--wait-timeout','180')
        Write-Host 'Dashboard: http://127.0.0.1:19000/rpc'
    }
    'health' {
        Invoke-Compose -Arguments @('ps','--all')
        Invoke-RestMethod http://127.0.0.1:19000/api/health | ConvertTo-Json -Depth 8
    }
    'reset' { Invoke-RestMethod -Method Post -ContentType application/json -Body '{}' http://127.0.0.1:19000/api/reset | ConvertTo-Json }
    'stop' { Invoke-Compose -Arguments @('stop',$Service) }
    'crash' { Invoke-Compose -Arguments @('kill','--signal','SIGKILL',$Service) }
    'start' { Invoke-Compose -Arguments @('start',$Service) }
    'restart' { Invoke-Compose -Arguments @('restart',$Service) }
    'logs' { Invoke-Compose -Arguments @('logs','--tail','100',$Service) }
    'verify' {
        foreach ($port in 19002..19005) {
            try { Invoke-RestMethod "http://127.0.0.1:$port/state" | Select-Object node,boot_id,kv,checkpoint,recovery,transactions | ConvertTo-Json -Depth 12 }
            catch { Write-Host "HTTP unreachable at $port : $($_.Exception.Message)" }
        }
    }
    'down' { Invoke-Compose -Arguments @('down') } # Named volumes retained. Never down -v.
}
