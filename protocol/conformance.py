"""Conformance corpus runner — executes `conformance/vectors/*.json`.

Vector kinds:
- `canon`      — input value → canonical string (or tagged error)
- `receipt`    — build spec → derived commitments (or tagged error)
- `document`   — full envelope → verify_receipt report (valid + error codes)
- `proof`      — build spec + expected proof parts; or proof_document → bool
- `signature`  — build spec + sign params → deterministic sig + verify

Tagged inputs (`{"$rr": "…"}`) express values JSON literals can't:
  "nan" → NaN · "+inf"/"-inf" → ±Infinity · "-0" → -0.0

The same files drive every SDK's conformance suite.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .canon import canonical_bytes
from .errors import ReceiptError
from .receipt import (
    PortableReceipt,
    ReceiptEdge,
    ReceiptNode,
    verify_proof_document,
)
from .signatures import sign, verify_signatures
from .verify import verify_any

TAG = "$rr"
_TAGS = {"nan": float("nan"), "+inf": float("inf"), "-inf": float("-inf"), "-0": -0.0}


def _untag(value: Any) -> Any:
    if isinstance(value, dict):
        if set(value) == {TAG}:
            tag = value[TAG]
            if tag in _TAGS:
                return _TAGS[tag]
            raise ValueError(f"unknown tag {tag!r}")
        return {k: _untag(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_untag(v) for v in value]
    return value


def _build(spec: dict[str, Any]) -> PortableReceipt:
    nodes = [
        ReceiptNode(id=n["id"], kind=n["kind"], payload=_untag(n.get("payload")), meta=n.get("meta"))
        for n in spec.get("nodes", [])
    ]
    edges = [ReceiptEdge(src=e["from"], dst=e["to"], rel=e["rel"]) for e in spec.get("edges", [])]
    return PortableReceipt(
        subject=spec["subject"],
        metadata=spec.get("metadata", {}),
        nodes=nodes,
        edges=edges,
        receipt_id=spec.get("receipt_id", "rr-conformance"),
        produced_at=spec.get("produced_at", "2026-01-01T00:00:00Z"),
    )


def _run_canon(vector: dict[str, Any]) -> tuple[bool, str]:
    expect = vector["expect"]
    try:
        produced = canonical_bytes(_untag(vector["input"])).decode("utf-8")
    except ReceiptError as exc:
        if "error" in expect:
            return (expect["error"] == exc.code, f"error {exc.code} vs {expect['error']}")
        return (False, f"unexpected error {exc.code}: {exc}")
    if "error" in expect:
        return (False, f"expected error {expect['error']}, encoded fine")
    return (produced == expect["canonical"], "canonical bytes differ")


def _run_receipt(vector: dict[str, Any]) -> tuple[bool, str]:
    expect = vector["expect"]
    try:
        receipt = _build(vector["input"])
        envelope = receipt.committed_envelope()
    except ReceiptError as exc:
        if "error" in expect:
            return (expect["error"] == exc.code, f"error {exc.code} vs {expect['error']}")
        return (False, f"unexpected error {exc.code}: {exc}")
    if "error" in expect:
        return (False, f"expected error {expect['error']}, built fine")
    mismatches = []
    if envelope["node_hashes"] != expect["node_hashes"]:
        mismatches.append("node_hashes")
    if envelope["edge_hashes"] != expect["edge_hashes"]:
        mismatches.append("edge_hashes")
    if envelope["merkle_root"] != expect["merkle_root"]:
        mismatches.append("merkle_root")
    if "receipt_hash" in expect and receipt.receipt_hash() != expect["receipt_hash"]:
        mismatches.append("receipt_hash")
    if "canonical_envelope" in expect:
        produced = canonical_bytes(envelope).decode("utf-8")
        if produced != expect["canonical_envelope"]:
            mismatches.append("canonical_envelope")
    return (not mismatches, f"fields differ: {', '.join(mismatches)}")


def _run_document(vector: dict[str, Any]) -> tuple[bool, str]:
    expect = vector["expect"]
    document = _untag(vector["input"])
    report = verify_any(document)
    if report.valid != expect["valid"]:
        return (False, f"valid={report.valid} expected {expect['valid']} ({report.errors})")
    for code in expect.get("errors", []):
        if not any(code in e for e in report.errors):
            return (False, f"missing expected error code {code} in {report.errors}")
    return (True, "")


def _run_proof(vector: dict[str, Any]) -> tuple[bool, str]:
    expect = vector["expect"]
    if "proof_document" in vector:
        ok = verify_proof_document(_untag(vector["proof_document"]))
        return (ok == expect["verify"], f"verify={ok} expected {expect['verify']}")
    receipt = _build(vector["input"])
    if "node" in expect:
        try:
            proof_doc = receipt.proof_for(expect["node"])
        except KeyError:
            if "error" in expect:
                return (True, "")
            return (False, "node not found, no error expected")
    else:
        proof_doc = receipt.proof_for_edge(expect["edge_index"])
    if proof_doc["leaf"] != expect["leaf"]:
        return (False, "leaf differs")
    if proof_doc["proof"] != expect["proof"]:
        return (False, "proof siblings differ")
    if proof_doc["merkle_root"] != expect["merkle_root"]:
        return (False, "root differs")
    return (verify_proof_document(proof_doc), "generated proof does not verify")


def _run_signature(vector: dict[str, Any]) -> tuple[bool, str]:
    expect = vector["expect"]
    committed = _build(vector["input"]).committed_envelope()
    spec = vector["sign"]
    sig_obj = sign(
        committed,
        spec["private_key"],
        scope=spec.get("scope", "receipt"),
        key_id=spec.get("key_id"),
        signed_at=spec.get("signed_at"),
    )
    if "public_key" in expect and sig_obj["public_key"] != expect["public_key"]:
        return (False, "public_key differs")
    if "sig" in expect and sig_obj["sig"] != expect["sig"]:
        return (False, "signature bytes differ")
    target = (
        _build(vector["verify_against"]).committed_envelope()
        if "verify_against" in vector
        else committed
    )
    results = verify_signatures(target, [sig_obj])
    ok = results[0]["valid"]
    return (ok == expect.get("valid", True), f"verify={ok}")


_RUNNERS = {
    "canon": _run_canon,
    "receipt": _run_receipt,
    "document": _run_document,
    "proof": _run_proof,
    "signature": _run_signature,
}


def run_vector_file(path: Path) -> dict[str, Any]:
    vector = json.loads(path.read_text(encoding="utf-8"))
    runner = _RUNNERS[vector["kind"]]
    try:
        ok, detail = runner(vector)
    except ReceiptError as exc:
        expect = vector.get("expect", {})
        ok = expect.get("error") == exc.code
        detail = f"error {exc.code}" + ("" if ok else f" (wanted {expect.get('error')})")
    except Exception as exc:  # noqa: BLE001 — a crash is a failed vector
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return {"name": vector.get("name", path.stem), "ok": ok, "detail": detail}


def run_corpus(vector_dir: Path) -> dict[str, Any]:
    files = sorted(Path(vector_dir).glob("*.json"))
    entries = [run_vector_file(f) for f in files]
    passed = sum(1 for e in entries if e["ok"])
    return {
        "vectors": entries,
        "total": len(entries),
        "passed": passed,
        "ok": passed == len(entries) and bool(entries),
        "implementation": "python",
    }
