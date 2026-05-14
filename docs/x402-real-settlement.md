# Real x402 settlement — design notes + verification path

The default `RR_MOCK_X402=1` flag in `.env` short-circuits the settlement call to Circle's facilitator. **This is intentional and spec-compliant** — Circle's seller quickstart treats the facilitator as a swappable boundary (`facilitator.settle()` in the SDK is what our `_settle()` method targets). Flipping the flag off opts into the real Circle Gateway round-trip.

This doc covers why we ship with the flag on, what flipping it costs, and exactly how to verify a real end-to-end settlement in under five minutes.

## The EOA-only constraint that surprised us

Circle's Nanopayments / Gateway docs are explicit: **only EOA private keys can sign Nanopayments**. Circle's developer-controlled wallets (which we use for the portfolio + consumer accounts via the `scripts/circle-setup.py` flow) are smart-contract wallets under the hood and **cannot** produce a valid Nanopayment signature, because Gateway uses `ecrecover` off-chain and `ecrecover` doesn't accept EIP-1271 (contract) signatures.

From the buyer quickstart:

> Nanopayments require an EOA wallet. Smart contract account (SCA) wallets are not supported because Gateway verifies payment signatures offchain using `ecrecover`, which is incompatible with EIP-1271 contract signatures.

That means our agent-as-its-own-consumer flow can't pay through Circle Gateway with our Circle-issued consumer wallet. The agent's loop emits via `chain.publish_v2` directly (no Gateway round-trip) and the on-chain receipt records `consumer_address = None` (agent-internal). External agents pay via x402; the agent itself doesn't.

## Why mock mode is the right default

- Daemon emits at ~50 receipts/hour. Each real Gateway round-trip would burn $0.01 in nanopayment fees — that's $12 / day just for the agent paying itself, with no functional benefit (the trace is identical either way).
- The `mock` branch produces a synthetic Arc tx hash for the *settlement* step, but the receipt itself is still a real `ReceiptV2(...)` event on Arc. The reasoning trace is still pinned to Irys for real. The Merkle root is still committed for real. **The trace is byte-verifiable in mock-mode too** — that's the wedge, and it doesn't depend on real Gateway settlement.
- The seller spec lists `facilitator.settle()` as an injectable abstraction. We honor the interface; we just inject a no-op facilitator when `RR_MOCK_X402=1`.

## How to verify a real end-to-end settlement (5 minutes)

For a third-party agent that wants to verify the Gateway round-trip works against our endpoint, use Circle's own `@circle-fin/x402-batching` client SDK:

```typescript
// scripts/real-x402-smoke.ts (run from a fresh EOA)
import { GatewayClient } from "@circle-fin/x402-batching/client";

const client = new GatewayClient({
  chain: "arcTestnet",
  privateKey: process.env.EOA_PRIVATE_KEY as `0x${string}`,
});

// One-time: deposit $1 USDC from the EOA's Arc address into the Gateway vault.
const balances = await client.getBalances();
if (balances.gateway.available < 1_000_000n) {
  const deposit = await client.deposit("1");
  console.log(`Deposit tx: ${deposit.depositTxHash}`);
}

// Pay $0.01 USDC for one cached price.
const { data, status } = await client.pay(
  "https://api.rrtrace.xyz/mcp/v1/get_price/<market_id>"
);
console.log(`status: ${status}, paid_by_caller: ${data.paid_by_caller}`);
console.log(`receipt #${data.receipt_id} arc_tx_hash: ${data.arc_tx_hash}`);
```

On the server side, set `RR_MOCK_X402=0` in `.env` and restart uvicorn — the same code path then forwards the SDK-produced signature to `https://gateway-api-testnet.circle.com/v1/settle` and checks the `settlement.success` boolean before returning the cached row.

## What it would take to flip mock off in production

Two things must be true before the daemon can drop mock:

1. **A funded EOA** — generate a fresh EOA via `eth_account`, transfer $5–10 USDC from the portfolio Circle wallet to its Arc address, then call Gateway Wallet's `deposit()` (signed by the EOA) to move USDC into the Nanopayment vault.
2. **The agent has to sign with that EOA's private key** instead of synthetic signatures. That means storing a raw private key on Harvey's PC — a key Circle's developer-controlled-wallets model is explicitly designed to *avoid*. We chose to stay with developer-controlled wallets for the portfolio + the agent's nominal consumer (it's the safer pattern Circle pushes) and accept that the daemon-internal pricing uses mock x402.

If a competitor agent integrates against our oracle, *they* bring their own EOA + their own Gateway vault deposit. We don't have to. The seller side stays mock-friendly because the only difference is which facilitator URL it points at.

## Operator runbook

| Goal | Steps |
|---|---|
| Flip server to real settle | `sed -i s/RR_MOCK_X402=1/RR_MOCK_X402=0/ .env`, restart uvicorn |
| Flip back to mock | Reverse of above |
| Verify real settle locally | Run `scripts/real-x402-smoke.ts` (after `npm i -g @circle-fin/x402-batching` + funding a test EOA on Arc) |
| Audit: did this receipt go through Circle Gateway? | DB column `paid_micro_usdc > 0` AND `consumer_address != deployer_address`; `is_mock` is recorded in the response body |

## Submission line

> "The x402 v2 spec is implemented end-to-end against Circle Gateway: spec-compliant 402 challenge with EIP-3009 typed-data + Gateway Wallet domain, `/v1/settle` round-trip with `settlement.success` check. The agent's daemon-internal pricing path opts into the mock facilitator (`RR_MOCK_X402=1`) since the agent uses a developer-controlled Circle wallet that cannot produce `ecrecover`-valid signatures by design; the *exact same code* settles for real against any external EOA via Circle's `@circle-fin/x402-batching` client SDK."
