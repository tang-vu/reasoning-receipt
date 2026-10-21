# ReasoningReceipt on Aomi: independent audit

Today the oracle grades and seals its own work. The critic that gates publication is a
model pass inside the same system, and the loop then uploads the trace and calls
`publishV2` itself. This Aomi App moves the last step to an independent auditor. With
`RR_AUDIT_MODE=aomi`, the loop stops at the raw trace. The auditor checks every cited
source, and only an approved trace is sealed and published, from the auditor's own wallet.

**Audits are disabled by default.** An ordinary build has no EVM namespace, and the API
refuses every audit route until a registry and an auditor wallet are configured.

```mermaid
sequenceDiagram
    participant Loop as Oracle loop
    participant API as ReasoningReceipt API
    participant Aomi as Aomi auditor
    participant Web as Cited sources
    participant Irys
    participant Wallet as Auditor wallet
    participant Arc as ReceiptRegistryV2 (Arc)
    Loop->>API: Critic-approved trace, stored as pending (no upload, no publish)
    Aomi->>API: GET /v1/audits/next
    Aomi->>Web: Fetch every cited URL (the app's own requests)
    Aomi->>Aomi: Judge each source and the claim
    Aomi->>Web: Fetch again at seal time
    Aomi->>API: POST /seal (fetch results + judgments + verdict)
    alt any source unreachable or unsupported, or verdict rejected
        API-->>Aomi: rejected, with reasons. Nothing is published
    else approved
        API->>API: Add xa_* nodes, keep every oracle node hash, new Merkle root
        API->>Irys: Upload sealed trace
        API-->>Aomi: Unsigned publishV2 (hash, root, CID)
        Aomi->>Aomi: Decode every ABI word, must match the seal
        Aomi->>Arc: stage_tx, then enforced simulate_batch (stop on failure)
        Aomi-->>Wallet: Preview, explicit approval (commit_txs)
        Wallet->>Arc: publishV2, publisher = auditor
        Aomi->>API: POST /published (tx hash)
        API->>Arc: Status, finality, canonical block, one matching ReceiptV2
        API-->>Aomi: published, receipt id
    end
```

## What the audit adds to the trace

The sealed trace is the oracle's `rr-trace/3` JSON, unchanged, plus `external_audit`:

| Node | Holds |
|---|---|
| `xa_<evidence id>` | one per cited source: URL, HTTP status, final URL, SHA-256 of the body, page title, whether it matches the cited title, fetch time, error, and the auditor's `supports` judgment with a one-line note |
| `xa_verdict` | `aomi-audit/1`, auditor address, chain, verdict, reasons, notes, time, and the oracle trace's own hash and Merkle root |

Every oracle node keeps its hash. The new nodes join the same sorted-pair Merkle tree, so
`/verify/{id}` and `/verify/{id}/node/{node_id}` work unchanged, including for `xa_*`
nodes. The audit says the record is honest: the sources exist and say what the trace
claims. It does not say the forecast is right; calibration still judges that.

## Where each rule is enforced

| Rule | Where |
|---|---|
| The model cannot write fetch results | `rr_seal_audit` re-fetches every source itself and sends those results. The model only adds `supports`, a note per source, a verdict and notes. |
| Approval is earned, not declared | The API skips sources that refused the fetch (403, 429, timeouts) and counts a 404 or 410 as unsupported. It rejects the audit unless more than half of the counted sources were retrieved with a 2xx and a body hash and `supports` them, and it rejects if the trace cites nothing or the verdict is `rejected`. Skipped sources are listed in `xa_verdict`. It requires exactly one finding per cited source at its cited URL. |
| Only the configured auditor publishes | Seal requires the connected wallet to equal the deployment's auditor on its chain. The skill guard limits writes to that chain, the registry and the `publishV2` selector. Confirmation requires the `ReceiptV2` publisher topic to be the auditor. |
| The publish matches the seal | The app decodes every word of the returned calldata (no consumer, market hash, probabilities, trace hash, root, schema, CID) before staging, and the host simulates it with stop on failure. Confirmation compares the logged event to the sealed calldata. |
| Pending, reverted or unfinalized never count | `/published` returns `pending`, `pending_finality` or `reverted` and records nothing. Success needs status `0x1`, a block at or below `finalized`, a canonical block hash and exactly one matching event. |
| One receipt per audit | `audits.transaction_hash` and `audits.trace_hash` are unique, and both the seal and the publish writes are conditional on the previous status. Tests run six concurrent confirmations. |

Two limits are worth stating. `ReceiptRegistryV2.publishV2` accepts repeated publishes, so
a second broadcast of the same audit would emit a second event; it can never become a second
recorded receipt, and the skill says to confirm the hash it has rather than publish again.
Source fetches resolve the host and refuse private, loopback and link-local addresses before
connecting, but a host that changes its DNS answer between the check and the request is not
fully excluded.

## Configure for live testing

1. Copy `audit-deployment.example.json` to `audit-deployment.json` (ignored by git), set the
   auditor wallet, and set `enabled` to `true`. The example already points at the live
   `ReceiptRegistryV2` on Arc testnet (`0x27d93c52…c4c1`); `publishV2` is permissionless.
2. On the API, set `RR_AUDIT_CONFIG` to that file, `RR_AUDIT_RPC_URL` to an Arc testnet RPC
   that supports the `finalized` block tag, and `RR_AUDIT_API_TOKEN` to a random token.
3. On the oracle loop, set `RR_AUDIT_MODE=aomi` (with `RR_USE_ENSEMBLE=1`).
4. Build the app with `RR_AUDIT_CONFIG` pointing at the same file. An invalid enabled
   deployment fails the build. Give only `RR_AUDIT_API_TOKEN` to the app's environment.
5. Audit one trace on Arc testnet through Aomi with the funded auditor wallet, then open
   `/verify/{receipt_id}` for the recorded receipt.

## Deploy

`.aomi/config.json` at the repo root lists this App, the repo-root `Cargo.toml` carries the
SDK pin Aomi's deploy gate reads, and this folder is its own Cargo workspace with
`Cargo.lock` beside it. `aomi.toml` sets `public = false` until the live run passes.

## Develop

```bash
cargo test --locked                                         # disabled build
RR_AUDIT_CONFIG=/abs/path/audit.json cargo test --locked    # configured build
uv run --extra dev pytest tests/test_audit.py               # API and loop, from the repo root
```
