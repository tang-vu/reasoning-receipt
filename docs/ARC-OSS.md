# Arc OSS — ReasoningReceipt as composable Arc infrastructure

> Submission to the **Arc Open Source Showcase**. ReasoningReceipt is
> MIT-licensed and stays open source during and after the event. This file is
> the fork-it manual: every reusable primitive, where it lives, what it depends
> on, and how to lift it into your own Arc project.

## The gap we filled

The Arc reference repos — `arc-commerce`, `arc-p2p-payments`, `arc-escrow` —
are all **payment-flow** primitives: checkout, transfer, escrow release.
ReasoningReceipt needed a different class of building block:
**verifiable-data infrastructure** — anchor an auditable artifact on Arc for a
fraction of a cent, then let *anyone* prove one piece of it without trusting
the publisher.

No Arc reference repo covered that. We built it. The four primitives below are
factored to be lifted out — each is self-contained, has a small dependency
surface, and is documented to fork. They live in one repo today (one coherent
submission), but none of them is entangled with the prediction-market app:
copy the listed files and the primitive runs.

> **Headline primitive spun out as a standalone Arc starter kit:**
> [`tang-vu/arc-merkle-anchor`](https://github.com/tang-vu/arc-merkle-anchor) —
> the Merkle-anchored audit registry below, generalized (no oracle-specific
> fields) and packaged so Arc builders can clone-and-deploy in 5 minutes.
> Live + source-verified on Arc Testnet at
> [`0x707B2243583CC6A9bda9AF5EAF02720042917769`](https://testnet.arcscan.app/address/0x707B2243583CC6A9bda9AF5EAF02720042917769).
> Per aadi's 2026-05-23 hint, the starter kit's docs target Arc builders from
> scratch — separate from this product's submission docs.

---

## Primitive 1 — Merkle-anchored audit registry *(headline)*

**`contracts/src/ReceiptRegistryV2.sol`** + **`agent/merkle.py`**

A generic, append-only on-chain registry for **any** auditable artifact. You
commit a tuple — `(contentHash, merkleRoot, schemaVersion, cid)` — and the
contract exposes an on-chain verifier:

```solidity
function verifyInclusion(bytes32 root, bytes32 leaf, bytes32[] calldata proof)
    external pure returns (bool);
```

That is the wedge. A consumer who only has the 32-byte root from an event log
can prove that one specific leaf — one evidence URL, one line item, one
inference step — was part of the commitment, by submitting a **~200-byte
proof**. No full-payload download, no trust in the publisher.

- **Hash:** SHA-256 throughout, via the Ethereum `sha256` precompile (~60 gas
  per proof level — far cheaper than a Solidity keccak loop).
- **Proofs:** sorted-pair (`sha256(min(a,b) ‖ max(a,b))`), so proofs are
  direction-free. Odd levels promote the lonely node (OpenZeppelin-canonical,
  no second-preimage risk). `agent/merkle.py` is the off-chain prover and it
  mirrors `verifyInclusion` **byte-for-byte** — same algorithm, same hash.
- **Cost:** one extra indexed `bytes32` per emit vs. a plain hash registry.
  Measured at **$0.000683 USDC** per receipt across 4,500+ live emissions on
  Arc Testnet.
- `publishV2` for single writes, `publishBatchV2` for amortized batch emits.

**Live + source-verified:**
`0x27d93c52fea923f956345af27f61d7bf47f0c4c1` ([Arcscan](https://testnet.arcscan.app/address/0x27d93c52fea923f956345af27f61d7bf47f0c4c1)).

**Fork it:**
1. Copy `contracts/src/ReceiptRegistryV2.sol` — pure Solidity 0.8.26, **zero
   imports**, no OpenZeppelin dependency.
2. Copy `agent/merkle.py` — pure Python stdlib (`hashlib` only), **zero
   third-party deps**.
3. Deploy with `scripts/deploy-registry-v2.sh` (Foundry 1.7.1, `via_ir=true`).
4. Rename `marketId`/`probability`/`confidence` to your domain fields, or keep
   them generic — the Merkle machinery doesn't care what the leaves mean.

**Extends beyond the reference repos:** payment repos move value. This anchors
*claims about value* — provenance, audit trails, ML inference logs, document
notarization — and makes a single claim independently checkable on-chain.
Arc had no "commit-and-prove-inclusion" reference contract before this.

---

## Primitive 2 — x402 v2 paywall middleware for FastAPI + MCP

**`server/x402.py`** + **`server/facilitator.py`** + **`server/mcp_paywalled.py`**

Drop-in per-call USDC monetization for any HTTP API on Arc. First request to a
protected route returns a spec-compliant **`402 PAYMENT-REQUIRED`** challenge:

- network `eip155:5042002` (Arc Testnet), amount in micro-USDC, `payTo`
  receiver, Gateway Wallet `verifyingContract`;
- the consumer signs an **EIP-3009 `TransferWithAuthorization`** typed-data
  payload and retries with an `X-Payment` header;
- the server settles via Circle Gateway `/v1/settle` and serves the response.

The facilitator is a **swappable boundary** (`facilitator.py`) — exactly the
seam the x402 spec defines. Point it at Circle's live `/v1/settle`, a local
verifier, or a mock for tests, without touching route code.
`mcp_paywalled.py` shows the same envelope wrapping **MCP tools** — an
agent-to-agent commerce path (`GET /mcp/v1/{get_price,audit}`, $0.01/call).

**Fork it:** copy the three files; depends on FastAPI + `httpx` + `eth-account`.
Decorate any route; set `payTo` / amount / facilitator URL via env. The
EIP-3009 typed-data builder and the 402 challenge are reusable as-is.

**Extends beyond the reference repos:** `arc-commerce` is a cart/checkout flow
— one purchase, one human. This is **per-request micropayment middleware** for
machine consumers: priced at the HTTP layer, no cart, no session, settles in
the request/response cycle. Built for agents paying agents.

---

## Primitive 3 — Headless Circle wallet provisioning

**`scripts/circle-setup.py`**

Provision Circle **developer-controlled wallets** with zero console clicks.
One script run, ~4 seconds:

1. generate the entity secret and **RSA-OAEP-encrypt it client-side** against
   Circle's public key (the secret never leaves the machine in plaintext);
2. register the ciphertext, create a `walletSet`, create N wallets — one POST
   each;
3. write every resulting wallet ID + address straight into `.env`.

This is the missing bootstrap step in the Arc/Circle reference samples, which
assume wallets were already provisioned by hand in the Circle console. CI,
fresh clones, and reproducible demos all need this to be a script.

**Fork it:** copy `scripts/circle-setup.py`; depends on `httpx` + `cryptography`
(RSA-OAEP). Set `CIRCLE_API_KEY`, set how many wallets you need, run it.

**Extends beyond the reference repos:** a developer-experience primitive, not
an app feature — it makes every other Circle-on-Arc project clone-and-go.

---

## Primitive 4 — Canonical-JSON byte-verifier

**`agent/trace.py`** + **`agent/trace_v3.py`**

Turn any structured object into a **byte-reproducible** artifact: deterministic
canonical JSON (sorted keys, fixed-precision floats, UTC timestamps), then
SHA-256 — per node, for the Merkle leaf set, and over the whole blob. Because
canonicalization is deterministic, a third party who fetches the same object
recomputes the identical hash and byte-matches the on-chain commitment. This is
what makes Primitive 1's roots *meaningful* rather than opaque.

**Fork it:** copy `agent/trace_v3.py` (canonicalizer + per-node hashing) and
`agent/merkle.py`; pure stdlib. Feed it your own object shape — it commits
whatever DAG of nodes you hand it.

---

## Supporting modules

- **Irys upload sidecar** — `services/irys/` — a tiny Node sidecar that does
  Bundlr-signed content-addressed uploads callable from Python. Reusable
  storage adapter for the `cid` field any Primitive-1 registry needs.
- **MCP stdio server** — `services/mcp/server.js` — wraps an HTTP API as a
  Claude Desktop / Cursor tool server; fork the tool-registration shape.
- **Client-side receipt verifier** — `scripts/verify-receipt.py` — fetches a
  trace from the Irys gateway and re-hashes it offline, trusting no server.
  The reference consumer for a Primitive-1 deployment.

---

## Composability map

| Primitive | Files to copy | External deps | Class |
|---|---|---|---|
| Merkle-anchored audit registry | `ReceiptRegistryV2.sol`, `agent/merkle.py` | none (Solidity 0.8.26 / Python stdlib) | verifiable data |
| x402 v2 paywall middleware | `server/x402.py`, `facilitator.py`, `mcp_paywalled.py` | FastAPI, httpx, eth-account | micropayments |
| Headless Circle provisioning | `scripts/circle-setup.py` | httpx, cryptography | developer experience |
| Canonical-JSON byte-verifier | `agent/trace_v3.py`, `agent/merkle.py` | Python stdlib | verifiable data |

All four are MIT-licensed and depend only on Arc Testnet + Circle public
endpoints — no ReasoningReceipt service has to be running for a fork to work.

## License & open-source commitment

MIT — see [`LICENSE`](../LICENSE). The repo is public and stays public during
and after the Arc Open Source Showcase. Issues and forks welcome; the four
primitives above are the parts we most want other Arc builders to take.
