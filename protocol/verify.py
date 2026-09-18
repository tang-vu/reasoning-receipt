"""Unified verification entry point — dispatch strictly on `schema_version`.

Never silently verifies a document under another version's rules. Every
report names the schema AND the canonicalization actually applied, so a
caller can always see exactly what was checked:

- `reasoning-receipt/1`        → spec rules (rr-json-1). If that fails and
                                  the document has no edges/signatures, the
                                  draft-era path is tried and reported as
                                  variant `draft` with legacy-json-6dp.
- `rr-trace/1`, `rr-trace/2`   → whole-blob legacy hash (no embedded
                                  commitment; report the recomputed hash).
- `rr-trace/3`                 → embedded node_hashes + merkle_root under
                                  legacy-json-6dp.
- anything else                → unsupported_schema, never downgraded.
"""

from __future__ import annotations

from typing import Any

from .legacy import (
    TRACE_BLOB_SCHEMAS,
    TRACE_DAG_SCHEMA,
    verify_receipt_draft,
    verify_trace3,
    verify_trace_blob,
)
from .receipt import SCHEMA_VERSION, VerifyReport, verify_receipt

KNOWN_SCHEMAS = [SCHEMA_VERSION, "rr-trace/3", "rr-trace/2", "rr-trace/1"]


def verify_any(
    document: dict[str, Any], *, expected_hash: str | None = None
) -> VerifyReport:
    """Verify `document` under the rules of its declared schema_version."""
    if not isinstance(document, dict):
        return VerifyReport(
            valid=False,
            schema_version="unknown",
            canonicalization="unknown",
            variant="unknown",
            checks={"shape": False},
            errors=["bad_type: document is not an object"],
        )

    schema = document.get("schema_version")

    if schema == SCHEMA_VERSION:
        report = verify_receipt(document)
        if report.valid:
            return report
        has_draft_shape = not any(
            key in document for key in ("edges", "edge_hashes", "signatures")
        )
        if has_draft_shape:
            draft = verify_receipt_draft(document)
            if draft.valid:
                return draft
        return report

    if schema in TRACE_BLOB_SCHEMAS:
        return verify_trace_blob(document, expected_hash=expected_hash)
    if schema == TRACE_DAG_SCHEMA:
        return verify_trace3(document)

    return VerifyReport(
        valid=False,
        schema_version=str(schema) if schema is not None else "missing",
        canonicalization="unknown",
        variant="unknown",
        checks={"shape": False},
        errors=[f"unsupported_schema: {schema!r} — refusing to verify under guessed rules"],
    )


def supported_schemas() -> list[dict[str, Any]]:
    """Machine-readable schema registry for `rr schemas` / /v1/schemas."""
    return [
        {
            "schema_version": SCHEMA_VERSION,
            "status": "current",
            "canonicalization": "rr-json-1",
            "features": ["nodes", "edges", "merkle_proofs", "signatures"],
        },
        {
            "schema_version": "rr-trace/3",
            "status": "legacy",
            "canonicalization": "legacy-json-6dp",
            "features": ["nodes", "merkle_proofs"],
        },
        {
            "schema_version": "rr-trace/2",
            "status": "legacy",
            "canonicalization": "legacy-json-6dp",
            "features": ["blob_hash"],
        },
        {
            "schema_version": "rr-trace/1",
            "status": "legacy",
            "canonicalization": "legacy-json-6dp",
            "features": ["blob_hash"],
        },
    ]
