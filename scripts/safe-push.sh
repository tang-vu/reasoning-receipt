#!/usr/bin/env bash
# safe-push.sh — banned-file gate + cadence gate + AI-trailer strip
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

# Use local time directly. Harvey's machine is in VN (UTC+7).
# `TZ=Asia/Ho_Chi_Minh` works on Linux/macOS, but Git Bash on Windows reads
# the Windows system clock as already-local and then "re-converts" it via
# the TZ env — yielding a 7-hour-wrong figure that falsely trips the dead
# zone. Plain `date` here matches the wall clock the human actually sees.
hour=$(date +%H)
minute=$(date +%M)
now=$(date +%s)

# === Cadence: dead zone (02:00 – 07:29 VN time) ===
if (( 10#$hour >= 2 && 10#$hour < 8 )); then
  if ! (( 10#$hour == 7 && 10#$minute >= 30 )); then
    echo "[safe-push] DEAD ZONE ($hour:$minute VN). Push deferred. Commits stay local."
    exit 0
  fi
fi

# === Cadence: 90-minute min gap between pushes ===
last_push_file=".git/.last_push"
if [[ -f "$last_push_file" ]]; then
  last=$(cat "$last_push_file" 2>/dev/null || echo 0)
  elapsed=$(( now - last ))
  if (( elapsed < 5400 )); then
    remaining=$(( (5400 - elapsed) / 60 ))
    echo "[safe-push] Last push was $((elapsed/60))m ago. Wait ${remaining}m. Skipping."
    exit 0
  fi
fi

banned='^(CLAUDE\.md|notes/|\.claude|AGENTS\.md|\.aider|\.cursor|\.continue|\.codeium)'

# === Staged + tracked check ===
if git ls-files | grep -qE "$banned"; then
  echo "[safe-push] BLOCKED: banned files tracked in repo."
  git ls-files | grep -E "$banned"
  exit 1
fi
if git diff --cached --name-only | grep -qE "$banned"; then
  echo "[safe-push] BLOCKED: banned files staged."
  git diff --cached --name-only | grep -E "$banned"
  exit 1
fi

# === Unpushed-commit check ===
if git rev-parse --quiet --verify origin/main >/dev/null 2>&1; then
  if git log origin/main..HEAD --name-only --pretty=format: 2>/dev/null | sort -u | grep -qE "$banned"; then
    echo "[safe-push] BLOCKED: banned files in unpushed commits."
    exit 1
  fi
fi

# === Strip AI trailers from any unpushed commit messages (paranoia) ===
if git rev-parse --quiet --verify origin/main >/dev/null 2>&1; then
  for sha in $(git rev-list origin/main..HEAD); do
    msg=$(git log -1 --format=%B "$sha")
    if echo "$msg" | grep -qiE '(generated with|co-authored-by:.*claude|co-authored-by:.*anthropic|🤖)'; then
      echo "[safe-push] BLOCKED: commit $sha has AI-attribution trailer."
      echo "$msg"
      echo "Run: git rebase -i origin/main and strip the trailer."
      exit 1
    fi
  done
fi

# === Jitter then push ===
jitter=$(( RANDOM % 85 + 5 ))
echo "[safe-push] Jitter: sleeping ${jitter}s before push…"
sleep "$jitter"

git push origin main
echo "$now" > "$last_push_file"
echo "[safe-push] Pushed at $(TZ=Asia/Ho_Chi_Minh date '+%Y-%m-%d %H:%M %Z')"
