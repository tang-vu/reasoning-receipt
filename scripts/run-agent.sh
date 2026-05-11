#!/usr/bin/env bash
# run-agent.sh — long-running agent loop with auto-restart.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

while true; do
  echo "[run-agent] starting agent.loop"
  uv run python -m agent.loop || true
  echo "[run-agent] loop exited; sleeping 5s and restarting"
  sleep 5
done
