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

## Segment 1 — 5-agent ensemble (30 s, terminal capture)

Caption: *"Each market goes through a structured debate. Bull / Bear / Edge run in parallel with isolated context. Supervisor merges. Critic audits across six rigor dimensions. Sub-second per stance, ~3 s per market end-to-end."*

Show scrolling log lines: stance Gemini calls fire in parallel, supervisor synthesises, critic audits, V2 emit fires. Lines look like `loop[v3]: priced X prob=0.62 conf=0.74 disagreement=21.3pp cat=macro tx=0x…`.

## Segment 2 — Paid query through x402 (60 s, terminal capture)

Caption: *"An external consumer pays $0.01 over x402. Server returns a 402 challenge with the PAYMENT-REQUIRED body, consumer signs an EIP-3009 TransferWithAuthorization, server settles via Circle Gateway and emits a ReceiptV2 with the Merkle root of the reasoning DAG."*

Run:

```bash
uv run python -m scripts.demo-runner
```

The script prints a markdown table of 5 receipts with probability, confidence, latency, the Merkle root, and the Arc tx hash. Total cost: $0.05 USDC.

## Segment 3 — Dashboard tour (45 s, headless browser)

Caption: *"Live SSE-backed receipt feed at rrtrace.xyz. Click a v3 receipt → see the ensemble panel (3 stances + supervisor weights), the critic's 6-dim audit, the falsifiable claims. Click Verify → fetch the trace from Irys, re-canonicalise, re-hash client-side, compare to the on-chain hash. Byte-for-byte."*

Playwright tour: `/` (hero + live feed + capability pills) → `/traces` (archive) → `/traces/{v3_id}` (ensemble panel, critic radar, falsifiables, verify button) → `/calibration` (Brier + reliability) → `/stats`.

```bash
uv run python -m scripts.record-demo --v3-trace-id <recent-v3-id>
```

## Segment 4 — On-chain Merkle proof (30 s, terminal + explorer)

Caption: *"Every node of the reasoning DAG — every evidence URL, every counter-argument, every sensitivity factor — gets its own SHA-256 and lives under the Merkle root on Arc. Here's a single-node inclusion proof passing on-chain via verifyInclusion."*

```bash
# Generate proof off-chain + verify on-chain (~200 bytes)
uv run python -m scripts.verify-receipt --node <node_id> <receipt_id>
```

Then open the explorer URL for `RECEIPT_REGISTRY_V2_ADDRESS` and switch to the **Events** tab — judges see the `ReceiptV2(...)` log entries with the merkleRoot field populated.

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

## Public dashboard (GitHub Pages)

The dashboard supports two modes:

* **Server mode** (default): Next.js SSR talking to the local FastAPI server at `NEXT_PUBLIC_DASHBOARD_API_URL`. Good for local dev.
* **Snapshot mode**: static export reading a frozen `public/snapshot.json` produced from the SQLite DB. Hosted free on **GitHub Pages** with custom domain at https://rrtrace.xyz — no backend needed, dashboard stays up forever.

### Auto-deploy on every push

`.github/workflows/deploy-dashboard.yml` runs on any push touching `dashboard/**`. It:

1. Reads the committed `dashboard/public/snapshot.json` (or emits a placeholder if absent)
2. Builds Next.js with `NEXT_PUBLIC_USE_SNAPSHOT=1 NEXT_PUBLIC_BASE_PATH=/reasoning-receipt`
3. Uploads the static output to GitHub Pages

→ To refresh the dashboard with new on-chain data:

```bash
# Local: export the latest snapshot from your SQLite DB
uv run python -m scripts.export-snapshot --out dashboard/public/snapshot.json --limit 2000

# Commit + push — Pages workflow rebuilds automatically
git add dashboard/public/snapshot.json
git commit -m "snapshot: <N> receipts"
git push
```

### Manual local build (if you want to preview before pushing)

```bash
cd dashboard
npm run build:snapshot   # produces ./out
npx serve out            # or any static server
```
