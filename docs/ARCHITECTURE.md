# Architecture

ReasoningReceipt is an x402-paywalled prediction-market oracle where every priced response carries a hashed, on-chain pointer to the full reasoning trace that produced it. The trace is the product.

```mermaid
graph LR
  A[Polymarket / Kalshi APIs] -->|events| B(Scanner)
  B --> C{Analyst — Gemini 3.1 Pro Preview<br/>+ Google Search grounding}
  C -->|trace JSON| D[Canonicalizer<br/>sort keys · UTC · 6dp floats]
  D -->|sha256| E[Irys / IPFS pin]
  D --> F[Trader — Kelly sizing<br/>portfolio wallet]
  E -->|CID + hash| G[ReceiptRegistry.sol on Arc]
  G -.->|Receipt event| H[Dashboard (Next.js / Vercel)]
  I[External consumer] -->|GET /price| J(FastAPI server)
  J -->|402 challenge| I
  I -->|USDC via x402| J
  J -->|settle| K[Circle Nanopayments facilitator]
  K --> G
  J --> H
  F -->|orders| L[Polymarket CLOB]
  L --> M[(Positions table)]
```

## Component map

| Layer | Files | Job |
|---|---|---|
| Scanner | `agent/scanner.py` | Pull Polymarket Gamma markets, apply liquidity / horizon / language filter, persist a candidate cache. |
| Analyst | `agent/analyst.py`, `agent/prompts/analyst.md` | Single Gemini 3.1 Pro Preview call (Vertex AI when `GOOGLE_CLOUD_PROJECT` set, public Gemini API otherwise) with Google Search grounding. Automatic fallback chain to Flash Preview and Gemini 2.5 Flash on quota / availability errors. Returns probability, confidence, cited sources, counter-arguments, sensitivity. |
| Trace | `agent/trace.py`, `storage/irys.py` | Canonicalize the analyst output, SHA-256 it, upload to Irys, return `(hash, cid)`. |
| Chain client | `server/chain.py`, `contracts/src/ReceiptRegistry.sol` | Emit `Receipt(...)` on Arc with `(consumer, market, probability, confidence, hash, cid)`. |
| x402 paywall | `server/x402.py`, `server/facilitator.py` | Issue HMAC-signed challenges, verify payments, settle via Circle Nanopayments. |
| Server | `server/main.py`, `server/routes.py` | `/price/<id>` orchestrates: pay → analyse → seal → publish → row. |
| Agent loop | `agent/loop.py`, `scripts/run-agent.sh` | Continuous scan → analyse → publish → trade cycle. |
| Trader | `agent/trader.py` | Half-Kelly sizing capped at 5 % bankroll. Submits Polymarket CLOB orders. |
| Wallets | `wallets/circle.py`, `wallets/portfolio.py` | Separate Circle wallets for the portfolio and for the agent's consumer-of-its-own-oracle role. |
| Storage | `storage/db.py` | SQLAlchemy 2.0 ORM (SQLite dev, Neon Postgres prod). |
| Dashboard | `dashboard/` | Next.js 15 server-rendered home/traces/events/stats pages. |

## Request flow — `GET /price/{market_id}`

1. Consumer hits `/price/<market_id>` with no `X-Payment` header.
2. Server returns **402** with an `Accept-Payment` body describing the price (default $0.01 USDC on `arc-testnet`), the receiver, an HMAC-signed nonce, and an expiry. The signed challenge token is in the `X-Payment-Challenge` response header.
3. Consumer signs an EIP-712 payment payload off-chain and retries with both headers set.
4. Server verifies the HMAC challenge (resource + nonce + expiry) and forwards the payment to the Circle facilitator for settlement (mock facilitator is in-process for local dev).
5. On settle, the analyst runs against the market candidate. The output is canonicalized, hashed, and pinned to Irys.
6. `ReceiptRegistry.publish(...)` emits `Receipt` on Arc with the consumer address, market id, probability, confidence, trace hash, CID, and timestamp.
7. A row is persisted with the on-chain receipt id, tx hash, block number, and latency.
8. Response body returns the price, the trace pointer, the on-chain refs, and the latency.

The challenge is HMAC-signed and stateless — no server-side session store. A short TTL (default 300 s) plus a per-request nonce defangs replay.

## Trace canonicalization

```text
trace_bytes = utf-8(json.dumps(payload, sort_keys=True, separators=(",", ":")))
              where every float is rounded to 6 decimal places before serialization
trace_hash  = "0x" + sha256(trace_bytes).hex()
```

This deterministic byte format means any client in any language can re-derive the hash from the JSON it pulls from Irys and compare it to the value on Arc. There is no "trust the publisher" step.

## Why Arc

Per-receipt economics make or break this product. Posting a $0.01 receipt over a classical L1 (gas ~$0.50+) is nonsense. On Arc the receipt costs *less than the answer it commits to* and settles in sub-second. That's what makes the agent's own consumer wallet a viable way to drive on-chain volume.

## Failure modes

| Failure | Behaviour |
|---|---|
| Gemini / Vertex outage | Analyst falls back to deterministic mock answer; trace and receipt continue. The trace's `model` field flips to `mock:...` so consumers can detect it. |
| Arc RPC outage | Chain client switches to mock mode, returns a synthetic tx hash. The DB row records `is_mock=True` via the model field; replays are skipped. |
| Irys outage | IrysClient enters mock mode; CID is a deterministic shortened hash. The trace can still be regenerated locally from the DB question + analyst output. |
| Polymarket schema drift | Scanner catches the exception, falls back to the deterministic mock fixture, and logs a warning. |
| Facilitator rejects | Server returns 402 with the facilitator error in the detail; consumer is not charged. |

## Observability

* `GET /healthz` reports per-subsystem mock state.
* `GET /stats` reports total receipts, distinct markets, distinct consumers, and total USDC settled.
* `GET /events/stream` is an SSE feed of new receipts as they emit — useful for live demos and downstream auditors.
* `GET /verify/{id}` re-derives the trace hash from the Irys-fetched canonical JSON and compares to the on-chain value. `scripts/verify-receipt.py` is the CLI version.
* The server-mode dashboard reads `/stats` and `/receipts` directly on each request — no caching layer.

## Deployment topology

```
                    push to main (dashboard/** or scripts/export-snapshot.py)
                                   │
                                   ▼
              .github/workflows/deploy-dashboard.yml
                                   │
                          npm ci · npm run build:snapshot
                                   │
                                   ▼
              GitHub Pages — https://tang-vu.github.io/reasoning-receipt/
                          (static, no backend, live forever)


  Harvey's PC (when actively driving volume)
   ├─ FastAPI server   uvicorn server.main:app
   ├─ Agent loop       python -m agent.loop
   └─ SQLite local
        │
        │ emits Receipt(...) events
        ▼
   Arc testnet · ReceiptRegistry.sol
        │ (persistent on-chain — survives PC reboots)
        │
        │ export-snapshot.py → dashboard/public/snapshot.json → git push
        ▼
   GitHub Pages refreshes ~70s later
```

The dashboard never talks to the FastAPI server in production — it reads a snapshot committed to the repo. That snapshot is regenerated from the SQLite DB whenever Harvey wants to publish updated traction.
