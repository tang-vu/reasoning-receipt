# Security model — reasoning-receipt/1

What the protocol guarantees, what it does not, and the threats it is
designed against. Read this before trusting a receipt for anything.

## What a verified receipt actually proves

| Check | Meaning |
|---|---|
| `shape` | The document is well-formed `reasoning-receipt/1` — field types, ID/vocabulary regexes, limits, timestamps all pass |
| `graph` | The DAG is acyclic, non-self-looping, non-duplicated, and every edge lands on a declared node |
| `hashes` | Every `node_hashes[id]` / `edge_hashes[i]` matches `SHA-256(domain || canonical(item))` recomputed from the document |
| `root` | `merkle_root` matches the sorted-pair Merkle root recomputed over all leaves |
| `receipt_hash` | `receipt_hash` matches `SHA-256("RR1:receipt\x00" || canonical(committed_envelope))` — binds `subject`, `metadata`, `produced_at`, `receipt_id` (the fields that are *not* leaves) |
| `signatures` | Each listed signature verifies against its declared scope over the committed bytes |
| inclusion proof | A leaf's sibling path recomputes the root — proves the leaf is *in* the commitment |

"Verified" means **byte-level integrity + internal consistency**. It does
not mean the claims inside are true, authorized, or produced by the
entity you think produced them.

## Trust terminology — do not blur these

- **integrity verified** — bytes are exactly what the producer committed
- **signature verified** — some holder of this Ed25519 key signed this exact commitment
- **anchor verified** — the root appears in an external timestamped log (adapter-specific)
- **source fetched** — payload content was retrieved from a stated URL (no integrity claim about the source itself)
- **semantic claim unverified** — the payload says X; nothing here establishes X

A signature proves *possession of a key*, not identity, authority, or
truth of evidence. Key-to-identity binding is out of scope (use key
registries, PKI, or claims signed elsewhere).

## Threat model

| Threat | Mitigation |
|---|---|
| **Receipt substitution** | `receipt_hash` + Merkle root are recomputed, never trusted from the document; a swapped receipt is a different commitment |
| **Hash-algorithm confusion** | Domain-separated leaves (`RR1:node\x00`, `RR1:edge\x00`, `RR1:receipt\x00`) — a node leaf can never masquerade as an edge or receipt hash |
| **Version downgrade** | Verification is schema-dispatched; unknown `schema_version` is rejected, never guessed. Legacy schemas verify under *their own* frozen rules and report which schema ran |
| **Signature confusion** | `scope` binds the signed message (`receipt` vs `node:<id>`); a node signature can't be replayed as a receipt signature |
| **Proof substitution** | Proofs are direction-free sorted-pair; a proof verifies only its own leaf against its own root — sibling/path/tamper mutations fail (fuzz-tested) |
| **Duplicate node IDs / edges** | Explicitly rejected in graph validation — hash-map collisions can't hide a second node |
| **Canonicalization mismatch** | One normative spec + shared conformance corpus; all SDKs produce byte-identical output (CI-enforced 3×3) |
| **Huge-payload DoS** | Bounded: ≤1024 nodes, ≤4096 edges, ≤8 MiB envelope, ≤64 depth, ≤1 MiB strings, ≤256-byte keys |
| **Archive traversal (bundles)** | Bundle import rejects `..`, absolute paths, symlinks; file count and sizes bounded |
| **Malicious metadata** | Metadata is committed but never executed; verifiers treat all payload content as inert data |
| **Misleading provenance** | `produced_at` is a producer-asserted timestamp — the protocol does not timestamp anything itself; use an anchor adapter for time evidence |
| **Predictable-value disclosure** | A node hash commits to exact payload bytes — low-entropy payloads are dictionary-attackable. See below |

## Selective disclosure and redaction

The Merkle structure already supports **withholding**: you can reveal a
single node + its proof without revealing any other payload — the rest of
the receipt stays hidden behind hashes. This is a *hash commitment*, not
encryption and not zero-knowledge:

- An attacker who guesses a hidden payload can confirm the guess by hashing.
- Redact by **omission** (don't include the node at all) or by committing a
  salted digest (`payload = {"sha256": h(secret || salt)}`), never by hoping
  a hash hides a guessable value.

## Anchoring

Blockchain/storage anchoring is an **adapter** concern. The protocol's
contract with anchors: anchor `merkle_root` (or `receipt_hash`) + schema
version + optional receipt_id. Anchoring proves *existence at a point in
time* under the anchor's security model — nothing more.

## Operational notes

- Verification is total and offline: any conforming verifier reaches the
  same verdict for the same bytes. Distrust disagreement between
  verifiers — that's a conformance bug worth reporting.
- Keep `receipt_hash` and signatures in stored documents — without them,
  `subject`/`metadata`/`produced_at` are recommitted but unchecked.
- The verifier validates structure *and* hashes; do not write
  hash-only verifiers.
