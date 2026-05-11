#!/usr/bin/env bash
# setup.sh — clean clone → working dev server.
# Idempotent. Safe to re-run.
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

echo "[setup] Python + uv sync"
if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install: https://github.com/astral-sh/uv"
  exit 1
fi
uv sync --extra dev

echo "[setup] .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "[setup]  → .env created from .env.example. Fill in keys to leave mock mode."
fi

echo "[setup] DB init"
mkdir -p data
uv run python -c "from storage.db import init_db; init_db(); print('db ready')"

if command -v forge >/dev/null 2>&1; then
  echo "[setup] Foundry — install forge-std"
  (cd contracts && forge install --no-commit foundry-rs/forge-std >/dev/null 2>&1 || true)
  (cd contracts && forge build) >/dev/null 2>&1 || echo "[setup]  → forge build failed (non-fatal)."
else
  echo "[setup] Foundry not on PATH. Install: https://book.getfoundry.sh/"
fi

if [[ -d dashboard ]]; then
  if command -v npm >/dev/null 2>&1; then
    echo "[setup] dashboard deps"
    (cd dashboard && npm install --silent --no-audit --no-fund)
  fi
fi

echo "[setup] sanity: pytest"
uv run --extra dev pytest tests/ -q

echo "[setup] done. Start the server with: uv run uvicorn server.main:app --reload"
