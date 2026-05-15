# refresh-snapshot.ps1 — regenerate dashboard/public/snapshot.json from the
# local DB and push if changed. ZERO Gemini calls — pure DB read + git.
#
# Designed to run on a Task Scheduler interval while the agent loop is paused
# (PAUSED flag present). Keeps the GH Pages static fallback current so the
# dashboard still reflects the latest on-chain state if api.rrtrace.xyz
# hangs or the tunnel drops.
#
# Register (no admin needed):
#   $action = New-ScheduledTaskAction -Execute "powershell.exe" `
#       -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File C:\Users\tangm\Documents\GitHub\reasoning-receipt\scripts\refresh-snapshot.ps1"
#   $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) `
#       -RepetitionInterval (New-TimeSpan -Minutes 60) `
#       -RepetitionDuration (New-TimeSpan -Days 3650)   # NOT MaxValue — overflows the XML schema
#   $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd `
#       -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
#   Register-ScheduledTask -TaskName "rrtrace-refresh-snapshot" `
#       -Action $action -Trigger $trigger -Settings $settings -Force
#
# Manual test:  powershell -ExecutionPolicy Bypass -File scripts/refresh-snapshot.ps1
# Unregister:   Unregister-ScheduledTask -TaskName "rrtrace-refresh-snapshot" -Confirm:$false

$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$logFile = "tmp/services/refresh-snapshot.log"
function Log($msg) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $logFile -Value "$ts $msg"
}

# 1. Regenerate snapshot.json (reads DB, no Gemini)
Log "starting snapshot regen"
$exportOut = & uv run python -m scripts.export-snapshot 2>&1
Log "export-snapshot: $exportOut"

# 2. If diff is non-trivial (>500 bytes), commit + push. Tiny diffs (just
#    the exported_at timestamp moving forward by an hour) are noise; skip.
$diffStat = & git diff --stat dashboard/public/snapshot.json 2>&1
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($diffStat)) {
    Log "no changes — skipping push"
    return
}

# Count of meaningfully-changed lines (lines added/removed). If only the
# timestamp moved we'd see "snapshot.json | 2 +-" type output.
$numStat = (& git diff --numstat dashboard/public/snapshot.json) -split '\s+'
$added = [int]$numStat[0]
if ($added -lt 5) {
    Log "trivial diff ($added lines added) — skipping push"
    & git checkout -- dashboard/public/snapshot.json
    return
}

# 3. Commit + push via safe-push.sh (enforces banned-files + push).
& git add dashboard/public/snapshot.json
$commitMsg = "snapshot: hourly refresh — $(Get-Date -Format 'yyyy-MM-dd HH:mm')"
& git commit -m $commitMsg --quiet
$pushOut = & bash scripts/safe-push.sh 2>&1
Log "pushed: $pushOut"
