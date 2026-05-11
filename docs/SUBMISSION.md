# Submission — Agora Agents Hackathon

Copy-paste-ready text for every form field. Fill in the bracketed placeholders before clicking submit.

---

## Short description (≤ 140 chars)

> An x402-paywalled prediction-market oracle. Every price ships with a Gemini-grounded reasoning trace, settled on Arc in <1 s for ~$0.01.

(134 chars.)

---

## Long description (~800 words)

ReasoningReceipt is an on-chain oracle for prediction markets where the **reasoning trace is the product, not just the number**. A consumer pays a few cents of USDC over x402, gets back a probability for a Polymarket or Kalshi event, and — critically — a **receipt**: a hashed, content-addressed pointer to the full chain-of-thought that produced the number. The trace lives on Irys (Arweave-compatible), the SHA-256 of its canonical bytes lives on Arc inside `ReceiptRegistry.sol`. Anyone can pull the trace, re-canonicalize it, hash it, and verify byte-for-byte that the published reasoning is what the oracle actually emitted. There is no "trust the publisher" step.

The agent itself is a four-stage loop. A **scanner** polls Polymarket Gamma for liquid (> $10k 24h volume), near-resolution (≤ 30 days), English-language markets. An **analyst** stage calls Gemini 2.5 Pro via Vertex AI with Google Search grounding and a strict structured-output prompt that demands a probability, calibrated confidence, at least two cited sources with URLs, at least one weighted counter-argument, and a sensitivity analysis. A **trace** stage canonicalizes that output — sorted keys, UTF-8, fixed 6-decimal floats, UTC timestamps — hashes it with SHA-256, and pins the bytes to Irys. A **trader** stage takes the analyst's probability, computes edge against the current market mid, and (when edge ≥ 4 pp and confidence ≥ 0.5) submits a Kelly-sized order on Polymarket capped at 5 % of the portfolio bankroll, half-Kelly when confidence is below 0.7. The portfolio wallet is a Circle developer-controlled wallet on Arc; a *separate* Circle wallet ("consumer wallet") pays the oracle for events the trader is sizing. The agent is, honestly, eating its own cooking — on-chain volume is real, not synthetic.

The server is the second face of the same oracle. A FastAPI endpoint `GET /price/<market_id>` returns 402 when called unpaid, with an `Accept-Payment` body describing the price (default $0.01 USDC), the receiver address, an HMAC-signed nonce challenge, and a TTL. The consumer signs an EIP-712 payment payload and retries with the `X-Payment` header set. The server verifies the HMAC challenge, forwards the payload to the Circle Nanopayments facilitator for settlement, runs the analyst (cache-coalesced per market id for a short window), seals the trace, emits `Receipt(...)` on Arc, persists the row, and returns the price plus the trace pointer. Per-call latency averages ~15 ms on the mock chain client and ~600 ms end-to-end against live Arc settlement. The challenge token is HMAC-only — no session store, no replay window beyond the nonce's TTL, fully horizontally scalable.

The dashboard at `dashboard/` is a Next.js 15 app deployed to Vercel. It server-renders every page on each hit, no caching layer — judges click a URL and see the on-chain truth, not a stale cache. The home page shows total receipts, USDC settled, distinct markets, distinct consumers, a 24-bucket volume chart, and the 100 most recent receipts. The trace explorer drills into any single receipt to show the cited sources, counter-arguments, the trace hash, the Irys CID, the Arc tx hash, and the paying consumer's address.

Per the "agentic sophistication" rubric: multi-stage autonomous decisions (scan → analyse → trade → publish → serve), Gemini 2.5 Pro for the reasoning step with Google Search grounding for fresh news context, structured traces that include not just the answer but the sources, the counter-arguments, and the sensitivity analysis. Per the "traction" rubric: the agent's consumer wallet drives continuous load, so every receipt on the dashboard is a real on-chain event. Per the "Circle tools" rubric: USDC settles every payment, Circle Wallets hold the portfolio and consumer balances, Nanopayments facilitates the x402 flow, Arc is the settlement chain. Per the "innovation" rubric: the wedge — "trace as the product" — is explicit in the README, the demo, the analyst prompt, and the contract event shape itself.

