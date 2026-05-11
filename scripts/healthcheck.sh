#!/usr/bin/env bash
# healthcheck.sh — quick liveness probe for the FastAPI server + a /price round-trip.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
MARKET_ID="${MARKET_ID:-mock-polymarket-fed-rate-cut-jun-2026}"

echo "[healthcheck] hitting $BASE_URL/healthz"
curl -fsS "$BASE_URL/healthz" | tee /dev/stderr | grep -q '"ok": *true' || {
  echo "[healthcheck] /healthz failed"; exit 1;
}

echo
echo "[healthcheck] 402 challenge for /price/$MARKET_ID"
status=$(curl -s -o /tmp/rr-402.json -w "%{http_code}" "$BASE_URL/price/$MARKET_ID")
if [[ "$status" != "402" ]]; then
  echo "[healthcheck] expected 402, got $status"; cat /tmp/rr-402.json; exit 1
fi
cat /tmp/rr-402.json
echo

echo "[healthcheck] OK"
