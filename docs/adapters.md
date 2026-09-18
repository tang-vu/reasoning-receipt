# Adapter guide

The protocol core is pure bytes-in/verdicts-out. Everything that touches
the outside world — storage, networks, chains, clocks, agent frameworks —
is an adapter. This page is the contract they live under.

## The boundary

```
agent / workflow
      │
      ▼
ReceiptBuilder ──► canonical document ──► verifier (offline)
                        │
                        ├─► file / database / HTTP          (storage adapters)
                        ├─► signatures                      (key management adapter)
                        ├─► content-addressed storage       (Irys, IPFS…)
                        └─► blockchain anchor               (Arc, EVM…)
```

An adapter may **transport, persist, anchor, or translate** receipts.
It must never change commitment semantics: canonicalization, hashing,
Merkle rules and validation live in `protocol/` only.

## Adapter contract

Every adapter follows three rules:

1. **Treat documents as opaque bytes.** Store/transport the canonical
   document verbatim; never re-serialize "equivalent" JSON through a
   non-canonical encoder before committing to it.
2. **Anchor compact commitments.** On-chain or in a log, record
   `merkle_root` (or `receipt_hash`) + `schema_version` + optional
   `receipt_id` — not whole receipts.
3. **Never reinterpret.** An adapter that encounters an unknown
   `schema_version` passes it through or rejects it; it does not
   "normalize" documents into something it understands.

## Built-in adapters

### Storage / anchoring

| Adapter | Module | What it does |
|---|---|---|
| Filesystem | `protocol/bundle.py` | portable `.rr` bundles — receipt + manifest + proofs, traversal-safe |
| Irys | `storage/irys.py` | content-addressed upload/fetch of canonical bytes |
| Arc / EVM | `contracts/` + `agent/` emitters | anchors `merkle_root` + `schemaVersion` in `ReceiptRegistryV2` |
| Postgres | `storage/db.py` | durable receipt rows; commitment fields stored verbatim |
| HTTP API | `server/portable.py` | create/verify/proof endpoints consuming the protocol core |

### Agent / tool adapters

| Adapter | Module | What it does |
|---|---|---|
| MCP | `protocol/mcp_server.py` | stdio MCP server: `create_receipt`, `verify_receipt`, `create_proof`, `verify_proof`, `inspect_receipt` |
| CLI | `protocol/cli.py` | `rr verify|inspect|proof|canon|hash|conformance` — fully offline |
| CI | `.github/actions/verify` | composite action: verify committed receipts in any repo |
| Framework events | `protocol/adapters.py` | map observable agent events (input/tool_call/tool_result/approval/outcome) to nodes — never hidden chain-of-thought |

## Writing a new adapter

Checklist:

- [ ] Input is a complete `reasoning-receipt/1` document or builder spec —
      no partial commitment state crosses the boundary.
- [ ] Output preserves committed bytes exactly (or is a proof/report
      derived from them).
- [ ] Failure modes are explicit: transport failure ≠ verification
      failure. An adapter never returns "valid" on behalf of the verifier.
- [ ] Time, randomness, and identity stay outside the commitment —
      `produced_at`, `receipt_id`, keys are caller-supplied inputs.
- [ ] Tests replay the conformance corpus through the adapter's own API
      where bytes could be mangled (databases, wire formats).

## What stays out of the core

- Blockchain libraries, RPC clients, wallet SDKs
- Model-provider SDKs (LLM calls are caller behavior, not protocol)
- Network fetch of payloads (a payload URL is data, not a fetch spec)
- Clock authority (`produced_at` is asserted, not attested)
- Key custody — signatures plug in 32-byte seeds; HSM/KMS integrations
  are application code
