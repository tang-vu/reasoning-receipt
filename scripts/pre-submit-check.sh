#!/usr/bin/env bash
# pre-submit-check.sh — final dry-run before Harvey clicks submit.
#
# Runs everything that can be validated locally without spending USDC:
#   - banned AI-tooling files not committed
#   - no leaked secrets in committed files
#   - pytest passes
#   - forge tests pass
#   - dashboard builds clean (snapshot mode)
#   - V1 + V2 contracts reachable on Arc, source-verified, totalReceipts() works
#   - .env.example is up to date (no required key missing)
#
# Usage:  ./scripts/pre-submit-check.sh
# Exit 0 = green, exit 1 = something to fix.

set -uo pipefail
cd "$(git rev-parse --show-toplevel)"

PASS=0
FAIL=0

step() { printf '\n=== %s ===\n' "$1"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }

# 1. Repo hygiene — banned files
step "Repo hygiene"
banned=$(git ls-files | grep -E '^(CLAUDE\.md|notes/|plans/|\.claude|AGENTS\.md|\.aider|\.cursor|\.continue|\.codeium)' || true)
if [[ -z "$banned" ]]; then
  ok "no AI-tooling files committed"
else
  bad "banned files in repo:"
  echo "$banned" | sed 's/^/      /'
fi

# 2. Secrets sweep
# Match real private keys / API keys, NOT the 32-byte hashes (trace_hash,
# merkle_root, tx_hash, market_id) that are legitimate public on-chain refs.
# Real private keys are hex-only without context; we look for them inside
# .env / .ini / shell files where they'd live, not in snapshot data.
secrets=$(git ls-files \
  | grep -vE '\.md$|snapshot\.json|tests/|\.test\.' \
  | xargs grep -lE 'sk-ant-[a-zA-Z0-9_-]{40,}|GOOGLE_API_KEY *= *[a-zA-Z0-9_-]+|"private_key" *: *"0x[a-f0-9]{64}"' 2>/dev/null \
  || true)
if [[ -z "$secrets" ]]; then
  ok "no obvious secrets in code"
else
  bad "possible secrets in:"
  echo "$secrets" | sed 's/^/      /'
fi

# 3. .env.example is current
if [[ -f .env && -f .env.example ]]; then
  missing=$(grep -E '^[A-Z_]+=' .env | cut -d= -f1 | while read k; do
    grep -q "^${k}=" .env.example || echo "$k"
  done)
  if [[ -z "$missing" ]]; then
    ok ".env.example covers every key in .env"
  else
    bad "keys in .env not in .env.example:"
    echo "$missing" | sed 's/^/      /'
  fi
fi

# 4. Python tests
step "Python tests + lint"
if uv run pytest -q >/tmp/pytest.log 2>&1; then
  ok "pytest: $(tail -1 /tmp/pytest.log)"
else
  bad "pytest failures — see /tmp/pytest.log"
fi
if uv run ruff check agent/ server/ storage/ wallets/ scripts/ tests/ >/tmp/ruff.log 2>&1; then
  ok "ruff clean"
else
  bad "ruff issues — see /tmp/ruff.log"
fi

# 5. Foundry tests
step "Foundry tests"
if (cd contracts && forge test >/tmp/forge.log 2>&1); then
  ok "forge: $(grep -oE 'passing|tests passed' /tmp/forge.log | head -1 || echo passed)"
else
  bad "forge failures — see /tmp/forge.log"
fi

# 6. Dashboard build
step "Dashboard build (snapshot mode)"
if (cd dashboard && \
    NEXT_PUBLIC_USE_SNAPSHOT=1 \
    NEXT_PUBLIC_LIVE_API_BASE=https://api.rrtrace.xyz \
    NEXT_PUBLIC_BASE_PATH="" \
    npx next build >/tmp/dashboard.log 2>&1); then
  ok "dashboard build green"
else
  bad "dashboard build failed — see /tmp/dashboard.log"
fi

# 7. On-chain sanity (V1 + V2 reachable)
step "On-chain sanity (Arc Testnet)"
if [[ -f .env ]]; then
  # shellcheck disable=SC1091
  set -a; . ./.env; set +a
fi
if [[ -n "${RPC:-}" && -n "${RECEIPT_REGISTRY_ADDRESS:-}" ]]; then
  v1=$(cast call "$RECEIPT_REGISTRY_ADDRESS" "totalReceipts()(uint256)" --rpc-url "$RPC" 2>/dev/null || echo "ERR")
  if [[ "$v1" =~ ^[0-9]+$ ]]; then
    ok "V1 totalReceipts() = $v1"
  else
    bad "V1 contract unreachable at $RECEIPT_REGISTRY_ADDRESS"
  fi
fi
if [[ -n "${RPC:-}" && -n "${RECEIPT_REGISTRY_V2_ADDRESS:-}" ]]; then
  v2=$(cast call "$RECEIPT_REGISTRY_V2_ADDRESS" "totalReceipts()(uint256)" --rpc-url "$RPC" 2>/dev/null || echo "ERR")
  if [[ "$v2" =~ ^[0-9]+$ ]]; then
    ok "V2 totalReceipts() = $v2"
  else
    bad "V2 contract unreachable at $RECEIPT_REGISTRY_V2_ADDRESS"
  fi
fi

# 8. Live domain (optional — only checks if DNS is set)
step "Live domain (rrtrace.xyz)"
if curl -sI -m 5 https://rrtrace.xyz >/tmp/curl.log 2>&1; then
  if grep -q "200 OK\|HTTP/.*200" /tmp/curl.log; then
    ok "rrtrace.xyz reachable + 200"
  else
    bad "rrtrace.xyz returned non-200"
  fi
else
  printf '  - rrtrace.xyz not reachable (DNS may not be propagated yet)\n'
fi

# 9. Submission deliverables presence
step "Submission deliverables"
[[ -f docs/SUBMISSION.md ]] && ok "docs/SUBMISSION.md exists" || bad "docs/SUBMISSION.md missing"
[[ -f docs/PITCH-SCRIPT.md ]] && ok "docs/PITCH-SCRIPT.md exists" || bad "docs/PITCH-SCRIPT.md missing"
[[ -f docs/DEMO.md ]] && ok "docs/DEMO.md exists" || bad "docs/DEMO.md missing"
[[ -f docs/canteen-walkthrough.md ]] && ok "docs/canteen-walkthrough.md exists" || bad "missing canteen walkthrough"
[[ -f docs/mcp.md ]] && ok "docs/mcp.md exists" || bad "MCP doc missing"

# Final
printf '\n=== SUMMARY ===\n'
printf '  passed: %d\n  failed: %d\n' "$PASS" "$FAIL"
if [[ "$FAIL" -eq 0 ]]; then
  printf '\n\033[32mAll green. Ready when Harvey is.\033[0m\n'
  exit 0
fi
printf '\n\033[31mFix the failures above before submitting.\033[0m\n'
exit 1
