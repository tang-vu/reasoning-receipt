# Cross-language parity harness

Every SDK emitter builds a `reasoning-receipt/1` document for **one fixed
semantic input** and writes `<lang>.receipt.json` here:

| Language   | Emitter                                            | Output             |
|------------|----------------------------------------------------|--------------------|
| Python     | `scripts/parity/emit.py`                           | `py.receipt.json`  |
| TypeScript | `sdks/typescript/scripts/emit-parity.mjs`          | `ts.receipt.json`  |
| Rust       | `sdks/rust/examples/emit_parity.rs`                | `rs.receipt.json`  |

All emitters must produce a **byte-identical canonical document** —
receipt IDs, `produced_at`, `signed_at` and the Ed25519 seed are fixed
constants, so the Merkle root, receipt hash *and signatures* are fully
deterministic across implementations.

Each language also ships a checker that verifies every emitted document
and compares canonical bytes:

- `scripts/parity/check.py`
- `sdks/typescript/scripts/check-parity.mjs`
- `sdks/rust/examples/check_parity.rs`

The `protocol` job in `.github/workflows/ci.yml` runs the full 3×3
matrix: three emitters, three verifiers, nine cross-checks.

## Fixture spec

```text
subject:     "parity:cross-language"
receipt_id:  "rr-parity-0001"
produced_at: "2026-05-20T00:00:00Z"
metadata:    {"harness": "rr-parity/1", "unicode": "héllo wörld — 数据 ✓"}

nodes: intent{action,target}·meta{source}  policy{limit,rules}
       decision{approved,score=0.125}      outcome{status,emoji}

edges: decision →policy   evaluated_against
       decision →intent   produced
       outcome  →decision produced

signatures: ed25519 seed "0x0123456789abcdef"×4, signed_at fixed
            scope "receipt" (key_id "parity-key")
            scope "node:decision" (key_id "parity-key")
```
