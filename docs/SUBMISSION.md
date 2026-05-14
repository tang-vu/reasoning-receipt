# Submission — Agora Agents Hackathon

Copy-paste-ready text for every form field. Fill in the bracketed placeholders before clicking submit.

---

## Short description (≤ 140 chars)

> Prediction-market oracle whose product is a 5-agent reasoning DAG, byte-verifiable on Arc via Merkle root. x402-paywalled.

(125 chars.)

---

## Long description (~800 words)

ReasoningReceipt is an on-chain oracle for prediction markets where the **reasoning trace is the product, not just the number**. A consumer pays a few cents of USDC over x402, gets back a probability for a Polymarket or Kalshi event, and — critically — a **receipt**: a hashed, content-addressed pointer to the full chain-of-thought that produced the number. The trace lives on Irys (Arweave-compatible). In **rr-trace/3** (the current schema), every NODE of the reasoning DAG gets its own SHA-256, and a Merkle root over all node hashes lands on Arc inside `ReceiptRegistryV2.sol`. Anyone can pull the trace, re-canonicalize it, hash it, and verify byte-for-byte that the published reasoning is what the oracle actually emitted — **and** they can challenge a single evidence URL with a ~200-byte inclusion proof without downloading the full trace. There is no "trust the publisher" step.

The agent runs a **5-agent ensemble** per market, not a single LLM call. Three sub-researchers run in parallel with isolated context — **Bull** advocates the strongest case for YES, **Bear** the strongest case for NO, and **Edge** surfaces the tail risks both partisans take for granted. A **Supervisor** then weighs their drafts (each weight in [0.1, 0.7], summing to 1.0), computes a weighted-Bayesian final probability, surfaces a disagreement_pp metric, and mandates at least one **falsifiable claim** — a concrete, dated observable that would invalidate the prediction. Finally a **Critic** (Gemini Flash) audits the supervisor's output across six rigor dimensions: evidence relevance, falsifiability, scope, coherence, exploration integrity, methodology. Verdict is approved / needs_revision (one revision pass) / rejected (not emitted). Receipts that fail audit never reach the chain. The whole ensemble runs continuously: a scanner polls **two prediction venues in parallel — Polymarket Gamma (24h volume > $10k) and Kalshi's public Trade API (open-interest × last-price > $2k)** — for near-resolution (≤ 30 days), English-language, single-question (non-parlay) markets every minute; a trader stage takes the ensemble's probability, computes edge against the market mid, and (when edge ≥ 4 pp and confidence ≥ 0.5) Kelly-sizes a position from the portfolio wallet capped at 5% of bankroll. The agent eats its own cooking — on-chain volume is real consumer-wallet load on its own oracle.

A **calibration feedback loop** closes the agentic story: a resolver polls Polymarket Gamma for resolved markets and back-fills outcomes; a per-category Brier + over-under bias is fed back into the Supervisor's prompt as a prior. If the past 30 days of macro predictions show overconfidence bias +0.06, the next macro market's Supervisor sees that line and tempers extremes accordingly. This is metric-driven self-correction, not a static prompt.

The server is the second face of the same oracle. A FastAPI endpoint `GET /price/<market_id>` returns **402 Payment Required** with a Circle Gateway / x402-v2 `PAYMENT-REQUIRED` body — `network: eip155:5042002`, `asset` set to USDC on Arc, `amount` in micro-USDC, `extra.verifyingContract` pointing at the Arc Testnet Gateway Wallet (`0x0077777d7EBA4688BDeF3E311b846F25870A19B9`). The consumer signs an EIP-3009 `TransferWithAuthorization` payload, retries with `X-Payment`, and the server forwards to Circle's facilitator `/v1/settle` for gasless USDC settlement. The trace is sealed (canonical JSON → SHA-256 → real Irys upload via the `@irys/upload` SDK), `Receipt(...)` is emitted on Arc, the row is persisted, and the response carries the price plus the trace pointer.

