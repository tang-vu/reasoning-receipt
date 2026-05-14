#!/usr/bin/env bash
# safe-push.sh — banned-file gate + AI-trailer strip
#
# Dead-zone (02:00-07:30 VN) and 90-min-gap cadence rules removed —
# Harvey explicitly asked to push freely after infra was wired live.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

now=$(date +%s)
last_push_file=".git/.last_push"

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
    # Match only the actual AI-attribution trailer formats — not any
    # commit body that happens to contain the phrase 'generated with'.
    # Trailers from AI tools always live on their own line and follow
    # one of these exact shapes:
    #   "🤖 Generated with [Claude Code](...)"
    #   "Generated with Claude"
    #   "Co-authored-by: Claude ..."
    if echo "$msg" | grep -qiE '(🤖 generated with|generated with \[?claude|generated with anthropic|co-authored-by:.*claude|co-authored-by:.*anthropic)'; then
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
