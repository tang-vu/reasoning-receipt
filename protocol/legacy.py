"""Legacy schema verification — `rr-trace/1`, `rr-trace/2`, `rr-trace/3`,
and draft-era `reasoning-receipt/1` documents.

Thousands of historical receipts exist under these schemas, committed
on-chain. They are NEVER reinterpreted under `rr-json-1` rules — each is
verified under the exact rules it was produced with, and the report says
which canonicalization was used (`canonicalization` field).

- `rr-trace/1`, `rr-trace/2`: whole-blob schema. The committed hash lives
  outside the document (DB row / contract event), so verification here
  means: recompute `sha256(legacy_canon(doc))` and report it as
  `receipt_hash`; callers compare it to the anchored value. Structural
  sanity is checked lightly — the hash is the real commitment.
- `rr-trace/3`: embeds `node_hashes` + `merkle_root`. We re-extract the
  node dicts per the reference schema's rules, recompute every hash under
  `legacy-json-6dp`, rebuild the sorted-by-id leaf set, and compare.
- `reasoning-receipt/1` draft (2026-08-29 → spec freeze): same envelope
  but hashed under `legacy-json-6dp` with undomain-separated leaves and
  id-sorted leaves. Detected by successful verification under draft rules.
"""

from __future__ import annotations

from typing import Any

from . import merkle
from .errors import ReceiptError
from .legacy_canon import canonical_bytes as _legacy_canon
from .legacy_canon import sha256_hex as _legacy_sha256
from .receipt import (
    REQUIRED_FIELDS,
    SCHEMA_VERSION,
    VerifyReport,
    _check_no_controls,
)

LEGACY_CANON = "legacy-json-6dp"

TRACE_BLOB_SCHEMAS = {"rr-trace/1", "rr-trace/2"}
TRACE_DAG_SCHEMA = "rr-trace/3"

_CRITIC_DIMS = (
    "evidence_relevance",
    "falsifiability",
    "scope",
    "coherence",
    "exploration_integrity",
    "methodology",
)


def _bytes32(hex_str: str) -> bytes:
    raw = hex_str[2:] if isinstance(hex_str, str) and hex_str.startswith("0x") else hex_str
    return bytes.fromhex(raw)


def legacy_trace_hash(document: dict[str, Any]) -> str:
    """sha256_hex(legacy_canon(document)) — the whole-blob commitment."""
    return _legacy_sha256(_legacy_canon(document))


def verify_trace_blob(
    document: dict[str, Any], *, expected_hash: str | None = None
) -> VerifyReport:
    """Verify an rr-trace/1 or rr-trace/2 document.

    `expected_hash` is the anchored/DB-side hash when available — the
    document alone carries no commitment to compare against.
    """
    schema = str(document.get("schema_version"))
    errors: list[str] = []
    checks: dict[str, bool] = {}
    for field_name in ("market_id", "claim", "probability", "produced_at"):
        checks[f"has_{field_name}"] = field_name in document
        if not checks[f"has_{field_name}"]:
            errors.append(f"missing_field: {field_name}")
    try:
        recomputed = legacy_trace_hash(document)
        checks["canonicalizable"] = True
    except ReceiptError as exc:
        recomputed = None
        checks["canonicalizable"] = False
        errors.append(f"{exc.code}: {exc}")

    if expected_hash is not None:
        checks["hash_matches_expected"] = (
            recomputed is not None and recomputed.lower() == expected_hash.lower()
        )
        if not checks["hash_matches_expected"]:
            errors.append("hash_mismatch: recomputed hash != expected anchored hash")

    return VerifyReport(
        valid=all(checks.values()),
        schema_version=schema,
        canonicalization=LEGACY_CANON,
        variant=schema,
        checks=checks,
        errors=errors,
        receipt_hash=recomputed,
        merkle_root=None,
        node_count=0,
        edge_count=0,
    )


