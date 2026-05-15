# run-services.ps1 — start uvicorn + agent loop in the background.
#
# Detached processes survive the calling shell (and any Claude Code session).
# Logs land in tmp/. Re-running this script kills any previous instance first
# so it's safe to call after editing code.
#
# Usage:
#   pwsh -ExecutionPolicy Bypass -File scripts/run-services.ps1
#
# Stop everything later with:
#   pwsh -ExecutionPolicy Bypass -File scripts/run-services.ps1 -Stop

param(
    [switch]$Stop,
    [int]$Port = 8000,
    [string]$LogDir = "tmp/services"
)

$ErrorActionPreference = "Stop"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

# Resolve paths
$logRoot = Join-Path $repoRoot $LogDir
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null

$serverPidFile = Join-Path $logRoot "server.pid"
$agentPidFile  = Join-Path $logRoot "agent.pid"
$serverLog     = Join-Path $logRoot "server.log"
$agentLog      = Join-Path $logRoot "agent.log"

function Stop-IfRunning($svcPidFile, $name) {
    if (Test-Path $svcPidFile) {
        $svcPid = Get-Content $svcPidFile -ErrorAction SilentlyContinue
        if ($svcPid) {
            try {
                Stop-Process -Id $svcPid -Force -ErrorAction Stop
                Write-Host "[run-services] stopped $name (pid $svcPid)"
            } catch {
                Write-Host "[run-services] $name (pid $svcPid) not running"
            }
        }
        Remove-Item $svcPidFile -Force -ErrorAction SilentlyContinue
    }
}

# Sweep ALL orphan processes whose CommandLine matches the given pattern.
# The PID-file approach above only kills the *latest* PID we recorded — if a
# previous restart lost track (PID file overwritten before the old process was
# stopped), zombie daemons accumulate and emit receipts in parallel. This was
# observed in production: seven concurrent agent.loop processes after multiple
# restarts, blowing through the Gemini quota. Pattern-based kill closes that.
function Stop-OrphansByCmdLine($pattern, $name) {
    $orphans = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue `
        | Where-Object { $_.CommandLine -match $pattern }
    if ($orphans) {
        foreach ($proc in $orphans) {
            try {
                Stop-Process -Id $proc.ProcessId -Force -ErrorAction Stop
                Write-Host "[run-services] swept orphan $name (pid $($proc.ProcessId), started $($proc.CreationDate))"
            } catch {
                # Already dead — fine.
            }
        }
    }
}

# === Stop mode ===
if ($Stop) {
    Stop-IfRunning $serverPidFile "uvicorn"
    Stop-IfRunning $agentPidFile  "agent loop"
    Stop-OrphansByCmdLine 'uvicorn.*server\.main' "uvicorn"
    Stop-OrphansByCmdLine '-m agent\.loop'        "agent loop"
    return
}

# Idempotency: kill stale instances first (PID file + orphan sweep).
Stop-IfRunning $serverPidFile "uvicorn (stale)"
Stop-IfRunning $agentPidFile  "agent loop (stale)"
Stop-OrphansByCmdLine 'uvicorn.*server\.main' "uvicorn (orphan)"
Stop-OrphansByCmdLine '-m agent\.loop'        "agent loop (orphan)"

# === Start uvicorn (FastAPI on :$Port) ===
Write-Host "[run-services] starting uvicorn on :$Port -> $serverLog"
$server = Start-Process -PassThru -FilePath "uv" `
    -ArgumentList @("run","uvicorn","server.main:app","--host","0.0.0.0","--port","$Port") `
    -RedirectStandardOutput $serverLog `
    -RedirectStandardError  "$serverLog.err" `
    -WindowStyle Hidden
$server.Id | Set-Content $serverPidFile
Write-Host "[run-services] uvicorn pid $($server.Id)"

# Give uvicorn a couple of seconds to bind before pointing the agent at the DB.
Start-Sleep -Seconds 3

# === Start agent loop ===
Write-Host "[run-services] starting agent loop -> $agentLog"
$agent = Start-Process -PassThru -FilePath "uv" `
    -ArgumentList @("run","python","-m","agent.loop") `
    -RedirectStandardOutput $agentLog `
    -RedirectStandardError  "$agentLog.err" `
    -WindowStyle Hidden
$agent.Id | Set-Content $agentPidFile
Write-Host "[run-services] agent loop pid $($agent.Id)"

Write-Host ""
Write-Host "Services running. Tail with:"
Write-Host "  Get-Content -Wait $serverLog"
Write-Host "  Get-Content -Wait $agentLog"
Write-Host ""
Write-Host "Stop with:"
Write-Host "  pwsh -ExecutionPolicy Bypass -File scripts/run-services.ps1 -Stop"
