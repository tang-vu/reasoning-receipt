# ReasoningReceipt Protocol — `reasoning-receipt/1`

**Status:** Release candidate (v0.5.0-rc). The schema identifier is frozen as
`reasoning-receipt/1`; the canonicalization and commitment rules in this
document are authoritative for all receipts carrying that identifier.

**Audience:** implementers of producers, verifiers, SDKs, and adapters.

> ReasoningReceipt produces **portable, byte-verifiable evidence receipts**
> for AI decisions and actions. A receipt commits intent, evidence, policy
> checks, tool calls, approvals, execution and outcomes as independently
> provable nodes under one Merkle root. Any conforming implementation —
> in any language, on any machine, offline — derives the same bytes, the
> same hashes, and the same verdict.

---

## 0. Conformance language

The key words **MUST**, **MUST NOT**, **SHOULD**, **SHOULD NOT**, and **MAY**
are to be interpreted as in RFC 2119 / RFC 8174.

"SHA-256" means the hash function defined in FIPS 180-4. Hex strings are
lowercase and `0x`-prefixed unless stated otherwise.

## 1. Scope and trust model

A ReasoningReceipt receipt attests to **byte-level integrity**: that a
specific set of typed nodes and edges existed in a specific canonical form.

Integrity is not truth. A verified receipt proves *what bytes were committed*,
not that the evidence is accurate, the decision was correct, or the signer is
who they claim to be. Signatures prove possession of a private key — nothing
more. See `docs/SECURITY-MODEL.md` for the full threat model and required
verifier terminology (`integrity verified`, `signature verified`,
`anchor verified`, `source fetched`, `semantic claim unverified`).

## 2. Receipt envelope

A receipt is a single JSON object — the **envelope** — with these fields:

| Field | Type | Req | Description |
|---|---|---|---|
| `schema_version` | string | ✓ | MUST be exactly `"reasoning-receipt/1"`. |
| `receipt_id` | string | ✓ | Instance identity. 1–128 chars, no control chars. See §10. |
| `subject` | string | ✓ | What this receipt is about. 1–500 chars, no control chars. |
| `produced_at` | string | ✓ | Timestamp, strict form `YYYY-MM-DDTHH:MM:SSZ` (UTC, second precision). MUST be a real calendar date/time. |
| `metadata` | object | — | Open extension map. Default `{}`. |
| `nodes` | array | ✓ | ≥ 1 node objects (§3). Unique `id`s. |
| `edges` | array | — | Relationship triples (§4). Default `[]`. |
| `node_hashes` | object | ✓ | Derived map `id → leaf hex` (§5). |
| `edge_hashes` | array | ✓ | Derived list of edge leaf hexes, parallel to canonically-sorted `edges`. `[]` when no edges. |
| `merkle_root` | string | ✓ | Derived `0x`-hex Merkle root (§6). |
| `signatures` | array | — | Optional signature objects (§8). Default `[]`. **Not part of the committed envelope.** |

The envelope is **closed**: fields outside this table MUST NOT appear at the
top level. Verifiers MUST reject envelopes with unknown top-level fields.
Extension data lives in `metadata` (open), node `meta` (open), or node
`payload` (open).

All derived fields (`node_hashes`, `edge_hashes`, `merkle_root`) are
**recomputed** by verifiers from `nodes`/`edges` alone. A verifier never
trusts supplied derived values.

## 3. Nodes

A node is one independently provable fact in a decision/action trace:

```json
{ "id": "policy", "kind": "policy", "payload": { "limit_usd": 100 } }
```

| Field | Type | Req | Rule |
|---|---|---|---|
| `id` | string | ✓ | `^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$`. Unique within the receipt. |
| `kind` | string | ✓ | `^[a-z][a-z0-9_]{0,63}$`. Open vocabulary; recommended set below. |
| `payload` | any JSON value | ✓ | The committed content. `null`/`{}`/`[]` all legal. |
| `meta` | object | — | Optional uncommitted-shape extension map (committed in hash). |

Recommended `kind` vocabulary (non-normative — verifiers MUST NOT reject
unknown kinds): `intent`, `request`, `constraint`, `policy`, `evidence`,
`claim`, `decision`, `approval`, `tool_call`, `tool_result`, `execution`,
`state_change`, `outcome`, `error`, `review`, `attestation`.

Producers MUST emit `nodes` sorted by `id` ascending (UTF-8 byte order).
Verifiers MUST sort before checking — input order is not significant.

## 4. Edges and graph semantics

Edges make relationships between nodes explicit:

```json
{ "from": "decision", "to": "policy", "rel": "evaluated_against" }
```

