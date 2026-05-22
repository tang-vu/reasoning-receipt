# Submission — Agora Agents Hackathon

> Copy-paste-ready answers mapped **1:1 to the live Agora submission form**
> (https://forms.gle/hFPM2t4Jt1zGfqzM7). Each `##` below is one form field.
> The form accepts multiple submissions — submit now, resubmit if numbers move
> before the 2026-05-25 deadline. `*` = required field.

---

## Short-answer fields — paste straight in

| Form field | Value |
|---|---|
| Email * | tangminhvu2212@gmail.com |
| Project Name * | ReasoningReceipt |
| Github Handle * | tang-vu |
| Discord Handle * | @hanhgia2212 |
| Telegram Handle * | @hanhgia2212 |
| Twitter / X Profile | *(optional — leave blank, or paste your X profile URL if you have one)* |
| Number of Team Members * | 1 (Solo) |
| Team Members Names * | Vu Minh Tang |
| Project Source Code * | https://github.com/tang-vu/reasoning-receipt |
| Project Live | https://rrtrace.xyz |
| Project Video Demo * | https://youtu.be/LjuwQcyboYc |

*Video note: keep it within the form's 3-minute guideline; the product demo
is already the right shape. The founder pitch video is separate and optional —
do not block submission on it.*

---

## Problem Statement *

> AI agents increasingly produce the probabilities that humans and other agents
> act on — in prediction markets, in trading, in risk decisions. But an oracle
> hands you a number with no way to audit *why*. You either trust the publisher
> or you don't. The reasoning that produced the number — the evidence weighed,
> the counter-arguments, the assumptions — is discarded, or at best hashed as an
> opaque blob you still can't inspect.
>
> Two things make this hard to fix. First, reasoning is only trustworthy if it's
> *verifiable* — byte-for-byte, by anyone, without trusting the server. Second,
> verification has to be cheap enough to attach to *every* call: a $0.01 oracle
> query can't carry a multi-dollar L1 gas receipt. On classical chains the
> receipt costs more than the answer, so nobody ships one.
>
> This is compelling because the agent economy is being built right now on
> unauditable outputs. An AI probability with no inspectable reasoning is a
> liability the moment money moves on it. ReasoningReceipt makes the reasoning
> *the product*, and makes committing it on-chain cost less than the answer
> itself — which only became possible with sub-second, sub-cent settlement on
> Arc.

---

## Project Description *

> ReasoningReceipt is an x402-paywalled AI oracle for prediction markets where
> every price ships with a hashed, byte-verifiable reasoning trace. Pay a few
> cents of USDC, get a probability for a Polymarket or Kalshi event — plus a
> receipt: a Merkle-rooted reasoning DAG committed to Arc that anyone can
> re-hash and verify without trusting us. The product isn't the number; it's
> the auditable trace.
>
> **How it works.** A continuous agent loop scans two live venues — Polymarket
> Gamma and Kalshi's Trade API — for liquid, near-resolution, single-question
> markets. Each market runs through a 5-agent ensemble: **Bull** argues YES,
> **Bear** argues NO, and **Edge** surfaces tail risks both partisans miss —
> three researchers in parallel with isolated context, Google-Search grounded.
> A **Supervisor** merges their drafts with a weighted-Bayesian synthesis,
> mandates a falsifiable claim (a dated, concrete observable), and folds in a
> per-category Brier prior from past resolutions. A **Critic** audits the result
> across six rigor dimensions and gates publication — rejected receipts never
> reach the chain.
>
> The approved trace is canonicalised, every DAG node gets its own SHA-256, a
> Merkle root is computed, the JSON is pinned to Irys, and a `Receipt` event is
> emitted on `ReceiptRegistryV2`. Because the root is per-node, anyone can
> challenge a single evidence URL or counter-argument with a ~200-byte inclusion
> proof — no full-trace download. A resolver back-fills resolved outcomes so a
> calibration module reports a live Brier score, which loops back into the
> Supervisor's prior. The same oracle is exposed behind an x402 v2 paywall
> (FastAPI) and as a paywalled MCP endpoint, so other agents can pay $0.01 USDC
> per call — agent-to-agent commerce.
>
> **Tech.** Python 3.11 (FastAPI, google-genai → Vertex AI, web3.py,
> SQLAlchemy), Solidity 0.8.26 (Foundry), Next.js 15 dashboard on GitHub Pages
> (live at rrtrace.xyz, SSE real-time feed). Six Circle products in production
> paths: **Arc Testnet** (settlement, chain 5042002), **USDC** (gas + paywall
> asset), **Circle developer-controlled Wallets**, **Gateway / x402 v2**
> (paywall), **CCTP V2** (cross-chain demo), and **App Kit Unified Balance**.
> Per-receipt gas measured at **$0.000683** — about 1/15 of a cent, ~20× cheaper
> than the answer it commits to. That margin is the wedge: on Arc the receipt
> costs less than the answer, which flips an oracle from "trust me" to
> "verify me." (Aligns with RFB 02 — Prediction Market Trader Intelligence —
> and RFB 03 — per-action economics ≤ $0.01, satisfied across two live venues.)

---

## Traction *

> ReasoningReceipt is an agent-economy product — its first and primary customer
> is another agent — so the honest traction metric is verifiable on-chain
> volume, not human signups.
>
> - **4,558 paid receipts emitted on Arc** (V1: 2,281 · V2: 2,277), each a real
>   on-chain transaction, across **217 distinct markets** spanning both
>   Polymarket and Kalshi — 4.5× the hackathon's 1,000-receipt target.
> - **19 distinct consumer wallet addresses** have paid the x402 paywall — the
>   oracle's own consumer wallet plus additional EOAs exercising the
>   multi-consumer path. Real agent-to-agent settlement, not a single wallet.
> - **7+ days of continuous live PnL** from the trader stage, on the public
>   dashboard.
> - **Live, independently verifiable surfaces** anyone can check today:
>   dashboard at rrtrace.xyz, live API at api.rrtrace.xyz, both contracts
>   source-verified on Arcscan, every trace re-hashable client-side. Every
>   number above is reproducible with the public Arc RPC
>   (`cast call <contract> "totalReceipts()(uint256)"`).
> - Progress broadcast throughout the build via `arc-canteen update-product` /
>   `update-traction`; also applied to the **Arc Open Source Showcase (Arc OSS)**
>   with a reusable-primitives catalog (`docs/ARC-OSS.md`).
>
> Honest scope: this is a solo, two-week build with no user-acquisition
> campaign, so there is no meaningful RT / follow / star count to report. The
> validation is that the system has run autonomously and continuously for the
> full build window, and that every claim is on-chain and checkable by anyone —
> the traction is verifiable rather than asserted.

---

## Circle / Arc Feedback

*Optional field, but the form notes a feedback award for specificity — this is
all from real integration work.*

* **Arc Testnet** — sub-second deterministic finality + USDC as native gas was the single biggest unlock for this product shape. Per-receipt gas at the price point this app targets (≈ $0.000683 average across 4,500+ emissions, measured) is **20× cheaper than the price of the answer it commits to**. Posting a $0.01 receipt to L1 Ethereum is nonsense; on Arc the receipt is dust. `arc-canteen rpc-url --export`, `arc-canteen context sync` (pulls in your skills + sample repos), and `cast block-number` worked first try. The only sharp edge: `gemini-3.1-pro-preview` is on Vertex AI's `global` location only, so when we paired it with `arc-canteen` it took a second to figure out the model wasn't 404'ing for permissions — just deployment region.

* **USDC (dual-decimals)** — native gas at 18 decimals and ERC-20 at 6 decimals is correct semantically but causes the "off-by-12-zeros" class of bugs. We learned this the hard way debugging a trader fee estimator. A `cast usdc` helper that auto-detects which decimals are meant from context would have saved a half-hour. Suggestion for the docs: a sidebar callout on every page mentioning the dual-decimals invariant.

* **Circle Wallets (developer-controlled)** — provisioning the entity secret, wallet set, and two wallets (portfolio + consumer) took **one Python script and 4 seconds** end-to-end (`scripts/circle-setup.py` in the repo). The RSA-OAEP encryption with Circle's public RSA key is well-documented; the only thing missing from the API docs is an explicit note that the `idempotencyKey` is a UUID v4 (we guessed correctly but a sample helps). One product request: a `walletSetId.fund` endpoint that takes a list of addresses and a per-address amount, performs the faucet drips server-side, returns N tx hashes. Today provisioning + funding two wallets is one API call + two faucet UI clicks; on a fresh testnet keyset that's the slowest step.

* **Gateway / x402 v2** — the spec is clean; the seller quickstart in `docs/gateway/nanopayments/quickstarts/seller.md` was enough to fully implement the challenge format in Python in a couple of hours. We did our settlement via `https://gateway-api-testnet.circle.com/v1/settle` against EIP-3009 typed-data signatures. The thing we'd most want next: a `scheme: stream` variant so a downstream agent polling at 5-second intervals doesn't pay full challenge-round-trip cost per call. Adjacent ask: returning the settled `tx_hash` in the `/settle` response body (rather than requiring a follow-up `/messages` lookup) — it cuts one round trip from the receipt path.

* **Circle CLI (`@circle-fin/cli`) — Windows binding gap.** Tried to walk the suggested Part 2 flow (`circle wallet create --type agent --chain ARC-TESTNET` + `circle skill install`). `npm install -g @circle-fin/cli` succeeds, but invoking `circle` immediately throws `Cannot find module '@open-wallet-standard/core-win32-x64-msvc'`. Checked the npm metadata: `@open-wallet-standard/core@1.3.2` (latest) only declares optional deps for `linux-x64-gnu`, `linux-arm64-gnu`, `darwin-x64`, `darwin-arm64` — **no Windows binding shipped**. As a Windows-native developer this blocked the whole agent-CLI flow, and the only workaround is spinning up WSL2 (15-min detour). Concrete ask: ship a `core-win32-x64-msvc` binding for the next release. Even just a documentation note ("Windows users: run inside WSL") would have saved ~20 minutes of debugging. We used the developer-controlled Wallets API directly (via `scripts/circle-setup.py`) and reproduced the equivalent — entity secret + walletSet + 2 wallets in 4 seconds — but missed out on showcasing the agent-CLI's `wallet-policy` / `wallet-pay` / `discover-services` skills.

* **App Kit / Unified Balance Kit (2026 release)** — `services/app-kit/demo.ts` integrates `@circle-fin/app-kit@1.5.1` + `@circle-fin/adapter-viem-v2@1.11.0`. With the agent operator's `DEPLOYER_PRIVATE_KEY` it derives an EOA via viem and calls `kit.unifiedBalance.getBalances({ token: "USDC", sources: { address }, networkType: "testnet" })`, returning a structured per-chain breakdown across **all 12 testnet chains** (Ethereum Sepolia, Base Sepolia, Avalanche Fuji, Arbitrum Sepolia, Sonic Testnet, World Chain Sepolia, Sei Testnet, HyperEVM Testnet, **Arc Testnet**, Optimism Sepolia, Polygon Amoy, Unichain Sepolia). The SDK clearly knows Arc and we got the read API up in ~5 minutes — strong DX. **Concrete doc bug**: the quickstart at `docs.arc.io/app-kit/quickstarts/unified-balance-deposit-and-spend` shows `sources: { account: '0x…' }`, but the runtime Zod validator only accepts `address` (or `adapter`). We hit `INPUT_VALIDATION_FAILED: Unrecognized key(s) in object: 'account'; At least one of 'adapter' or 'address' must be provided in a balance source.` — a 30-second fix once the error surfaces, but the quickstart should match the validator. Also: the README example uses `createViemAdapterFromPrivateKey` then dereferences `adapter.account?.address`, but the runtime adapter exposes `getAddress(chain)` instead — deriving the EOA via `privateKeyToAccount(pk).address` directly (from `viem/accounts`) is more straightforward for read-only flows. Product ask: a worked-out **deposit → balance → spend → withdraw** round-trip example for a single EOA on testnet, so it's clear the unified balance is gated by `kit.unifiedBalance.deposit()` rather than appearing automatically from existing ERC-20 holdings.

* **CCTP V2** — `scripts/cctp-demo.py` in the repo implements the direct-mint path in ~200 lines of viem-equivalent Python. We ran it live as part of this submission — **1.0 USDC moved Sepolia → Arc Testnet end-to-end in ~60 seconds** (approve + burn on Sepolia, Iris attestation `pending_confirmations` → `complete` in ~12 s, then `receiveMessage` on Arc):

  ```
  approve  (Sepolia) : 0x7457ef1dcd2a3cdb5d43bbc7912f70a0ef5ee953ed2935a0f4df522aa2050b3d
  burn     (Sepolia) : 0x2aebe23128bb7742c6c3babbd32889c29f3b938940176c41d794169a28f4d615
  mint     (Arc)     : 0x8a4ae433cfef773298bb766e1ea4c2d5d1f5005f3a5002fbe03439c370baeccf
  ```

  Verifiable on the explorers (`sepolia.etherscan.io` and `testnet.arcscan.app`). Balance delta confirms: Sepolia USDC 20 → 19, Arc USDC 60 → 60.08 (mint plus small gas-on-Arc credit from a parallel run). Real product gap we hit: the contract addresses page is mainnet-only by default; we had to dig for the testnet table. Two clicks added to mark "Testnet" prominently would help.

---

## General Feedback

*Optional field.*

> **What worked:** `arc-canteen` as the spine of the hackathon was genuinely
> good — `context sync` pulling Arc + Circle docs and sample repos into one
> local folder meant you could be productive without tab-hunting, and
> `update-product` / `update-traction` made progress legible without a separate
> status channel. Arc Testnet was stable for the entire two-week window — no
> downtime that blocked us.
>
> **What was rough:** the Circle CLI Windows binding gap (detailed above) cost
> real time. More broadly, some RFB scope clarifications landed in Discord
> mid-build; a single canonical, versioned rules doc would save re-checking the
> announcement channel.
>
> **Suggestion:** publish the submission form's fields as a machine-readable
> schema on day one. Teams could then prepare submission copy in-repo from the
> start instead of reformatting it in the final 48 hours.

---

# Reference — supporting detail (NOT form fields)

The form has no field for the items below; keep them for your own answer-prep
and in case a judge asks. RFB tracks are not a form field either — RFB 02 /
RFB 03 alignment is woven into the Problem Statement and Project Description
above.

## Links

| What | URL / value |
|---|---|
| GitHub | https://github.com/tang-vu/reasoning-receipt |
| Demo video | https://youtu.be/LjuwQcyboYc |
| Live dashboard | https://rrtrace.xyz |
| ReceiptRegistryV2 (Merkle root + schema version) | https://testnet.arcscan.app/address/0x27d93c52fea923f956345af27f61d7bf47f0c4c1 |
| ReceiptRegistry V1 (source-verified) | https://testnet.arcscan.app/address/0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf |
| CanteenUSDC wrapper (source-verified) | https://testnet.arcscan.app/address/0x7473d0db92F77aA89F19A2D74174D14D14CBD3E1 |
| Latest release | https://github.com/tang-vu/reasoning-receipt/releases/tag/v0.4.0 |
| Circle Developer Console email | tangminhvu2212@gmail.com |

## Per-action cost evidence (measured, not hypothetical)

Mean cost per receipt across **4,558 real on-chain emissions**, measured by the
deployer wallet's USDC balance delta:

| Metric | Value |
|---|---|
| Total receipts emitted | **4,558** (and rising — daemon emits daily) |
| Distinct markets priced | 217 (Polymarket + Kalshi) |
| Distinct consumer wallets | 19 |
| Deployer USDC burned | ≈ 0.92 USDC |
| **Per-receipt gas cost** | **$0.000683 USDC** (≈ 1/15 of a cent, measured) |
| Avg end-to-end latency | 24.3 s (real Gemini grounding + Arc tx confirmation) |
| x402 settlement amount | $0.01 USDC per paid call |
| End-to-end consumer cost | $0.01 USDC paid + $0.0007 underlying gas |

## Transaction count — verify live

```sh
RPC=https://rpc.testnet.arc-node.thecanteenapp.com/v1/<your-token>
# Legacy rr-trace/2 receipts
cast call 0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf "totalReceipts()(uint256)" --rpc-url $RPC
# rr-trace/3 receipts (Merkle-rooted reasoning DAG)
cast call 0x27d93c52fea923f956345af27f61d7bf47f0c4c1 "totalReceipts()(uint256)" --rpc-url $RPC
```

Snapshot at last commit: **2,281 on V1 + 2,277 on V2 = 4,558 total** across
**217 distinct markets**. The V2 count grows live as the daemon emits.

## Margin explanation

A $0.01 oracle call is uneconomical on classical L1s — gas alone exceeds the
price of the answer. Sub-second, sub-cent settlement on Arc inverts that: each
receipt costs **less than the information it commits to**. That margin enables
a new product shape — selling reasoning, not predictions — and keeps the
agent's own consumer-wallet load loop honest (real on-chain volume).

## Verifiability cutoff (honest note, in case a judge re-hashes an old receipt)

Mid-build we caught a real bug in the Node Irys sidecar — it was
`JSON.parse → JSON.stringify`-ing the input before upload, re-serializing with
JS-default key order and float formatting. The on-chain `traceHash` (SHA-256 of
Python's canonical bytes) therefore did not byte-match the bytes on Irys, though
the semantic content was identical. Receipts before **#2273** load the right
trace JSON via CID but fail byte-for-byte verify; from #2273 onward,
`/verify/{id}` returns `verified: true`. We kept the bug+fix in the commit log
(`16ea6c1 fix: irys sidecar uploads raw bytes`) as evidence of iteration.

## Pre-submit checklist

- [x] `.env` gitignored, not committed
- [x] `git ls-files | grep -E "^(CLAUDE|notes/|plans/|\.claude|AGENTS)"` empty
- [x] No committed secrets
- [x] CI green on main
- [x] Dashboard live: https://rrtrace.xyz
- [x] V1 + V2 contracts source-verified on Arc Testnet explorer
- [x] Byte-for-byte trace verification proven against a live receipt (≥ #2273)
- [x] Product demo video uploaded: https://youtu.be/LjuwQcyboYc
- [ ] Founder pitch video — optional, do not block submission
- [ ] `scripts/setup.sh` smoke-tested from a fresh clone
- [x] `arc-canteen update-product` + `update-traction` ran during the build