def _extract_trace3_nodes(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Rebuild the rr-trace/3 leaf dicts from a serialized trace.

    Mirrors `agent.trace_v3.ReasoningTraceV3.node_dicts` on plain JSON:
    claim, stances (minus evidence), flattened evidence, counter-arguments,
    sensitivity, falsifiable claims, and the six critic dimensions.
    """
    out: dict[str, dict[str, Any]] = {}
    claim = document.get("claim")
    if isinstance(claim, dict) and "id" in claim:
        out[claim["id"]] = dict(claim)
    for stance in document.get("stances") or []:
        if not isinstance(stance, dict) or "id" not in stance:
            continue
        sdict = dict(stance)
        evidence_list = sdict.pop("evidence", []) or []
        out[stance["id"]] = sdict
        for ev in evidence_list:
            if isinstance(ev, dict) and "id" in ev:
                out[ev["id"]] = dict(ev)
    for key in ("counter_arguments", "sensitivity", "falsifiable_claims"):
        for item in document.get(key) or []:
            if isinstance(item, dict) and "id" in item:
                out[item["id"]] = dict(item)
    audit = document.get("critic_audit") or {}
    for dim in _CRITIC_DIMS:
        if isinstance(audit.get(dim), dict):
            out[f"cd_{dim}"] = dict(audit[dim])
    return out


def verify_trace3(document: dict[str, Any]) -> VerifyReport:
    """Verify an rr-trace/3 document under legacy rules.

    Checks: embedded node_hashes match sha256(legacy_canon(node)) for every
    extractable node; merkle_root matches the sorted-by-id leaf set; the
    full-blob hash is recomputed and reported.
    """
    errors: list[str] = []
    checks: dict[str, bool] = {}
    nodes = _extract_trace3_nodes(document)
    checks["nodes_extracted"] = bool(nodes)
    if not nodes:
        errors.append("invalid_shape: no rr-trace/3 nodes could be extracted")

    embedded_hashes = document.get("node_hashes")
    checks["node_hashes_present"] = isinstance(embedded_hashes, dict) and bool(embedded_hashes)
    if not checks["node_hashes_present"]:
        errors.append("missing_field: 'node_hashes'")
        embedded_hashes = {}

    recomputed: dict[str, str] = {}
    for node_id, node_dict in nodes.items():
        recomputed[node_id] = _legacy_sha256(_legacy_canon(node_dict))
    checks["hashes"] = bool(embedded_hashes) and recomputed == embedded_hashes
    if embedded_hashes and recomputed != embedded_hashes:
        errors.append("hash_mismatch: embedded node_hashes != recomputed")

    embedded_root = document.get("merkle_root")
    root_hex: str | None = None
    if embedded_hashes:
        try:
            leaves = [_bytes32(embedded_hashes[i]) for i in sorted(embedded_hashes)]
            root_hex = "0x" + merkle.merkle_root(leaves).hex()
            checks["root"] = root_hex == embedded_root
            if not checks["root"]:
                errors.append("root_mismatch: embedded merkle_root != recomputed")
        except (ValueError, TypeError) as exc:
            checks["root"] = False
            errors.append(f"malformed_hash: {exc}")
    else:
        checks["root"] = False
        errors.append("missing_field: 'merkle_root'")

    try:
        blob_hash = legacy_trace_hash(document)
    except ReceiptError:
        blob_hash = None

    return VerifyReport(
        valid=all(checks.values()),
        schema_version=TRACE_DAG_SCHEMA,
        canonicalization=LEGACY_CANON,
        variant=TRACE_DAG_SCHEMA,
        checks=checks,
        errors=errors,
        receipt_hash=blob_hash,
        merkle_root=embedded_root if isinstance(embedded_root, str) else None,
        node_count=len(nodes),
        edge_count=0,
    )


def verify_receipt_draft(document: dict[str, Any]) -> VerifyReport:
    """Verify a draft-era `reasoning-receipt/1` document (legacy canon).

    Draft rules: leaf = sha256(legacy_canon(node_dict)); leaves sorted by
    node id; no edges/signatures fields; no domain separation.
    """
    errors: list[str] = []
    checks: dict[str, bool] = {}
    for field_name in sorted(REQUIRED_FIELDS - {"edge_hashes"}):
        checks[f"has_{field_name}"] = field_name in document
        if not checks[f"has_{field_name}"]:
            errors.append(f"missing_field: {field_name}")
    if document.get("schema_version") != SCHEMA_VERSION:
        errors.append("unsupported_schema: not reasoning-receipt/1")
        checks["schema"] = False
    else:
        checks["schema"] = True

    raw_nodes = document.get("nodes") or []
    ids = [n.get("id") for n in raw_nodes if isinstance(n, dict)]
    checks["unique_ids"] = len(ids) == len(set(ids)) and None not in ids
    checks["nonempty"] = bool(raw_nodes)

    try:
        subject = document.get("subject", "")
        if isinstance(subject, str):
            _check_no_controls(subject, what="subject", code="empty_subject")
    except ReceiptError as exc:
        checks["subject"] = False
        errors.append(f"{exc.code}: {exc}")

    recomputed: dict[str, str] = {}
    root_hex: str | None = None
    if checks.get("unique_ids") and raw_nodes:
        try:
            ordered = sorted(raw_nodes, key=lambda n: n["id"])
            for nd in ordered:
                recomputed[nd["id"]] = _legacy_sha256(_legacy_canon(nd))
            leaves = [_bytes32(recomputed[i]) for i in sorted(recomputed)]
            root_hex = "0x" + merkle.merkle_root(leaves).hex()
            checks["hashes"] = recomputed == document.get("node_hashes")
            checks["root"] = root_hex == document.get("merkle_root")
            if not checks["hashes"]:
                errors.append("hash_mismatch: node_hashes != recomputed (draft rules)")
            if not checks["root"]:
                errors.append("root_mismatch: merkle_root != recomputed (draft rules)")
        except (KeyError, TypeError, ValueError) as exc:
            checks["hashes"] = False
            errors.append(f"malformed: {exc}")

    return VerifyReport(
        valid=all(checks.values()) and bool(raw_nodes),
        schema_version=SCHEMA_VERSION,
        canonicalization=LEGACY_CANON,
        variant="draft",
        checks=checks,
        errors=errors,
        receipt_hash=None,
        merkle_root=document.get("merkle_root") if isinstance(document.get("merkle_root"), str) else None,
        node_count=len(raw_nodes),
        edge_count=0,
    )