| Field | Rule |
|---|---|
| `from`, `to` | MUST equal the `id` of a node in this receipt. |
| `rel` | `^[a-z][a-z0-9_]{0,63}$`. Open vocabulary; recommended: `evaluated_against`, `supported_by`, `produced`, `approved_by`, `invoked`, `returned`, `caused`, `derived_from`, `reviewed_by`, `attested_by`, `supersedes`. |

Rules — all enforced by producers AND checked by verifiers:

1. `from` and `to` MUST reference existing node ids (no dangling edges).
2. `from != to` (no self-loops).
3. The triple `(from, to, rel)` MUST be unique (no duplicate edges).
4. The edge set MUST form a **DAG**: no directed cycles exist.
5. Orphan nodes (no incident edges) are legal.
6. Edges are optional entirely; receipts without edges are valid.

Producers MUST emit `edges` sorted by `(from, to, rel)` ascending (UTF-8
byte order, element-wise). Verifiers MUST sort before checking.

The same `(from, to)` pair MAY appear with different `rel`s — e.g.
`decision -approved_by→ approval` and `decision -derived_from→ claim`.

## 5. Node hashing and leaf construction

Every committed item — each node and each edge — becomes exactly one
32-byte Merkle **leaf**:

```
leaf(node) = SHA-256( "RR1:node\x00" ‖ canonical_bytes(node_dict) )
leaf(edge) = SHA-256( "RR1:edge\x00" ‖ canonical_bytes(edge_dict) )
```

where `‖` is byte concatenation and `node_dict`/`edge_dict` are the JSON
objects of §3/§4 encoded per §7. The `\x00` is a literal NUL byte; the
prefix `RR1:node` / `RR1:edge` is domain separation — a node preimage can
never collide with an edge preimage or with a bare `sha256(json)` digest.

`node_hashes` maps each node `id` to its `0x`-hex leaf. `edge_hashes` lists
each edge's `0x`-hex leaf in the canonically-sorted edge order.

## 6. Merkle tree and root

The receipt commits one SHA-256 binary Merkle root over the leaf set:

1. `leaves` = all node leaves ∪ all edge leaves, **sorted ascending by
   their 32-byte value** (unsigned byte comparison).
2. Build levels bottom-up. For each pair `(a, b)` compute the parent as
   `SHA-256( min(a,b) ‖ max(a,b) )` — the **sorted-pair** rule, matching
   OpenZeppelin's convention with SHA-256 substituted for keccak256.
3. If a level has an odd node count, the last node is **promoted**
   unchanged to the next level (never duplicated).
4. A single-leaf tree's root is the leaf itself. An empty leaf set is
   impossible (envelopes require ≥ 1 node).

`merkle_root` = `0x` ‖ lowercase hex of the final root.

This is byte-identical to the algorithm implemented by the deployed
`ReceiptRegistryV2.verifyInclusion` contract — an off-chain proof generated
per this spec verifies on-chain unchanged.

## 7. Canonical encoding — RR-Canonical-JSON-1

Hash inputs are **exact byte sequences**. Any implementation producing
different bytes for the same value breaks verification. This section is the
complete encoding contract.

### 7.1 Value domain

Canonical input is any JSON value built from: `null`, booleans, integers,
non-integer numbers, strings, arrays, objects. Out of domain — MUST be
rejected with an error, never silently coerced:

- `NaN`, `+Infinity`, `-Infinity`
- integers outside `[-(2^53−1), 2^53−1]` (the portable-integer range)
- strings containing unpaired surrogates or non-character code points
  (input must be a valid Unicode scalar sequence)
- object members with duplicate keys
- non-string object keys, non-JSON types (functions, symbols, bytes,
  `BigInt`, `Decimal`, `datetime`, …)

### 7.2 Structure encoding

- Output is UTF-8, no BOM, **zero insignificant whitespace**.
- `null` → `null`; `true` → `true`; `false` → `false`.
- Arrays: `[` then elements comma-separated then `]`. Order preserved.
- Objects: `{` then members comma-separated then `}`. Members sorted by
  the **UTF-8 byte sequence of the key string**, ascending. (Equivalent to
  Unicode code-point order; for ASCII keys it is plain lexicographic order.)
- Empty array → `[]`; empty object → `{}`.

### 7.3 String encoding

