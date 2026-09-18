"""Generate the language-independent conformance corpus in conformance/vectors/.

Authoritative-first: every expected value is computed by the Python
implementation, then serialized. SDKs in other languages must reproduce
the same bytes/hashes/signature bytes from the same inputs.

    uv run python -m scripts.generate-conformance

Vector files are deterministic — regenerate freely; diffs mean the
implementation changed (or a bug was fixed and vectors need review).
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any

from protocol.canon import canonical_bytes
from protocol.conformance import _build, _untag  # noqa: PLC2701 — same package tool
from protocol.errors import ReceiptError
from protocol.receipt import verify_proof_document
from protocol.signatures import sign

OUT_DIR = Path(__file__).resolve().parent.parent / "conformance" / "vectors"

VECTORS: list[dict[str, Any]] = []


def vec(name: str, kind: str, **body: Any) -> None:
    VECTORS.append({"name": name, "kind": kind, **body})


# ------------------------------------------------------------------ canon


def canon_ok(name: str, value: Any) -> None:
    vec(name, "canon", input=value, expect={"canonical": canonical_bytes(_untag(value)).decode()})


def canon_err(name: str, value: Any, code: str) -> None:
    try:
        canonical_bytes(_untag(value))
    except ReceiptError as exc:
        assert exc.code == code, f"{name}: got {exc.code}, wanted {code}"
    else:
        raise AssertionError(f"{name}: expected {code}, encoded fine")
    vec(name, "canon", input=value, expect={"error": code})


# ---------------------------------------------------------------- receipt


def receipt_ok(name: str, spec: dict[str, Any], *, with_canonical: bool = True) -> None:
    receipt = _build(spec)
    env = receipt.committed_envelope()
    expect: dict[str, Any] = {
        "valid": True,
        "node_hashes": env["node_hashes"],
        "edge_hashes": env["edge_hashes"],
        "merkle_root": env["merkle_root"],
        "receipt_hash": receipt.receipt_hash(),
    }
    if with_canonical:
        expect["canonical_envelope"] = canonical_bytes(env).decode()
    vec(name, "receipt", input=spec, expect=expect)


def receipt_err(name: str, spec: dict[str, Any], code: str) -> None:
    try:
        _build(spec).to_dict()
    except ReceiptError as exc:
        assert exc.code == code, f"{name}: got {exc.code}, wanted {code}"
    else:
        raise AssertionError(f"{name}: expected {code}, built fine")
    vec(name, "receipt", input=spec, expect={"error": code})


# --------------------------------------------------------------- document


def document_vec(name: str, document: dict[str, Any], *, valid: bool, errors: list[str] | None = None) -> None:
    vec(name, "document", input=document, expect={"valid": valid, "errors": errors or []})


# ------------------------------------------------------------------ proof


def proof_vec(name: str, spec: dict[str, Any], *, node: str | None = None, edge_index: int | None = None) -> None:
    receipt = _build(spec)
    if node is not None:
        doc = receipt.proof_for(node)
        expect = {
            "node": node,
            "leaf": doc["leaf"],
            "proof": doc["proof"],
            "merkle_root": doc["merkle_root"],
        }
    else:
        doc = receipt.proof_for_edge(edge_index or 0)
        expect = {
            "edge_index": edge_index or 0,
            "leaf": doc["leaf"],
            "proof": doc["proof"],
            "merkle_root": doc["merkle_root"],
        }
    assert verify_proof_document(doc)
    vec(name, "proof", input=spec, expect=expect)


def proof_doc_vec(name: str, proof_document: dict[str, Any], *, verify: bool) -> None:
    assert verify_proof_document(proof_document) == verify
    vec(name, "proof", proof_document=proof_document, expect={"verify": verify})


# -------------------------------------------------------------- signature


def signature_vec(
    name: str,
    spec: dict[str, Any],
    *,
    private_key: str,
    scope: str = "receipt",
    key_id: str | None = None,
    signed_at: str = "2026-01-01T00:00:00Z",
    verify_against: dict[str, Any] | None = None,
    valid: bool = True,
) -> None:
    committed = _build(spec).committed_envelope()
    sig = sign(committed, private_key, scope=scope, key_id=key_id, signed_at=signed_at)
    expect: dict[str, Any] = {"valid": valid}
    if valid:
        expect["public_key"] = sig["public_key"]
        expect["sig"] = sig["sig"]
    body: dict[str, Any] = {
        "input": spec,
        "sign": {
            "private_key": private_key,
            "scope": scope,
            "signed_at": signed_at,
            **({"key_id": key_id} if key_id else {}),
        },
        "expect": expect,
    }
    if verify_against is not None:
        body["verify_against"] = verify_against
    vec(name, "signature", **body)


# ================================================================ vectors


REFUND_SPEC = {
    "subject": "support:refund-approval",
    "metadata": {"workflow": "customer-support", "channel": "email"},
    "receipt_id": "rr-conf-001",
    "produced_at": "2026-01-01T00:00:00Z",
    "nodes": [
        {"id": "decision", "kind": "decision", "payload": {"approved": True}},
        {"id": "intent", "kind": "intent", "payload": {"refund_usd": 49}},
        {"id": "policy", "kind": "policy", "payload": {"limit_usd": 100}},
    ],
    "edges": [
        {"from": "decision", "to": "policy", "rel": "evaluated_against"},
        {"from": "decision", "to": "intent", "rel": "produced"},
    ],
}

AGENT_SPEC = {
    "subject": "coding-agent:pr-42",
    "metadata": {"repo": "acme/widget", "base_sha": "cafebabe"},
    "receipt_id": "rr-conf-002",
    "produced_at": "2026-02-02T12:30:00Z",
    "nodes": [
        {"id": "intent", "kind": "intent", "payload": {"request": "fix flaky test"}},
        {"id": "policy", "kind": "policy", "payload": {"allow_paths": ["tests/"], "require_review": True}},
        {"id": "evidence", "kind": "evidence", "payload": {"test": "test_x", "failure_rate": 0.4}},
        {"id": "tool_call", "kind": "tool_call", "payload": {"tool": "edit_file", "path": "tests/test_x.py"}},
        {"id": "tool_result", "kind": "tool_result", "payload": {"diff_lines": 12}},
        {"id": "test_run", "kind": "tool_result", "payload": {"cmd": "pytest -q", "passed": 140, "failed": 0}},
        {"id": "approval", "kind": "approval", "payload": {"approver": "harvey", "method": "github-review"}},
        {"id": "commit", "kind": "execution", "payload": {"sha": "deadbeef"}},
        {"id": "outcome", "kind": "outcome", "payload": {"status": "merged"}},
    ],
    "edges": [
        {"from": "tool_call", "to": "policy", "rel": "evaluated_against"},
        {"from": "tool_result", "to": "tool_call", "rel": "returned"},
        {"from": "test_run", "to": "tool_result", "rel": "produced"},
        {"from": "commit", "to": "approval", "rel": "approved_by"},
        {"from": "outcome", "to": "commit", "rel": "caused"},
        {"from": "tool_call", "to": "intent", "rel": "derived_from"},
        {"from": "test_run", "to": "evidence", "rel": "supported_by"},
    ],
}


def main() -> int:
    # ---- canon: object ordering / structure --------------------------
    canon_ok("canon-key-order", {"b": 1, "a": [True, None, "x"], "m": {"y": 2, "b": 3}})
    canon_ok("canon-empty-structures", {"o": {}, "a": [], "s": ""})
    canon_ok("canon-nested", {"a": {"b": {"c": [{"d": [1, 2, {"e": None}]}]}}})
    canon_ok(
        "canon-unicode-key-order",
        {"z": 1, "ä": 2, "😀": 3, "a": 4, "Á": 5},
    )

    # ---- canon: strings ----------------------------------------------
    canon_ok("canon-escapes", {"s": 'quote " backslash \\ slash / tab\t nl\n cr\r bs\b ff\f'})
    canon_ok("canon-control-chars", {"s": ""})
    canon_ok("canon-unicode-emoji", {"s": "rocket 🚀✨", "cjk": "漢字かなカナ"})
    canon_ok("canon-combining-chars", {"nfc": "é", "nfd": "é", "hangul": "한"})
    canon_ok("canon-line-separators", {"s": "  "})

    # ---- canon: numbers ----------------------------------------------
    canon_ok("canon-integers", {"zero": 0, "neg": -7, "big": 9007199254740991, "negbig": -9007199254740991})
    canon_ok("canon-floats", {"p": 0.58, "q": -3.1415926535, "r": 0.1, "s": 123.4567891})
    canon_ok("canon-float-integral", {"five": 5.0, "neg": -2.0, "exp": 1e6})
    canon_ok("canon-float-rounding", {"up": 0.1234567, "down": 0.9999994, "tiny": 0.0000004, "negtiny": -0.0000004})
    canon_ok("canon-negative-zero", {"$rr": "-0"})
    canon_err("canon-err-nan", {"x": {"$rr": "nan"}}, "noncanonical_value")
    canon_err("canon-err-pos-inf", {"x": {"$rr": "+inf"}}, "noncanonical_value")
    canon_err("canon-err-neg-inf", {"x": {"$rr": "-inf"}}, "noncanonical_value")
    canon_err("canon-err-big-int", {"x": 9007199254740992}, "noncanonical_value")
    canon_err("canon-err-big-float", {"x": 1e20}, "noncanonical_value")
    canon_err("canon-err-depth", {"a": _nested(65)}, "limit_exceeded")
    canon_err("canon-err-lone-surrogate", {"s": "\ud800"}, "noncanonical_value")

    # ---- receipts: positive -------------------------------------------
    receipt_ok(
        "receipt-minimal",
        {
            "subject": "one-node",
            "receipt_id": "rr-conf-000",
            "produced_at": "2026-01-01T00:00:00Z",
            "nodes": [{"id": "only", "kind": "intent", "payload": {"x": 1}}],
        },
    )
    receipt_ok("receipt-refund", REFUND_SPEC)
    receipt_ok("receipt-agent-workflow", AGENT_SPEC)
    receipt_ok(
        "receipt-unicode-payload",
        {
            "subject": "unicode",
            "receipt_id": "rr-conf-003",
            "produced_at": "2026-03-03T03:03:03Z",
            "nodes": [
                {"id": "i18n", "kind": "evidence", "payload": {"text": "émoji 🚀 naïve 中文", "n": -0.25}}
            ],
        },
    )
    receipt_ok(
        "receipt-node-meta",
        {
            "subject": "meta",
            "receipt_id": "rr-conf-004",
            "produced_at": "2026-01-01T00:00:00Z",
            "nodes": [
                {
                    "id": "ev",
                    "kind": "evidence",
                    "payload": {"url": "https://x.example"},
                    "meta": {"redacted": True, "confidence": 0.9},
                }
            ],
        },
    )

    # ---- receipts: graph errors ---------------------------------------
    base = deepcopy(REFUND_SPEC)
    bad = deepcopy(base)
    bad["edges"].append({"from": "decision", "to": "ghost", "rel": "produced"})
    receipt_err("receipt-err-dangling-edge", bad, "dangling_edge")

    bad = deepcopy(base)
    bad["edges"].append({"from": "policy", "to": "decision", "rel": "produced"})
    bad["edges"].append({"from": "intent", "to": "decision", "rel": "produced"})
    receipt_err("receipt-err-cycle", bad, "cycle")

    bad = deepcopy(base)
    bad["edges"].append({"from": "decision", "to": "decision", "rel": "produced"})
    receipt_err("receipt-err-self-loop", bad, "self_loop")

    bad = deepcopy(base)
    bad["edges"].append({"from": "decision", "to": "policy", "rel": "evaluated_against"})
    receipt_err("receipt-err-duplicate-edge", bad, "duplicate_edge")

    bad = deepcopy(base)
    bad["nodes"].append({"id": "policy", "kind": "policy", "payload": {"x": 1}})
    receipt_err("receipt-err-duplicate-node-id", bad, "duplicate_node_id")

    bad = deepcopy(base)
    bad["nodes"] = []
    receipt_err("receipt-err-empty-nodes", bad, "empty_nodes")

    bad = deepcopy(base)
    bad["nodes"][0]["id"] = "has space"
    receipt_err("receipt-err-bad-node-id", bad, "invalid_node_id")

    bad = deepcopy(base)
    bad["nodes"][0]["kind"] = "Policy"
    receipt_err("receipt-err-bad-kind", bad, "invalid_kind")

    bad = deepcopy(base)
    bad["edges"][0]["rel"] = "EVAL"
    receipt_err("receipt-err-bad-rel", bad, "invalid_rel")

    bad = deepcopy(base)
    bad["produced_at"] = "2026-13-40T99:99:99Z"
    receipt_err("receipt-err-bad-timestamp", bad, "invalid_timestamp")

    # ---- documents: tampering / negatives -----------------------------
    doc = _build(REFUND_SPEC).to_dict()
    document_vec("document-valid-full", doc, valid=True)

    tampered = deepcopy(doc)
    tampered["nodes"][1]["payload"]["refund_usd"] = 49000
    document_vec("document-tampered-payload", tampered, valid=False, errors=["hash_mismatch"])

    tampered = deepcopy(doc)
    tampered["merkle_root"] = "0x" + "00" * 32
    document_vec("document-wrong-root", tampered, valid=False, errors=["root_mismatch"])

    tampered = deepcopy(doc)
    tampered["node_hashes"]["policy"] = "0x" + "11" * 32
    document_vec("document-wrong-node-hash", tampered, valid=False, errors=["hash_mismatch"])

    tampered = deepcopy(doc)
    tampered["receipt_hash"] = "0x" + "22" * 32
    document_vec("document-wrong-receipt-hash", tampered, valid=False, errors=["hash_mismatch"])

    tampered = deepcopy(doc)
    tampered["unknown_field"] = True
    document_vec("document-unknown-field", tampered, valid=False, errors=["unknown_field"])

    tampered = deepcopy(doc)
    del tampered["merkle_root"]
    document_vec("document-missing-field", tampered, valid=False, errors=["missing_field"])

    tampered = deepcopy(doc)
    tampered["schema_version"] = "reasoning-receipt/0"
    document_vec("document-bad-schema", tampered, valid=False, errors=["unsupported_schema"])

    tampered = deepcopy(doc)
    tampered["produced_at"] = "not-a-timestamp"
    document_vec("document-bad-timestamp", tampered, valid=False, errors=["invalid_timestamp"])

    tampered = deepcopy(doc)
    tampered["node_hashes"]["policy"] = "0xZZ"
    document_vec("document-malformed-hash", tampered, valid=False, errors=["malformed_hash"])

    tampered = deepcopy(doc)
    tampered["nodes"][0]["extra"] = 1
    document_vec("document-node-unknown-field", tampered, valid=False, errors=["unknown_field"])

    tampered = deepcopy(doc)
    tampered["edges"][0] = dict(tampered["edges"][1])  # exact triple duplicate
    document_vec("document-duplicate-edge", tampered, valid=False, errors=["duplicate_edge"])

    tampered = deepcopy(doc)
    tampered["nodes"] = list(reversed(tampered["nodes"]))
    document_vec("document-node-order-insensitive", tampered, valid=True)

    # draft-era /1 document: legacy canon + id-sorted leaves
    draft_doc = _make_draft_document()
    document_vec("document-draft-legacy", draft_doc, valid=True)

    # ---- proofs --------------------------------------------------------
    proof_vec("proof-node-policy", REFUND_SPEC, node="policy")
    proof_vec("proof-node-decision", REFUND_SPEC, node="decision")
    proof_vec("proof-edge-0", REFUND_SPEC, edge_index=0)
    proof_vec("proof-agent-node", AGENT_SPEC, node="test_run")

    good = _build(REFUND_SPEC).proof_for("policy")
    tampered = deepcopy(good)
    tampered["item"]["payload"]["limit_usd"] = 5
    proof_doc_vec("proof-tampered-item", tampered, verify=False)

    tampered = deepcopy(good)
    tampered["proof"][0] = "0x" + "ab" * 32
    proof_doc_vec("proof-tampered-sibling", tampered, verify=False)

    tampered = deepcopy(good)
    tampered["merkle_root"] = "0x" + "ff" * 32
    proof_doc_vec("proof-wrong-root", tampered, verify=False)

    other_leaf = _build(REFUND_SPEC).proof_for("intent")
    tampered = deepcopy(good)
    tampered["item"] = other_leaf["item"]
    tampered["leaf"] = other_leaf["leaf"]
    proof_doc_vec("proof-node-confusion", tampered, verify=False)

    # ---- signatures -----------------------------------------------------
    SEED_A = "0x" + bytes(range(32)).hex()
    SEED_B = "0x" + (b"\xff" * 32).hex()

    signature_vec("signature-receipt-scope", REFUND_SPEC, private_key=SEED_A, key_id="agent-01")
    signature_vec("signature-node-scope", AGENT_SPEC, private_key=SEED_B, scope="node:approval")

    mutated = deepcopy(REFUND_SPEC)
    mutated["nodes"][1]["payload"]["refund_usd"] = 49000
    signature_vec(
        "signature-wrong-message",
        REFUND_SPEC,
        private_key=SEED_A,
        verify_against=mutated,
        valid=False,
    )

    # ---- write -----------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.json"):
        old.unlink()
    for vector in VECTORS:
        path = OUT_DIR / f"{vector['name']}.json"
        try:
            text = json.dumps(vector, indent=2, ensure_ascii=False, sort_keys=True)
            path.write_text(text + "\n", encoding="utf-8")
        except UnicodeEncodeError:
            # Lone surrogates can't live in UTF-8 — keep them \uXXXX-escaped.
            text = json.dumps(vector, indent=2, ensure_ascii=True, sort_keys=True)
            path.write_text(text + "\n", encoding="utf-8")
    print(f"wrote {len(VECTORS)} vectors to {OUT_DIR}")
    return 0


def _nested(depth: int) -> Any:
    value: Any = {"leaf": 1}
    for _ in range(depth):
        value = {"a": value}
    return value


def _make_draft_document() -> dict[str, Any]:
    """Build a draft-era /1 envelope: legacy canon + id-sorted leaves."""
    from protocol import merkle
    from storage.irys import canonical_bytes as legacy_canon
    from storage.irys import sha256_hex

    nodes = [
        {"id": "decision", "kind": "outcome", "payload": {"approved": True}},
        {"id": "intent", "kind": "request", "payload": {"refund_usd": 49.0}},
        {"id": "policy", "kind": "policy", "payload": {"limit_usd": 100.0}},
    ]
    node_hashes = {n["id"]: sha256_hex(legacy_canon(n)) for n in nodes}
    leaves = [bytes.fromhex(node_hashes[i][2:]) for i in sorted(node_hashes)]
    return {
        "schema_version": "reasoning-receipt/1",
        "receipt_id": "rr-draft-001",
        "subject": "support:refund-approval",
        "produced_at": "2026-08-30T00:00:00Z",
        "metadata": {"workflow": "customer-support"},
        "nodes": nodes,
        "node_hashes": node_hashes,
        "merkle_root": "0x" + merkle.merkle_root(leaves).hex(),
    }


if __name__ == "__main__":
    sys.exit(main())