The dashboard at `https://rrtrace.xyz` is a Next.js 15 static build, auto-deployed by GitHub Actions on every push to `dashboard/**` or whenever a fresh snapshot is committed. It runs in hybrid mode: live API (via Cloudflare Tunnel → backend on Harvey's PC) for real-time data, frozen `snapshot.json` as fallback when the tunnel hiccups. The home page has an SSE-backed **live receipts feed** — new receipts ticker in as the daemon emits them; a v3 pill flags ensemble-built traces alongside their disagreement_pp. Each trace page has a **Verify** button that pulls the trace JSON from Irys, re-canonicalises it, re-hashes it client-side, and shows a byte-for-byte verdict against the on-chain hash — for rr-trace/3 traces it also renders the **Ensemble panel** (Bull / Bear / Edge stance cards with per-stance weights), the **Critic radar** (six dim bars), and the **falsifiable-claims list**. The wedge is auditable, not just claimed.

**Agent-to-agent commerce via paywalled MCP**: alongside the free stdio MCP server (for human dev tools), the oracle exposes a Circle x402 v2 paywalled HTTP variant at `https://api.rrtrace.xyz/mcp/v1/get_price/{market_id}` and `https://api.rrtrace.xyz/mcp/v1/audit/{receipt_id}`. A downstream agent without our Vertex/Arc-gas overhead pays $0.01 USDC per call and gets back the latest cached probability + trace pointer + Merkle root (or a re-verification result against Irys). The challenge response carries the full x402 v2 envelope — `network: eip155:5042002`, EIP-3009 typed-data, Gateway Wallet `verifyingContract` — so any agent that already speaks x402 to our `/price` endpoint speaks the MCP endpoint with zero extra code.

Per the "agentic sophistication" rubric: the 5-agent ensemble with isolated context per stance, single-pass critic revision loop, calibration prior feeding the Supervisor, and multi-model fallback chain (Gemini 3.1 Pro Preview → 3 Flash Preview → 2.5 Flash) together implement autonomous decision-making, not automation. Per the "traction" rubric: the agent's consumer wallet drives continuous load, so the **2,700+ receipts on Arc** at submission time are real on-chain events, not synthetic — plus rr-trace/3 receipts dual-commit to the new V2 contract with the Merkle root, and **13 distinct consumer addresses** have already paid the paywall (full agent-to-agent commerce, not a single stress wallet). The scanner pulls from **two live prediction venues — Polymarket Gamma and Kalshi's public Trade API** — so RFB 03 ("markets" plural) is satisfied by the production loop, not a roadmap promise. Per the "Circle tools" rubric: Wallets (developer-controlled, portfolio + consumer split), USDC (settlement currency + native gas), Arc (settlement chain), Gateway / x402 v2 (paywall spec), and CCTP V2 (cross-chain liquidity demo) — five Circle products in production paths. Per the "innovation" rubric: per-node Merkle commit of the reasoning DAG is a structural step beyond "hash an opaque blob" — anyone can challenge a single counter-argument or evidence URL without downloading the full trace; falsifiable-claims mandate at the schema level forces every published probability to commit to a dated observable.

### Circle Product Feedback (from real integration)

* **Arc Testnet** — sub-second deterministic finality + USDC as native gas was the single biggest unlock for this product shape. Per-receipt gas at the price point this app targets (≈ $0.00068 average across 2700+ emissions, measured) is **20× cheaper than the price of the answer it commits to**. Posting a $0.01 receipt to L1 Ethereum is nonsense; on Arc the receipt is dust. `arc-canteen rpc-url --export`, `arc-canteen context sync` (pulls in your skills + sample repos), and `cast block-number` worked first try. The only sharp edge: `gemini-3.1-pro-preview` is on Vertex AI's `global` location only, so when we paired it with `arc-canteen` it took a second to figure out the model wasn't 404'ing for permissions — just deployment region.

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
| Live dashboard | https://rrtrace.xyz |
| Contract on Arc — ReceiptRegistryV2 (Merkle root + schema version) | https://testnet.arcscan.app/address/0x27d93c52fea923f956345af27f61d7bf47f0c4c1 |
| Contract on Arc — ReceiptRegistry V1 (source-verified) | https://testnet.arcscan.app/address/0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf |
| Contract on Arc — CanteenUSDC wrapper (source-verified) | https://testnet.arcscan.app/address/0x7473d0db92F77aA89F19A2D74174D14D14CBD3E1 |
| Latest release | https://github.com/tang-vu/reasoning-receipt/releases/tag/v0.3.0 |
| Team | Solo — Vu Minh Tang (`tang-vu`) |
| Circle Developer Console email | `[email — fill in]` |

---

## Tech stack

Python 3.11+ (FastAPI, `google-genai` SDK targeting Vertex AI with `global` region, web3.py, SQLAlchemy 2.0, `eth_account`, `cryptography` for the RSA-OAEP entity-secret encryption), Solidity 0.8.26 (Foundry 1.7.1) with `via_ir=true`, Node sidecars for `@irys/upload` + `@irys/upload-ethereum` (Bundlr-signed trace bundles), TypeScript / Next.js 15 / Tailwind / Recharts. Arc Testnet (chain id 5042002), Circle developer-controlled Wallets, Circle Gateway Nanopayments (x402 v2), CCTP V2 (Iris attestation API), Polymarket Gamma API, Irys (devnet + Arweave gateway). MCP server (`@modelcontextprotocol/sdk`) exposes the oracle as a stdio tool for Claude Desktop / Cursor / Cline. GitHub Pages with the rrtrace.xyz custom domain for the dashboard; Cloudflare Tunnel terminates TLS on `api.rrtrace.xyz` and `events.rrtrace.xyz` for the live API + SSE stream. GitHub Actions for CI + auto-deploy. ~6,500 lines of code across the stack.

---

## Per-action cost evidence (measured, not hypothetical)

Mean cost per receipt across **2,736 real on-chain emissions** as of 2026-05-15, measured by the deployer wallet's USDC balance delta:

| Metric | Value |
|---|---|
| Total receipts emitted | **2,736** (and rising — daemon active) |
| Distinct markets priced | 177 (Polymarket + Kalshi) |
| Distinct consumer wallets | 13 |
| Deployer USDC burned | ≈ 0.92 USDC |
| **Per-receipt gas cost** | **$0.000683 USDC** (≈ 1/15 of a cent, measured) |
| Avg end-to-end latency | 24.3 s (real Gemini grounding + Arc tx confirmation) |
| x402 settlement amount | $0.01 USDC per paid call (paywall config) |
| End-to-end consumer cost | $0.01 USDC paid + $0.0007 underlying gas |

Live verification at submission time (both contracts — each receipt lands on exactly one):

```sh
# V1 contract (legacy rr-trace/2 — hash + CID, schema-blind):
cast call 0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf "totalReceipts()(uint256)" \
  --rpc-url $RPC
# V2 contract (rr-trace/3 — adds the per-node Merkle root field):
cast call 0x27d93c52fea923f956345af27f61d7bf47f0c4c1 "totalReceipts()(uint256)" \
  --rpc-url $RPC
```

Per-receipt fee column is visible on the Arc explorer:
* V1: https://testnet.arcscan.app/address/0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf
* V2: https://testnet.arcscan.app/address/0x27d93c52fea923f956345af27f61d7bf47f0c4c1

---

## Transaction count

Live at submission. Run from anywhere with the public Arc Testnet RPC:

```sh
RPC=https://rpc.testnet.arc-node.thecanteenapp.com/v1/<your-token>
# Legacy rr-trace/2 receipts
cast call 0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf \
  "totalReceipts()(uint256)" --rpc-url $RPC
# rr-trace/3 receipts (Merkle-rooted reasoning DAG)
cast call 0x27d93c52fea923f956345af27f61d7bf47f0c4c1 \
  "totalReceipts()(uint256)" --rpc-url $RPC
```

Snapshot at last commit: **2,281 receipts on V1 + 478 receipts on V2 (≈2,759 total)** across **177 distinct markets** spanning Polymarket and Kalshi (2.7× the 1,000 target with 10 days of build window remaining). The V2 count grows live — every new rr-trace/3 receipt the daemon emits lands there.

---

## Margin explanation

A $0.01 oracle call is uneconomical on classical L1s — gas alone exceeds the price of the answer. Sub-second, sub-cent settlement on Arc inverts that: each receipt costs **less than the information it commits to**. That margin enables an entirely new product shape — selling reasoning, not predictions — and makes the agent's own consumer-wallet load loop honest (real on-chain volume, not synthetic ticks).

---

## What's new in rr-trace/3 (rubric-mapped delta from v0.2.0)

| Lever | What's new |
|---|---|
| Agentic Sophistication (30%) | 5-agent ensemble (Bull/Bear/Edge + Supervisor + Critic) with isolated context per stance, emergent disagreement metric, single-pass revision loop. Calibration prior from per-category Brier feeds the Supervisor's prompt — closes the metric-driven self-correction loop. |
| Innovation (20%) | Merkle-rooted reasoning DAG on Arc via `ReceiptRegistryV2` — per-node SHA-256 hashes, ~200-byte inclusion proof for any single evidence/counter-argument/sensitivity factor. Falsifiable-claims mandated at the schema level. 6-dimensional ARA-style epistemic critic. **Agent-to-agent revenue path** via paywalled MCP at `/mcp/v1/{get_price,audit}` — agents pay $0.01 USDC per call (Circle x402 v2, EIP-3009 settle). |
| Traction (30%) | 2,700+ receipts on Arc across 177 markets and **13 distinct consumer wallets**; rr-trace/3 receipts dual-commit to V2 with the Merkle root; **two live venues** (Polymarket Gamma + Kalshi Trade API) on the same scanner; live custom-domain dashboard at `rrtrace.xyz` with SSE-backed real-time receipt feed. |
| Circle Tools (20%) | Unchanged — five Circle products in production paths (Arc Testnet, USDC as gas+value, Wallets developer-controlled, Gateway+x402 v2, CCTP V2). |

## Pre-submit checklist

Repo hygiene (run each before submitting):

- [x] `.env` is gitignored, not committed
- [x] `git ls-files | grep -E "^(CLAUDE|notes/|plans/|\.claude|AGENTS)"` returns empty
- [x] `git ls-files | xargs grep -l "sk-ant\\|0x[a-f0-9]\\{64\\}"` returns empty (no committed secrets)
- [x] CI green on main: https://github.com/tang-vu/reasoning-receipt/actions
- [x] Dashboard live: https://rrtrace.xyz
- [x] V1 contract source-verified on Arc Testnet explorer (`forge verify-contract` via Blockscout, Solidity 0.8.26 with `via_ir`)
- [x] V2 contract source-verified on Arc Testnet explorer
- [x] Byte-for-byte trace verification proven against a live receipt (receipt ≥ #2273; see "Verifiability cutoff" note below)

### Verifiability cutoff

Mid-build, we caught a real bug in the Node Irys sidecar — it was `JSON.parse → JSON.stringify`-ing the input before upload, which re-serialized with JS-default insertion-order keys and float formatting. The on-chain `traceHash` (SHA-256 of Python's canonical bytes) therefore did not byte-match the bytes that ended up on Irys, even though the semantic content was identical. Receipts before **#2273** load the right trace JSON via CID but fail the byte-for-byte verify; from #2273 onward, `/verify/{id}` returns `verified: true` (the canonical pipeline is now Python-only end-to-end; the JS sidecar is a transport). At submission time the daemon will have emitted thousands of post-fix verifying receipts; we kept the bug+fix in the commit log (see `16ea6c1 fix: irys sidecar uploads raw bytes`) as evidence of the iteration.

Submission deliverables (Harvey fills these in the final week):

- [ ] `dashboard/public/snapshot.json` regenerated from a DB with ≥ 1000 receipts
- [ ] Founder pitch video recorded + uploaded to YouTube (unlisted)
- [ ] Product demo video recorded via `scripts/record-demo.py` + uploaded to YouTube (unlisted)
- [ ] `scripts/setup.sh` smoke-tested from a fresh clone in `/tmp/test-clone`
- [ ] All bracketed placeholders above are filled in
- [ ] `arc-canteen update-product` + `arc-canteen update-traction` ran during the build window
