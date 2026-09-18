# Versioning — schemas, canonicalization, releases

Three versioned surfaces, versioned independently on purpose.

## 1. Schema version (`schema_version`)

The receipt envelope format identifier — the `schema_version` field.

| Schema | Status |
|---|---|
| `reasoning-receipt/1` | **current** — the only schema producers should emit |
| `rr-trace/3`, `rr-trace/2`, `rr-trace/1` | frozen legacy — verification only |
| draft-era `reasoning-receipt/1` | frozen legacy — verification only (distinct canonicalization) |

Rules:

- Producers MUST emit exactly one schema version string.
- Verifiers MUST dispatch on `schema_version` and MUST reject unknown
  values — never guess, never reinterpret under a different schema.
- A new schema version is required for **any** change to: committed
  fields, node/edge structure, leaf construction, Merkle rules,
  canonicalization, or validation semantics.
- Within a schema version, only editorial fixes are allowed. If you are
  tempted to "clarify" observable behavior — that is a new version.

## 2. Canonicalization version (`canonicalization`)

The byte-encoding rules, identified in verification reports.

| ID | Used by |
|---|---|
| `rr-json-1` | `reasoning-receipt/1` |
| `legacy-json-6dp` | all `rr-trace/*` + draft `reasoning-receipt/1` |

Canonicalization changes are protocol changes: a different canonical
form means different hashes, so a canonicalization revision implies a
new schema version.

## 3. Package versions (`pyproject.toml`, `sdks/*/package.json`, `Cargo.toml`)

SDK release numbers — SemVer, independent per SDK but expected to stay
aligned while the protocol is young:

- `0.x.y` — protocol `reasoning-receipt/1` is a **release candidate**;
  compatibility rules below are enforced but the corpus may still grow.
- `1.0.0` per SDK is earned when: spec is stable, conformance corpus is
  stable, at least TypeScript + Python pass cross-language parity in CI,
  and the security review checklist in `docs/security-model.md` has been
  walked.

A patch bump = bug fixes with identical wire behavior. A minor bump =
new optional APIs. A major bump = anything that changes emitted bytes,
accepted inputs, or verification outcomes.

## Compatibility contract

- **Readers are liberal, writers are conservative.** Verifiers accept
  every schema they know under that schema's own rules; producers emit
  only the current schema.
- **Unknown fields are errors** inside `reasoning-receipt/1` documents
  (typo-resistance beats forward-compat for committed bytes). New
  optional fields therefore require a schema bump.
- **Unknown relations and kinds are fine** — the vocabularies are open
  (lowercase-snake regex only). Extension happens inside `payload` and
  `meta`, which are committed but uninterpreted.
- **Corpus is additive.** Vectors may be added for uncovered behavior;
  existing expected values change only if a bug in an implementation is
  discovered — and that is a protocol-level incident, documented in the
  CHANGELOG.

## Deprecation

Nothing is deleted silently. A legacy schema moves through:
`supported` → `verification-only` → `archived` (still verifies, but
tooling may warn). Historical receipts remain verifiable forever — the
frozen canonicalizers are never removed.
