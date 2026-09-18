# Conformance guide

How to prove an implementation speaks `reasoning-receipt/1` correctly —
and how to add coverage without breaking others.

## The corpus

`conformance/vectors/*.json` is the single source of truth. Every file is
one self-contained case:

```json
{
  "name": "receipt-minimal",
  "kind": "receipt",
  "input": { "...": "spec or document" },
  "expect": { "...": "expected outcome" }
}
```

`kind` selects the harness:

| kind | input | expect |
|---|---|---|
| `canon` | any JSON value (tags below allowed) | `canonical` bytes — or `error` code |
| `receipt` | builder spec `{subject, metadata, nodes, edges, receipt_id, produced_at}` | `node_hashes`, `edge_hashes`, `merkle_root`, `canonical_envelope`, `receipt_hash` — or `error` code |
| `document` | a complete receipt document | `valid` + expected `errors` codes |
| `proof` | builder spec + `expect.node` / `expect.edge_index`, or a full `proof_document` | `leaf`, `proof`, `merkle_root` — or `verify` bool |
| `signature` | builder spec + `sign` block | `public_key`, `sig`, verification outcomes |

### Tagged inputs (`{"$rr": "…"}`)

Values JSON literals cannot express are wrapped:
`"$rr": "nan" | "+inf" | "-inf" | "-0"`. Runners must unwrap tags before
handing the value to the implementation under test. Non-finite numbers
MUST be rejected with `noncanonical_value`.

## Running the corpus

```bash
# Python
uv run python -m protocol.cli conformance            # or: rr conformance

# TypeScript
cd sdks/typescript && npm test                        # vitest runs all vectors

# Rust
cd sdks/rust && cargo test --test conformance
```

Expected: `62/62` vectors pass in every implementation. The CI
`protocol` job enforces this.

## Implementing a new SDK

Minimum work to claim conformance:

1. Implement `canonical_bytes` per `spec/REASONING-RECEIPT-1.md` §7 —
   run every `canon` vector first; canonicalization bugs poison
   everything downstream.
2. Implement leaf hashing + sorted-pair Merkle (§9) — `receipt` vectors.
3. Implement validation + `verify_receipt` (§10) — `document` vectors.
4. Implement proofs (§12) — `proof` vectors.
5. Implement Ed25519 signatures (§8) — `signature` vectors.
6. Implement legacy dispatch if you accept historical documents —
   `document-*-legacy*` vectors.

Rules of engagement:

- Vector files are the contract — if your implementation disagrees with
  an expectation, the implementation is wrong until proven otherwise.
- Compare error **codes**, not messages.
- Do not special-case vector inputs; runners feed inputs through the
  same public API surface a user would call.

## Cross-language parity

`conformance/parity/` holds the deterministic emit/verify harness:
three emitters build one fixed receipt; three verifiers check all three
outputs are byte-identical *and* valid — a 3×3 matrix including Ed25519
signatures. See `conformance/parity/README.md`.

## Adding vectors

1. Add the case to `scripts/generate-conformance.py` (expected values
   are computed by the reference implementation — never hand-edit a
   vector).
2. Regenerate: `uv run python scripts/generate-conformance.py`.
3. Re-run all three conformance suites.
4. New vectors must be additive; changing an existing expected value is
   a protocol-level incident (see `docs/versioning.md`).

## Property and fuzz coverage

Beyond fixed vectors:

- `tests/test_protocol_properties.py` — Hypothesis property tests:
  canon fixed-point, key-order invariance, mutation sensitivity,
  proof locality, tamper rejection.
- `scripts/fuzz/fuzz.py` — seeded mutation fuzzing over byte mutation,
  canonicalization stability, and proof negatives.
  `uv run python scripts/fuzz/fuzz.py --iterations 500 --seed 0x5EED`
