# daemon-daily-run.ps1 — run the agent loop for a bounded window, then stop it.
#
# The 24/7 uvicorn API server is managed separately (run-services.ps1) and is
# left untouched here — only the agent.loop daemon is cycled. Used as a daily
# scheduled task so the live receipt feed stays fresh through the judging
# window without paying for a continuously-running Gemini ensemble.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/daemon-daily-run.ps1
#   powershell -ExecutionPolicy Bypass -File scripts/daemon-daily-run.ps1 -Minutes 90
#
# Register as a daily task (runs 15:00 local, no admin needed):
#   $a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File C:\Users\tangm\Documents\GitHub\reasoning-receipt\scripts\daemon-daily-run.ps1"
#   $t = New-ScheduledTaskTrigger -Daily -At 15:00
#   Register-ScheduledTask -TaskName "rrtrace-daemon-daily" -Action $a -Trigger $t -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable) -Force

param(
    [int]$Minutes = 60,
    [string]$LogDir = "tmp/services"
)

$ErrorActionPreference = "Continue"
$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

$logRoot = Join-Path $repoRoot $LogDir
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$agentPidFile = Join-Path $logRoot "agent.pid"
$agentLog     = Join-Path $logRoot "agent.log"
$pauseFlag    = Join-Path $logRoot "PAUSED"
$runLog       = Join-Path $logRoot "daily-run.log"

function Write-RunLog($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $runLog -Value "$ts $msg"
    Write-Host "[daemon-daily-run] $msg"
}

# Sweep any stale agent.loop processes so daemons never stack (a past incident:
# seven concurrent loops after lost PID tracking, blowing the Gemini quota).
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '-m agent\.loop' } |
    ForEach-Object {
        try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-RunLog "swept stale agent.loop pid $($_.ProcessId)" } catch {}
    }

# Clear the PAUSED marker for the duration of the run.
Remove-Item $pauseFlag -Force -ErrorAction SilentlyContinue

# Start the agent loop, detached.
$agent = Start-Process -PassThru -FilePath "uv" `
    -ArgumentList @("run","python","-m","agent.loop") `
    -RedirectStandardOutput $agentLog `
    -RedirectStandardError  "$agentLog.err" `
    -WindowStyle Hidden
$agent.Id | Set-Content $agentPidFile
Write-RunLog "agent.loop started pid $($agent.Id) — running for $Minutes min"

Start-Sleep -Seconds ($Minutes * 60)

# Stop the agent loop (recorded PID + cmdline sweep for safety).
try { Stop-Process -Id $agent.Id -Force -ErrorAction Stop } catch {}
Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match '-m agent\.loop' } |
    ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }
Remove-Item $agentPidFile -Force -ErrorAction SilentlyContinue

$stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Set-Content -Path $pauseFlag -Value "Daemon auto-stopped $stamp after $Minutes-min daily run"
Write-RunLog "agent.loop stopped — daemon paused until next daily run"

# Refresh the dashboard snapshot so the GitHub Pages static fallback reflects
# the receipts this run emitted; push only when the change is non-trivial
# (a moved exported_at timestamp alone is noise). Pure DB read — no Gemini.
Write-RunLog "regenerating dashboard snapshot"
& uv run python -m scripts.export-snapshot 2>&1 | Out-Null
$numstat = & git diff --numstat -- dashboard/public/snapshot.json
if ([string]::IsNullOrWhiteSpace($numstat)) {
    Write-RunLog "snapshot unchanged"
} else {
    $added = [int](($numstat -split '\s+')[0])
    if ($added -ge 5) {
        & git add dashboard/public/snapshot.json
        & git commit -m "snapshot: daily refresh $(Get-Date -Format 'yyyy-MM-dd HH:mm')" --quiet
        $pushOut = & bash scripts/safe-push.sh 2>&1
        Write-RunLog "snapshot pushed: $pushOut"
    } else {
        & git checkout -- dashboard/public/snapshot.json
        Write-RunLog "snapshot diff trivial ($added lines) — skipped push"
    }
}
