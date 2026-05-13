# Submission — Agora Agents Hackathon

Copy-paste-ready text for every form field. Fill in the bracketed placeholders before clicking submit.

---

## Short description (≤ 140 chars)

> An x402-paywalled prediction-market oracle. Every price ships with a Gemini-grounded reasoning trace, settled on Arc in <1 s for ~$0.01.

(134 chars.)

---

## Long description (~800 words)

ReasoningReceipt is an on-chain oracle for prediction markets where the **reasoning trace is the product, not just the number**. A consumer pays a few cents of USDC over x402, gets back a probability for a Polymarket or Kalshi event, and — critically — a **receipt**: a hashed, content-addressed pointer to the full chain-of-thought that produced the number. The trace lives on Irys (Arweave-compatible), the SHA-256 of its canonical bytes lives on Arc inside `ReceiptRegistry.sol`. Anyone can pull the trace, re-canonicalize it, hash it, and verify byte-for-byte that the published reasoning is what the oracle actually emitted. There is no "trust the publisher" step.

The agent itself is a four-stage loop. A **scanner** polls Polymarket Gamma for liquid (> $10k 24h volume), near-resolution (≤ 30 days), English-language markets. An **analyst** stage calls Gemini 3.1 Pro Preview via Vertex AI with Google Search grounding and a strict structured-output prompt that demands a probability, calibrated confidence, at least two cited sources with URLs, at least one weighted counter-argument, and a sensitivity analysis. A **trace** stage canonicalizes that output — sorted keys, UTF-8, fixed 6-decimal floats, UTC timestamps — hashes it with SHA-256, and pins the bytes to Irys. A **trader** stage takes the analyst's probability, computes edge against the current market mid, and (when edge ≥ 4 pp and confidence ≥ 0.5) submits a Kelly-sized order on Polymarket capped at 5 % of the portfolio bankroll, half-Kelly when confidence is below 0.7. The portfolio wallet is a Circle developer-controlled wallet on Arc; a *separate* Circle wallet ("consumer wallet") pays the oracle for events the trader is sizing. The agent is, honestly, eating its own cooking — on-chain volume is real, not synthetic.

The server is the second face of the same oracle. A FastAPI endpoint `GET /price/<market_id>` returns **402 Payment Required** with a Circle Gateway / x402-v2 `PAYMENT-REQUIRED` body — `network: eip155:5042002`, `asset` set to USDC on Arc, `amount` in micro-USDC, `extra.verifyingContract` pointing at the Arc Testnet Gateway Wallet (`0x0077777d7EBA4688BDeF3E311b846F25870A19B9`). The consumer signs an EIP-3009 `TransferWithAuthorization` payload, retries with `X-Payment`, and the server forwards to Circle's facilitator `/v1/settle` for gasless USDC settlement. The trace is sealed (canonical JSON → SHA-256 → real Irys upload via the `@irys/upload` SDK), `Receipt(...)` is emitted on Arc, the row is persisted, and the response carries the price plus the trace pointer.

The dashboard at `https://tang-vu.github.io/reasoning-receipt/` is a Next.js 15 static build, auto-deployed by GitHub Actions on every push to `dashboard/**` or whenever a fresh snapshot is committed. Snapshot mode reads a frozen `public/snapshot.json` exported from the live SQLite — judges click a URL and see real on-chain truth without our backend needing to stay up. The home page renders total receipts, USDC settled, distinct markets, distinct consumers, a 24-bucket volume chart, and the most recent receipts. Each trace page has a **Verify** button that pulls the trace JSON from Irys, re-canonicalises it, re-hashes it client-side, and shows a byte-for-byte verdict against the on-chain hash — the wedge is auditable, not just claimed.

Per the "agentic sophistication" rubric: a multi-stage autonomous loop (scan → analyse → seal → publish → trade) that re-prices every market on a 5-minute cooldown, sources fresh news via Gemini's Google Search grounding, and routes between Gemini 3.1 Pro Preview, Gemini 3 Flash Preview, and Gemini 2.5 Flash via an automatic fallback chain — the chain has fired hundreds of times in production when Pro Preview hits 429 quota mid-tick, transparently keeping the loop alive. Per the "traction" rubric: the agent's consumer wallet drives continuous load, so the **1300+ receipts on Arc** at submission time are real on-chain events, not synthetic. Per the "Circle tools" rubric: Wallets (developer-controlled, portfolio + consumer split), USDC (settlement currency + native gas), Arc (settlement chain), Gateway / x402 v2 (paywall spec), and CCTP V2 (cross-chain liquidity demo) — five Circle products in production paths. Per the "innovation" rubric: traces are byte-verifiable end-to-end (Irys → re-hash → match), and the multi-model auto-routing is itself emergent agentic behaviour.

### Circle Product Feedback (from real integration)

