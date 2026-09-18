# Legacy compatibility

Thousands of historical receipts exist under earlier schemas. They are
never reinterpreted under new rules — each verifies under the exact
semantics its `schema_version` declares, and verification reports say
which schema and canonicalization were applied.

## Schema dispatch table

| `schema_version` | Canonicalization | Commitment model | Status |
|---|---|---|---|
| `reasoning-receipt/1` | `rr-json-1` | domain-separated node/edge leaves, value-sorted leaf set, sorted-pair Merkle | **current** |
| `reasoning-receipt/1` (draft era) | `legacy-json-6dp` | undomain-separated leaves, ID-sorted | verification-only |
| `rr-trace/3` | `legacy-json-6dp` | embedded `node_hashes` + `merkle_root`, legacy leaf/hash shapes | verification-only |
| `rr-trace/2` | `legacy-json-6dp` | whole-document SHA-256 | verification-only |
| `rr-trace/1` | `legacy-json-6dp` | whole-document SHA-256 | verification-only |

Verification output fields identify what ran:

```json
{
  "schema_version": "rr-trace/3",
  "canonicalization": "legacy-json-6dp",
  "variant": "legacy",
  "valid": true
}
```

## How legacy verification works

`verify_any(document)` dispatches on `schema_version`:

- **`rr-trace/1`, `rr-trace/2`** — the whole blob was hashed with the
  frozen `legacy-json-6dp` encoder (`json.dumps` + `repr`-style floats,
  code-point key order). Verification recomputes `SHA-256(canonical)` and
  compares against the expected hash passed via `expected_hash` / anchor
  metadata.
- **`rr-trace/3`** — documents carry `node_hashes` + `merkle_root` under
  the legacy leaf model: leaves hashed without domain separation, sorted
  by node ID. Verification recomputes both.
- **draft `reasoning-receipt/1`** — the pre-freeze draft used legacy
  canonicalization and undomain-separated, ID-sorted leaves. Documents
  are detected by their structural shape (they lack final-form markers)
  and verified under draft rules.

The frozen encoder lives in `protocol/legacy_canon.py` — it exists for
verification only. Producers must not emit new documents under it.

## Upgrading a legacy receipt

There is no in-place upgrade — commitments are immutable by design. To
re-issue a historical receipt under `reasoning-receipt/1`:

1. Re-express the *semantic content* (subject, nodes, edges) as a new
   receipt — the node IDs and payload bytes may be reused if they were
   already in the new schema's domain.
2. Reference the original via `metadata`:
   `"supersedes": {"schema_version": "rr-trace/3", "trace_hash": "0x…"}`.
3. Emit, sign, and anchor the new receipt normally.

Never edit a committed document to "fix" it — a changed byte is a
different receipt.

## Guarantees

- Legacy verifiers are permanently frozen code paths; a protocol change
  can never alter a historical verdict.
- Unknown `schema_version` is rejected — a future document can never be
  silently verified under the wrong rules.
- Every verification report names the schema + canonicalization applied,
  so audit logs are unambiguous about what was checked.