- Escape **only**: `"` → `\"`, `\` → `\\`, `\b` → `\b`, `\f` → `\f`,
  `\n` → `\n`, `\r` → `\r`, `\t` → `\t`.
- Other C0 control characters (U+0000–U+001F not listed above) → `\u00XX`
  with lowercase hex (e.g. `\u0001`).
- Every other character — including all non-ASCII (emoji, CJK, combining
  marks), `/`, DEL, U+2028/2029 — is emitted **literally** as UTF-8.
  No `\uXXXX` escaping for characters ≥ U+0020.
- **No Unicode normalization is applied.** `é` (NFC, U+00E9) and
  `e` + `◌́` (NFD, U+0065 U+0301) hash differently. Producers SHOULD emit
  NFC; verifiers MUST NOT normalize — the receipt commits bytes, not
  interpretations.

### 7.4 Number encoding

Encoding is by **value**, not by lexical type — JSON has a single number
type and parse-time integer/real distinctions are not portable across
languages (`JSON.parse("5.0")` and `JSON.parse("5")` are indistinguishable).

- Reject `NaN`, `+Infinity`, `-Infinity`, and any value with
  `|v| ≥ 2^53` (outside the portable range).
- **Integral values** → decimal digits, no leading zeros, `-` only for
  negatives: `0`, `42`, `-7`. A value `v` is integral iff `v = trunc(v)`;
  this covers `5` and `5.0` identically — both encode as `5`.
- **Non-integral values** → fixed-point with **exactly six fraction
  digits**, round-to-nearest at the 7th digit (a binary64 value can never
  sit exactly on a 7th-digit tie, so tie-breaking is unobservable):
  `0.580000`, `-3.141593`, `0.000001`.
- **Integer-collapse rule** — if the six-fraction-digit rendering is
  integral (ends in `.000000`), the fractional part is dropped and the
  integer form is emitted: `1e-7` → `0.000000` → `0`;
  `999999.9999999` → `1000000.000000` → `1000000`. This keeps
  canonicalization a fixed point: `canon(parse(canon(x))) = canon(x)`.
- `-0.0` and any value rounding to zero magnitude → `0`
  (no negative zero in canonical form).
- Consequence: non-integral numbers are quantized to 1e-6. Producers
  needing arbitrary precision MUST use decimal strings
  (e.g. `"0.123456789"`), which are hashed as strings.

### 7.5 Canonicalization is total

`canonical_bytes` is a pure function `value → bytes | error`. It performs
no I/O, no network, no clock reads, no normalization of semantic content.
Two conforming implementations MUST produce byte-identical output for
every in-domain input.

## 8. Signatures (optional)

Signatures bind a **key** to a committed value. They live in the
`signatures` array — **outside** the committed envelope, so adding or
removing a signature never changes `merkle_root` or `receipt_hash`.
Unsigned receipts are fully valid.

Signature object:

```json
{
  "alg": "ed25519",
  "scope": "receipt",
  "public_key": "0x<32-byte hex>",
  "sig": "0x<64-byte hex>",
  "signed_at": "2026-09-18T12:00:00Z",
  "key_id": "agent-wallet-01",
  "meta": {}
}
```

| Field | Rule |
|---|---|
| `alg` | `"ed25519"` only in this version. Unknown `alg` → that signature is `unverifiable`, never `valid`. |
| `scope` | `"receipt"` signs the whole envelope; `"node:<id>"` signs one node leaf. |
| `public_key` | 32-byte Ed25519 public key, `0x`-hex. |
| `sig` | 64-byte Ed25519 signature, `0x`-hex. |
| `signed_at` | Same timestamp rule as `produced_at`. |
| `key_id`, `meta` | Optional opaque hints (never signed over identity claims). |

Signed preimage:

```
scope == "receipt"    →  "RR1:sig:receipt\x00" ‖ <32-byte receipt_hash>
scope == "node:<id>"  →  "RR1:sig:node\x00"    ‖ <32-byte node leaf>
```

`receipt_hash` (§9) is what a `receipt`-scope signature commits to — a
signer therefore binds to the full envelope, not just the Merkle root.

Multiple signers compose naturally: an agent signs `receipt`, a human signs
`node:approval`, an auditor countersigns `receipt` later — each signature is
independent and order-free.

**A valid signature proves only**: the holder of the private key for
`public_key` signed this exact commitment. It does not prove human
identity, organizational authority, or evidence truth.

## 9. Receipt hash and identities

```
receipt_hash = "0x" ‖ hex( SHA-256( "RR1:receipt\x00" ‖ canonical_bytes(committed_envelope) ) )
```

where `committed_envelope` is the envelope object **without** the
`signatures` field.

Two identities are deliberately distinct (§ idempotency):

- **Content identity** — `merkle_root` + `receipt_hash`. Deterministic:
  identical `nodes`/`edges`/`subject`/… produce identical values.
- **Instance identity** — `receipt_id`. Chosen by the producer; two
  identical decisions issued twice SHOULD get distinct `receipt_id`s but
  identical content commitments.

## 10. Verification

`verify(document) → report`. A conforming verifier performs, in order:

1. **Shape** — parse JSON; reject non-objects, unknown top-level fields,
   missing required fields, out-of-range scalars (id/kind/rel patterns,
   timestamp form, limits in §11).
2. **Graph** — unique node ids; edge endpoints exist; no self-loops;
   unique edge triples; DAG (no cycles).
3. **Node hashes** — recompute each leaf; compare to `node_hashes` /
   `edge_hashes`.
4. **Root** — rebuild sorted leaf set, recompute Merkle root, compare to
   `merkle_root`.
5. **Receipt hash** (when requested) — recompute over committed envelope.
6. **Signatures** (when present) — check each per §8. A receipt with a
   failed signature reports `integrity valid, signature invalid` — the
   failure is reported per-signature, never silently.

Outcomes are reported per-check, not collapsed into one boolean:
`{ valid: bool, schema_version, checks: {shape, graph, hashes, root,
signatures[]}, errors: [...] }`. `valid` = all structural+commitment checks
passed (signatures excluded from `valid` unless the caller requires them —
a verifier MUST let the caller see unsigned-but-valid vs signed states).

Unknown `schema_version` → `unsupported_schema`, NEVER silently verified
under another version's rules.

## 11. Practical limits

Verifiers SHOULD enforce (defaults a conforming implementation MUST
accept):

| Limit | Value |
|---|---|
| Envelope canonical size | ≤ 8 MiB |
| Nodes | ≤ 1024 |
| Edges | ≤ 4096 |
| Payload nesting depth | ≤ 64 |
| Object key length | ≤ 256 chars |
| String value length | ≤ 1 MiB |
| `id`/`kind`/`rel` | patterns in §3/§4 |

## 12. Inclusion proofs

A proof for committed item `x` (node or edge):

```json
{
  "schema_version": "reasoning-receipt/1",
  "item_type": "node",          // or "edge"
  "item": { ... },              // the node/edge dict
  "leaf": "0x<32-byte leaf>",
  "merkle_root": "0x<root>",
  "proof": ["0x<sibling>", ...] // bottom-up
}
```

Verification: recompute `leaf` from `item` (§5), fold with siblings via
the sorted-pair rule (§6), compare to `merkle_root`. Any deviation →
invalid. Proofs are direction-free (sorted pairs need no left/right
positions) and ~32 bytes per tree level (~200 B for 1024 leaves).

## 13. Versioning and compatibility

- `schema_version` = `"reasoning-receipt/" N`. Within `N=1`, only
  backward-compatible additions are permitted: new optional top-level
  fields (old verifiers MUST reject unknown fields — so in practice all
  additions land in `metadata`/`meta`/`payload`), new `kind`/`rel`
  vocabulary, new `alg` values.
- Any change to canonicalization, hashing, leaf construction, Merkle
  rules, envelope shape, or validation semantics → `reasoning-receipt/2`.
- Verifiers dispatch strictly on `schema_version`. See `docs/LEGACY.md`
  for `rr-trace/2`, `rr-trace/3`, and `reasoning-receipt/1` draft-era
  verification rules.
- The `/1` **draft period** (2026-08-29 → this spec): early portable-API
  receipts used a different canonicalization (`legacy-json-6dp`, §14) and
  no edges/signatures. The unified verifier detects and reports them as
  `reasoning-receipt/1-draft`. Nothing under that draft was anchored
  on-chain; producers SHOULD re-emit under this spec.

## 14. Registered canonicalizations

| Id | Used by | Definition |
|---|---|---|
| `rr-json-1` | `reasoning-receipt/1` | §7 of this document. |
| `legacy-json-6dp` | `rr-trace/2`, `rr-trace/3`, `/1` drafts | `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True)` over input where every float is first rounded via `float(f"{x:.6f}")`. Kept verbatim in `storage/irys.py::canonical_bytes`; see `docs/LEGACY.md`. |

## 15. Bundles (informative pointer)

Receipts travel inside `.rrbundle` JSON containers — manifest + embedded
files, no archive formats, no path traversal surface. See
`docs/BUNDLES.md` and `protocol/bundle.py`.

## 16. Conformance

`conformance/vectors/*.json` is the normative machine-readable corpus.
An implementation is conforming when `rr conformance` (or its equivalent
runner) passes every positive vector and rejects every negative vector
with the expected error class. See `docs/CONFORMANCE.md`.
