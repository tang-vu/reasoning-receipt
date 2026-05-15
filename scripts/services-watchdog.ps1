# services-watchdog.ps1 — restart uvicorn + agent loop if they die.
#
# Run as Task Scheduler "At Logon" + "Repeat every 5 minutes" so the backend
# survives a 2-week hackathon window even if a child process crashes.
#
# Register once (no admin):
#   $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File C:\Users\tangm\Documents\GitHub\reasoning-receipt\scripts\services-watchdog.ps1"
#   $trigger = New-ScheduledTaskTrigger -AtLogOn
#   $repeat  = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
#   Register-ScheduledTask -TaskName "rrtrace-watchdog" -Action $action -Trigger @($trigger,$repeat) -Settings (New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd) -Force
#
# Manual test:
#   powershell -ExecutionPolicy Bypass -File scripts/services-watchdog.ps1

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$serverPidFile = "tmp/services/server.pid"
$agentPidFile  = "tmp/services/agent.pid"
$pauseFlag     = "tmp/services/PAUSED"

# Manual override: dropping a file at tmp/services/PAUSED stops the watchdog
# from auto-restarting the agent loop. Use this to halt Gemini spend without
# kill-9ing the watchdog itself. Remove the file to resume.
if (Test-Path $pauseFlag) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path "tmp/services/watchdog.log" -Value "$ts paused (PAUSED flag present)"
    return
}

function Test-PidAlive($pidFile) {
    if (!(Test-Path $pidFile)) { return $false }
    $svcPid = Get-Content $pidFile -ErrorAction SilentlyContinue
    if (-not $svcPid) { return $false }
    return [bool](Get-Process -Id $svcPid -ErrorAction SilentlyContinue)
}

$serverAlive = Test-PidAlive $serverPidFile
$agentAlive  = Test-PidAlive $agentPidFile

if ($serverAlive -and $agentAlive) {
    # All good — nothing to do. Log a single line for audit.
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path "tmp/services/watchdog.log" -Value "$ts ok server=alive agent=alive"
    return
}

$ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
Add-Content -Path "tmp/services/watchdog.log" -Value "$ts restart server=$serverAlive agent=$agentAlive"

# Re-launch via the existing start script — it will stop stale PIDs first.
& powershell.exe -ExecutionPolicy Bypass -File "scripts/run-services.ps1"
