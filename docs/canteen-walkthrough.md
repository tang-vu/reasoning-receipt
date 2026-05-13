# Canteen Walkthrough — Parts 0 / 1 / 2 completion log

Concrete on-chain evidence that we completed each part of the recommended Canteen / Arc / Circle Agent Stack walkthrough.

## Part 0 — Arc-Canteen CLI

| Step | Status | Evidence |
|---|---|---|
| Install CLI | ✅ | `uv tool install git+https://github.com/the-canteen-dev/ARC-cli` |
| `arc-canteen login` | ✅ | profile `tang-vu` on the dashboard |
| `arc-canteen rpc-url --export` | ✅ | `$RPC` populated; verified live with `cast block-number` |
| `arc-canteen context sync` | ✅ | `~/.arc-canteen/context/` synced (docs + 5 sample repos + Circle skills) |
| `arc-canteen update-product` | ✅ | ran 2× during build window (May 11, May 13) |
| `arc-canteen update-traction` | ✅ | submitted with measured metrics (1500+ receipts, $0.000683/tx, 5/7 Circle products) |
| Use testnet RPC | ✅ | **1,500+ paid receipts** emitted via the Canteen-hosted RPC |
| `arc-canteen submit-puzzle` | ⏳ | active puzzle status checked, no submission yet |

## Part 1 — cUSDC wrapper on Arc

> "Make a canteenUSDC wrapper around USDC. Build a simple CLI to wrap or unwrap USDC using this context. Write the wrap/unwrap contract as well as the ERC20 CA to testnet with the RPC. **Make sure to verify the contract.**"

| Item | Detail |
|---|---|
| Contract | [`contracts/src/CanteenUSDC.sol`](../contracts/src/CanteenUSDC.sol) |
| Tests | [`contracts/test/CanteenUSDC.t.sol`](../contracts/test/CanteenUSDC.t.sol) — **10/10 passing** including fuzz |
| Deploy script | [`contracts/script/DeployCanteenUSDC.s.sol`](../contracts/script/DeployCanteenUSDC.s.sol) |
| CLI | [`scripts/cusdc-cli.py`](../scripts/cusdc-cli.py) — `wrap`, `unwrap`, `balance` subcommands |
| **Deployed address** | `0x7473d0db92F77aA89F19A2D74174D14D14CBD3E1` |
| Underlying USDC | `0x3600000000000000000000000000000000000000` (Arc Testnet) |
| **Source-verified** | ✅ `is_verified: True` — https://testnet.arcscan.app/address/0x7473d0db92F77aA89F19A2D74174D14D14CBD3E1 |

### Roundtrip executed live

```
balance BEFORE   : USDC 59.923405, cUSDC 0.000000
approve tx       : 0xbfa5e3e99f4aebf70f8082897aff275c6821a3a5b943fb96aeef7f35192e7893
wrap tx          : 0xad6aebaf27a481618d0d73d28cd06078a236e613af2a4997929fbb59268c1124  (block 42025748)
balance AFTER wrap: USDC 58.920120, cUSDC 1.000000   (supply 1.000000)
unwrap tx        : 0xb57bd6eff8786593b8bb655d2df61faed81501edd878b8a45498fc8b2dbd5608  (block 42025773)
balance AFTER    : USDC 59.918209, cUSDC 0.000000
```

Net gas across all 3 transactions: **0.005196 USDC** (~$0.0017 per tx average). cUSDC was minted 1:1 and burned 1:1 against the underlying — no fees, no slippage.

Run it yourself once the repo is cloned + `.env` is populated:

```bash
uv run python -m scripts.cusdc-cli balance
uv run python -m scripts.cusdc-cli wrap 1.0
uv run python -m scripts.cusdc-cli unwrap 1.0
```

## Part 2 — Paywalled merchant on the Circle Agent stack

> "Build a merchant on Circle's Agent stack! Our merchant says 'Hello world' on a paywalled /hello-world endpoint on Arc testnet"

We over-shot the "hello world" prompt — the merchant is the full ReasoningReceipt oracle:

| Item | Detail |
|---|---|
| Paywalled endpoint | `GET /price/{market_id}` on the FastAPI server |
| x402 version | **v2 spec-compliant** (PAYMENT-REQUIRED header, `eip155:5042002` CAIP-2, EIP-3009 typed data, Gateway Wallet `verifyingContract`) |
| Facilitator | Circle Gateway: `https://gateway-api-testnet.circle.com/v1/settle` |
| Underlying chain | Arc Testnet (sub-second finality, USDC-as-gas) |
| Wallets | Circle developer-controlled (provisioned via API in `scripts/circle-setup.py` — entity secret RSA-OAEP encrypted, walletSet + 2 wallets in one Python call) |

For the `circle` CLI / agent-type wallet variant explicitly suggested in the slides (`circle wallet create --type agent`), see the open task in `notes/state.md` — it's a separate wallet flow from the developer-controlled wallets we built the receipt path on, and requires interactive email+OTP login.

## Beyond the walkthrough

We also shipped pieces not on the suggested path that strengthen the same thesis:

- **CCTP V2 demo** ([`scripts/cctp-demo.py`](../scripts/cctp-demo.py)) — 1 USDC Sepolia → Arc, end-to-end ~60s. Tx hashes in `docs/SUBMISSION.md`.
- **Real Irys upload** ([`services/irys/upload.js`](../services/irys/upload.js)) — Bundlr-signed bundles via Node sidecar. Trace JSON is publicly retrievable from the Irys gateway and byte-matches the on-chain hash.
- **Researcher + Critic two-agent loop** ([`agent/critic.py`](../agent/critic.py)) — Gemini Pro drafts, Gemini Flash audits across 5 categories (fabrication, strawmen, calibration, sensitivity, internal consistency), Pro revises if any fail. Trace records the critic review.
- **Backtest** ([`agent/resolver.py`](../agent/resolver.py) + [`agent/calibration.py`](../agent/calibration.py)) — Polymarket resolution back-fill + Brier score + 10-bucket reliability curve, surfaced at `/calibration`.
- **MCP server** ([`services/mcp/server.js`](../services/mcp/server.js)) — oracle exposed to Claude Desktop / Cursor / Cline as a first-class tool. See [`docs/mcp.md`](mcp.md).
