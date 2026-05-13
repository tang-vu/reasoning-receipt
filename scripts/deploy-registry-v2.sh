#!/usr/bin/env bash
# deploy-registry-v2.sh — deploy ReceiptRegistryV2 to Arc testnet.
# Additive to V1 — leaves the existing RECEIPT_REGISTRY_ADDRESS untouched.
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
  echo "[deploy-v2] installing forge-std"
  forge install --no-commit foundry-rs/forge-std
fi

echo "[deploy-v2] forge build"
forge build

echo "[deploy-v2] forge test --match-contract ReceiptRegistryV2 (sanity)"
forge test --match-contract ReceiptRegistryV2 -q

echo "[deploy-v2] forge script DeployRegistryV2"
forge script script/DeployRegistryV2.s.sol \
  --rpc-url "$RPC" \
  --private-key "$DEPLOYER_PRIVATE_KEY" \
  --broadcast \
  --legacy

echo ""
echo "[deploy-v2] done."
echo "[deploy-v2] copy the address from the log above and set RECEIPT_REGISTRY_V2_ADDRESS in .env"
echo "[deploy-v2] then source-verify on Arc explorer (Blockscout):"
echo "[deploy-v2]   forge verify-contract \\"
echo "[deploy-v2]     --rpc-url \"\$RPC\" \\"
echo "[deploy-v2]     --verifier blockscout \\"
echo "[deploy-v2]     --verifier-url https://testnet.arcscan.app/api \\"
echo "[deploy-v2]     <ADDRESS> contracts/src/ReceiptRegistryV2.sol:ReceiptRegistryV2"
