# Changelog

All notable changes to the protocol and SDKs. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning policy lives in `docs/versioning.md`.

## [Unreleased] — `reasoning-receipt/1` release candidate

### Added

- **Normative specification** `spec/REASONING-RECEIPT-1.md`: canonical
  JSON (`rr-json-1`), typed nodes, explicit DAG edges, domain-separated
  leaves, sorted-pair Merkle commitments, inclusion proofs, optional
  Ed25519 signatures, bounded inputs, stable error codes.
- **Python protocol core** (`protocol/`): builder, verifier, proofs,
  signatures, schema dispatch, legacy verification paths (`rr-trace/1-3`,
  draft `reasoning-receipt/1`), bundles, adapters, `rr` CLI.
- **Conformance corpus**: 62 language-independent vectors in
  `conformance/vectors/` covering canonicalization, Unicode, numbers,
  graphs, proofs, signatures, tampering and legacy behavior; generated
  by `scripts/generate-conformance.py`.
- **TypeScript SDK** (`sdks/typescript`): ESM, zero runtime deps beyond
  `@noble/hashes` + `@noble/ed25519`, full builder/verify/proof/sign
  surface — 62/62 vectors.
- **Rust SDK** (`sdks/rust`): `serde`/`sha2`/`ed25519-dalek`
  implementation with the same surface — 62/62 vectors.
- **Cross-language parity harness** (`conformance/parity/`): deterministic
  emitters in all three languages produce byte-identical canonical
  documents (signatures included); every verifier checks all outputs —
  a 3×3 matrix enforced in CI.
- **Reusable verify action** (`.github/actions/verify`): composite
  GitHub Action verifying committed receipt documents offline, plus a
  dogfood job in CI.
- **MCP adapter** (`protocol/mcp_server.py`): stdio server exposing
  `create_receipt`, `verify_receipt`, `create_proof`, `verify_proof`,
  `inspect_receipt`.
- **Property tests** (`tests/test_protocol_properties.py`, Hypothesis)
  and **seeded fuzz harness** (`scripts/fuzz/fuzz.py`) covering byte
  mutation, canon stability, and proof negatives.
- **Docs**: `docs/security-model.md`, `docs/versioning.md`,
  `docs/conformance.md`, `docs/adapters.md`,
  `docs/legacy-compatibility.md`, `docs/profiles.md`.
- **API**: `server/portable.py` consumes the protocol core for
  create/verify/proof with per-check verification reports.
- **Browser-safe TypeScript SDK**: all `Buffer` usage replaced with
  isomorphic `Uint8Array` hex helpers (`src/hex.ts`); the strict `0x`
  digest decoder is now exported as `digestBytes`. The SDK verifies
  receipts in any runtime — Node, browser, edge.
- **Dashboard `/verify`**: fully client-side offline receipt verifier —
  paste/upload/build-sample input, one-byte tamper demo, and the full
  verification report (checks, receipt hash, Merkle root, signature
  results, errors). Vendored SDK refreshed via `npm run sync-sdk`.

### Fixed

- **Canonicalization idempotence** (`canon-float-collapse`): values whose
  six-fraction-digit rendering collapses to an integer (`1e-7`,
  `999999.9999999`) now emit integer form — canonical output reparses to
  identical bytes. Spec §7.4 updated; all three SDKs fixed; corpus
  vector added. Found by property testing.
- Protocol package is now self-contained — no imports from `agent/`,
  `server/`, `storage/`, `wallets/`.

### Notes

- Protocol `reasoning-receipt/1` is a **release candidate**. `1.0`
  promotion criteria are in `docs/versioning.md`.
- Historical receipts (`rr-trace/1-3`, draft `reasoning-receipt/1`)
  remain verifiable under frozen legacy semantics — see
  `docs/legacy-compatibility.md`.

## [0.4.0] — 2026-05-15

Kalshi second venue, App Kit unified balance, Merkle inclusion
playground, paywalled MCP HTTP, cost knobs, dashboard hybrid refresh.
(See git history / release page for details.)
