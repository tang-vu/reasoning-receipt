# Demo script

The submission demo is ~3 minutes, no voice-over, captions only. Below is the script ready to record one-take if you'd rather speak it.

## Setup (~2 min)

```bash
# Terminal 1 — server
cp .env.example .env  # fill in keys for live mode; mock fallback works without
uv run uvicorn server.main:app --port 8000

# Terminal 2 — agent loop
uv run python -m agent.loop

# Terminal 3 — dashboard
cd dashboard && npm install && npm run dev    # http://localhost:3000

# Seed the DB so the dashboard isn't empty (optional)
uv run python -m scripts.seed-demo --count 80
```

## Segment 1 — Agent loop (30 s, terminal capture)

Caption: *"The agent runs continuously. Scan markets → produce a probability with Gemini 3.1 Pro Preview (Google Search grounded, via Vertex AI) → hash the trace → emit a Receipt on Arc. Sub-second per cycle."*

Show two scrolling log lines per second of the agent loop printing `priced X prob=Y conf=Z tx=0x…`. Stop after ~30 s.

## Segment 2 — Paid query (60 s, terminal capture)

Caption: *"An external consumer pays $0.01 over x402. Server returns a 402 challenge, consumer signs, server settles on Arc, and returns a receipt."*

Run:

```bash
uv run python -m scripts.demo-runner
```

The script prints a markdown table of 5 receipts with probability, confidence, latency, and the Arc tx hash. Total cost: $0.05 USDC.

## Segment 3 — Dashboard (45 s, headless browser)

Caption: *"The public dashboard reads on-chain receipts and renders PnL, trace explorer, and per-market volume. Anyone can verify any receipt by re-hashing the trace from Irys."*

Headless Chrome walks through `/` → `/traces` → `/traces/{id}` → `/events` → `/stats`. Each page renders in <1 s, no client-side fetching, everything server-rendered.

## Segment 4 — Arc explorer (30 s, browser capture)

Caption: *"Every receipt is a real on-chain event. Here's the contract event log on Arc testnet."*

Open the explorer URL for `RECEIPT_REGISTRY_ADDRESS`, switch to the **Events** tab, and scroll through the `Receipt` log lines emitted during the demo.

## Segment 5 — Title card (15 s)

Caption:
```
ReasoningReceipt
x402 oracle for prediction markets
the trace is the product
github.com/tang-vu/reasoning-receipt
```

## Stitching

```bash
uv run python -m scripts.record-demo --out recordings/demo.mp4
```

Produces `recordings/demo.mp4` (1080p, ~3 min). Upload to YouTube unlisted; paste the URL into `docs/SUBMISSION.md`.