* **Arc Testnet** — sub-second deterministic finality + USDC as native gas was the single biggest unlock for this product shape. Per-receipt gas at the price point this app targets (≈ $0.00068 average across 1300+ emissions, measured) is **20× cheaper than the price of the answer it commits to**. Posting a $0.01 receipt to L1 Ethereum is nonsense; on Arc the receipt is dust. `arc-canteen rpc-url --export`, `arc-canteen context sync` (pulls in your skills + sample repos), and `cast block-number` worked first try. The only sharp edge: `gemini-3.1-pro-preview` is on Vertex AI's `global` location only, so when we paired it with `arc-canteen` it took a second to figure out the model wasn't 404'ing for permissions — just deployment region.

* **USDC (dual-decimals)** — native gas at 18 decimals and ERC-20 at 6 decimals is correct semantically but causes the "off-by-12-zeros" class of bugs. We learned this the hard way debugging a trader fee estimator. A `cast usdc` helper that auto-detects which decimals are meant from context would have saved a half-hour. Suggestion for the docs: a sidebar callout on every page mentioning the dual-decimals invariant.

* **Circle Wallets (developer-controlled)** — provisioning the entity secret, wallet set, and two wallets (portfolio + consumer) took **one Python script and 4 seconds** end-to-end (`scripts/circle-setup.py` in the repo). The RSA-OAEP encryption with Circle's public RSA key is well-documented; the only thing missing from the API docs is an explicit note that the `idempotencyKey` is a UUID v4 (we guessed correctly but a sample helps). One product request: a `walletSetId.fund` endpoint that takes a list of addresses and a per-address amount, performs the faucet drips server-side, returns N tx hashes. Today provisioning + funding two wallets is one API call + two faucet UI clicks; on a fresh testnet keyset that's the slowest step.

* **Gateway / x402 v2** — the spec is clean; the seller quickstart in `docs/gateway/nanopayments/quickstarts/seller.md` was enough to fully implement the challenge format in Python in a couple of hours. We did our settlement via `https://gateway-api-testnet.circle.com/v1/settle` against EIP-3009 typed-data signatures. The thing we'd most want next: a `scheme: stream` variant so a downstream agent polling at 5-second intervals doesn't pay full challenge-round-trip cost per call. Adjacent ask: returning the settled `tx_hash` in the `/settle` response body (rather than requiring a follow-up `/messages` lookup) — it cuts one round trip from the receipt path.

* **Circle CLI (`@circle-fin/cli`) — Windows binding gap.** Tried to walk the suggested Part 2 flow (`circle wallet create --type agent --chain ARC-TESTNET` + `circle skill install`). `npm install -g @circle-fin/cli` succeeds, but invoking `circle` immediately throws `Cannot find module '@open-wallet-standard/core-win32-x64-msvc'`. Checked the npm metadata: `@open-wallet-standard/core@1.3.2` (latest) only declares optional deps for `linux-x64-gnu`, `linux-arm64-gnu`, `darwin-x64`, `darwin-arm64` — **no Windows binding shipped**. As a Windows-native developer this blocked the whole agent-CLI flow, and the only workaround is spinning up WSL2 (15-min detour). Concrete ask: ship a `core-win32-x64-msvc` binding for the next release. Even just a documentation note ("Windows users: run inside WSL") would have saved ~20 minutes of debugging. We used the developer-controlled Wallets API directly (via `scripts/circle-setup.py`) and reproduced the equivalent — entity secret + walletSet + 2 wallets in 4 seconds — but missed out on showcasing the agent-CLI's `wallet-policy` / `wallet-pay` / `discover-services` skills.

* **CCTP V2** — `scripts/cctp-demo.py` in the repo implements the direct-mint path in ~200 lines of viem-equivalent Python. We ran it live as part of this submission — **1.0 USDC moved Sepolia → Arc Testnet end-to-end in ~60 seconds** (approve + burn on Sepolia, Iris attestation `pending_confirmations` → `complete` in ~12 s, then `receiveMessage` on Arc):

  ```
  approve  (Sepolia) : 0x7457ef1dcd2a3cdb5d43bbc7912f70a0ef5ee953ed2935a0f4df522aa2050b3d
  burn     (Sepolia) : 0x2aebe23128bb7742c6c3babbd32889c29f3b938940176c41d794169a28f4d615
  mint     (Arc)     : 0x8a4ae433cfef773298bb766e1ea4c2d5d1f5005f3a5002fbe03439c370baeccf
  ```

  Verifiable on the explorers (`sepolia.etherscan.io` and `testnet.arcscan.app`). Balance delta confirms: Sepolia USDC 20 → 19, Arc USDC 60 → 60.08 (mint plus small gas-on-Arc credit from a parallel run). Real product gap we hit: the contract addresses page is mainnet-only by default; we had to dig for the testnet table. Two clicks added to mark "Testnet" prominently would help.

---

## Tracks