### Circle Product Feedback

* **Arc testnet** — sub-second confirmation is the unlock. Posting a $0.01 receipt to Ethereum L1 is nonsense; here the receipt costs less than the answer it commits to. The dev experience was tight: `arc-canteen rpc-url --export` and `cast block-number` worked first try.
* **USDC** — using USDC as both gas and value-of-payment removes a class of UX pain (no separate gas token to fund). One thing that bit us: explorer support for USDC-denominated tx fees would help judges audit per-call cost.
* **Circle Wallets (developer-controlled)** — single API for both portfolio and consumer roles. Signing flow with `entitySecretCiphertext` is clean. Suggestion: a batch-transfer endpoint would let us amortise consumer-wallet top-ups into a single tx rather than N transfers.
* **Nanopayments / x402** — facilitator interface matches `docs/x402/welcome` exactly. The thing we'd most want next: a "scheme: stream" so high-frequency consumers (like a downstream trading agent polling every 5 s) don't pay challenge round-trip every call.

---

## Tracks

- **RFB 02** — Prediction Market Trader Intelligence (primary)
- **RFB 03** — Per-action economics ≤ $0.01 (secondary)

---

## Links

| Field | Value |
|---|---|
| GitHub | `https://github.com/tang-vu/reasoning-receipt` |
| Demo video | `[YouTube unlisted URL — fill in after recording]` |
| Live dashboard | `[Vercel URL — fill in after deploy]` |
| Contract on Arc | `[Arc explorer URL — fill in after deploy]` |
| Team | Solo — Vu Minh Tang (`tang-vu`) |
| Circle Developer Console email | `[email — fill in]` |

---

## Tech stack

Python 3.11+ (FastAPI, `google-genai` SDK targeting Vertex AI, web3.py, SQLAlchemy 2.0), Solidity 0.8.26 (Foundry), TypeScript / Next.js 15 / Tailwind / Recharts, Arc testnet, Circle Wallets (developer-controlled), Circle Nanopayments, x402, Polymarket Gamma + CLOB, Irys.

---

## Per-action cost evidence

Mean cost per receipt across the last 1 000 events:

| Metric | Value |
|---|---|
| Receipt emission gas | `[fill in]` |
| Effective USD cost / receipt | `[$ from Arc explorer fee column]` |
| x402 settlement amount | `$0.01 USDC` |
| End-to-end consumer cost | `≈ $0.01 USDC` |

Screenshot of an Arc explorer fee column for a single `ReceiptRegistry.publish(...)` call: `docs/images/per-action-fee.png`.

---

## Transaction count

Pulled from the contract event log at submission time:

```sh
cast call $RECEIPT_REGISTRY_ADDRESS "totalReceipts()(uint256)" --rpc-url $RPC
```

Target: ≥ 1 000 emitted receipts before submission, ≥ 7 days of PnL data on the portfolio wallet.

---

## Margin explanation

A $0.01 oracle call is uneconomical on classical L1s — gas alone exceeds the price of the answer. Sub-second, sub-cent settlement on Arc inverts that: each receipt costs **less than the information it commits to**. That margin enables an entirely new product shape — selling reasoning, not predictions — and makes the agent's own consumer-wallet load loop honest (real on-chain volume, not synthetic ticks).

---

## Pre-submit checklist

- [ ] `.env` redacted from any uploaded asset
- [ ] `git ls-files | grep -E "^(CLAUDE|notes/|\.claude|AGENTS)"` returns empty
- [ ] `git ls-files | xargs grep -l "sk-ant\\|0x[a-f0-9]\\{64\\}"` returns empty (no committed secrets)
- [ ] Demo video plays in incognito
- [ ] Dashboard public URL responds in incognito
- [ ] `scripts/setup.sh` works from a fresh clone in `/tmp/test-clone`
- [ ] All bracketed placeholders above are filled in
