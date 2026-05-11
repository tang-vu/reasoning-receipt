#!/usr/bin/env bash
# deploy-contract.sh — deploy ReceiptRegistry to Arc testnet.
# Requires: foundry on PATH, RPC + DEPLOYER_PRIVATE_KEY in .env.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

: "${RPC:?RPC is unset; export it or set in .env}"
: "${DEPLOYER_PRIVATE_KEY:?DEPLOYER_PRIVATE_KEY is unset; export it or set in .env}"

cd contracts
if [[ ! -d lib/forge-std ]]; then
  echo "[deploy] installing forge-std"
  forge install --no-commit foundry-rs/forge-std
fi

echo "[deploy] forge build"
forge build

echo "[deploy] forge script Deploy"
forge script script/Deploy.s.sol \
  --rpc-url "$RPC" \
  --private-key "$DEPLOYER_PRIVATE_KEY" \
  --broadcast \
  --legacy

echo "[deploy] done. Set RECEIPT_REGISTRY_ADDRESS in .env to the printed address."