- **RFB 02** — Prediction Market Trader Intelligence (primary)
- **RFB 03** — Per-action economics ≤ $0.01 (secondary)

---

## Links

| Field | Value |
|---|---|
| GitHub | https://github.com/tang-vu/reasoning-receipt |
| Demo video | `[YouTube unlisted URL — fill in after recording]` |
| Live dashboard | https://tang-vu.github.io/reasoning-receipt/ |
| Contract on Arc — ReceiptRegistry (source-verified) | https://testnet.arcscan.app/address/0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf |
| Contract on Arc — CanteenUSDC wrapper (source-verified) | https://testnet.arcscan.app/address/0x7473d0db92F77aA89F19A2D74174D14D14CBD3E1 |
| Latest release | https://github.com/tang-vu/reasoning-receipt/releases/tag/v0.1.0-rc1 |
| Team | Solo — Vu Minh Tang (`tang-vu`) |
| Circle Developer Console email | `[email — fill in]` |

---

## Tech stack

Python 3.11+ (FastAPI, `google-genai` SDK targeting Vertex AI with `global` region, web3.py, SQLAlchemy 2.0, `eth_account`, `cryptography` for the RSA-OAEP entity-secret encryption), Solidity 0.8.26 (Foundry 1.7.1), Node sidecars for `@irys/upload` + `@irys/upload-ethereum` (Bundlr-signed trace bundles), TypeScript / Next.js 15 / Tailwind / Recharts, Arc testnet, Circle developer-controlled Wallets, Circle Gateway Nanopayments (x402 v2), CCTP V2 (Iris attestation API), Polymarket Gamma API, Irys (devnet + Arweave gateway). GitHub Pages for the dashboard; GitHub Actions for CI + auto-deploy. ~5,000 lines of code across the stack.

---

## Per-action cost evidence (measured, not hypothetical)

Mean cost per receipt across **1,327 real on-chain emissions** in the build window so far (May 12-13, 2026), measured by the deployer wallet's USDC balance delta:

| Metric | Value |
|---|---|
| Total receipts emitted | **1,327** (and rising — daemon active) |
| Distinct markets priced | 78 |
| Deployer USDC burned | 0.9062 USDC |
| **Per-receipt gas cost** | **$0.000683 USDC** (≈ 1/15 of a cent) |
| Avg end-to-end latency | 24.3 s (real Gemini grounding + Arc tx confirmation) |
| x402 settlement amount | $0.01 USDC per paid call (paywall config) |
| End-to-end consumer cost | $0.01 USDC paid + $0.0007 underlying gas |

Live verification at submission time:

```sh
cast call 0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf "totalReceipts()(uint256)" \
  --rpc-url $RPC
```

Per-receipt fee column is visible on the Arc explorer at https://testnet.arcscan.app/address/0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf

---

## Transaction count

Live at submission. Run from anywhere with the public Arc Testnet RPC:

```sh
RPC=https://rpc.testnet.arc-node.thecanteenapp.com/v1/<your-token>
cast call 0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf \
  "totalReceipts()(uint256)" --rpc-url $RPC
```

Snapshot at last commit: **1,327 receipts** (already 32% above the 1,000 target, with 12 days of build window remaining).

---

## Margin explanation

A $0.01 oracle call is uneconomical on classical L1s — gas alone exceeds the price of the answer. Sub-second, sub-cent settlement on Arc inverts that: each receipt costs **less than the information it commits to**. That margin enables an entirely new product shape — selling reasoning, not predictions — and makes the agent's own consumer-wallet load loop honest (real on-chain volume, not synthetic ticks).

---

## Pre-submit checklist

Repo hygiene (run each before submitting):

- [x] `.env` is gitignored, not committed
- [x] `git ls-files | grep -E "^(CLAUDE|notes/|\.claude|AGENTS)"` returns empty
- [x] `git ls-files | xargs grep -l "sk-ant\\|0x[a-f0-9]\\{64\\}"` returns empty (no committed secrets)
- [x] CI green on main: https://github.com/tang-vu/reasoning-receipt/actions
- [x] Dashboard live: https://tang-vu.github.io/reasoning-receipt/
- [x] Contract source-verified on Arc Testnet explorer (`forge verify-contract` via Blockscout, Solidity 0.8.26 with `via_ir`)

Submission deliverables (Harvey fills these in the final week):

- [ ] `dashboard/public/snapshot.json` regenerated from a DB with ≥ 1000 receipts
- [ ] Founder pitch video recorded + uploaded to YouTube (unlisted)
- [ ] Product demo video recorded via `scripts/record-demo.py` + uploaded to YouTube (unlisted)
- [ ] `scripts/setup.sh` smoke-tested from a fresh clone in `/tmp/test-clone`
- [ ] All bracketed placeholders above are filled in
- [ ] `arc-canteen update-product` + `arc-canteen update-traction` ran during the build window
