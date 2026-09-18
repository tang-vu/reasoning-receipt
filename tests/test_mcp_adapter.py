"""Tests for the MCP adapter tools (direct calls — the tools are plain
functions; stdio transport is covered by the smoke path in the module docstring)."""

from __future__ import annotations

import pytest

mcp = pytest.importorskip("mcp", reason="mcp package not installed")

from protocol.mcp_server import (  # noqa: E402
    create_proof,
    create_receipt,
    inspect_receipt,
    verify_proof,
    verify_receipt,
)

DOC_SPEC = {
    "subject": "mcp:test",
    "nodes": [
        {"id": "intent", "kind": "intent", "payload": {"goal": "refund"}},
        {"id": "policy", "kind": "policy", "payload": {"limit": 100}},
        {"id": "decision", "kind": "decision", "payload": {"approved": True}},
    ],
    "edges": [
        {"from": "decision", "to": "policy", "rel": "evaluated_against"},
        {"from": "decision", "to": "intent", "rel": "produced"},
    ],
    "metadata": {"adapter": "mcp"},
    "receipt_id": "rr-mcp-test",
    "produced_at": "2026-05-20T00:00:00Z",
}


def test_create_verify_roundtrip():
    doc = create_receipt(**DOC_SPEC)
    assert doc["schema_version"] == "reasoning-receipt/1"
    report = verify_receipt(doc)
    assert report["valid"], report["errors"]
    assert report["node_count"] == 3
    assert report["edge_count"] == 2


def test_create_and_verify_proof():
    doc = create_receipt(**DOC_SPEC)
    proof = create_proof(doc, node_id="policy")
    assert proof["item_type"] == "node"
    assert proof["item"]["id"] == "policy"
    assert verify_proof(proof)["verify"] is True

    edge_proof = create_proof(doc, edge_index=0)
    assert edge_proof["item_type"] == "edge"
    assert verify_proof(edge_proof)["verify"] is True


def test_verify_rejects_tamper():
    doc = create_receipt(**DOC_SPEC)
    doc["nodes"][0]["payload"] = {"goal": "wire-fraud"}
    assert verify_receipt(doc)["valid"] is False


def test_inspect_reports_schema():
    doc = create_receipt(**DOC_SPEC)
    info = inspect_receipt(doc)
    assert info["schema_version"] == "reasoning-receipt/1"
    assert info["valid"] is True
    assert any(s["schema_version"] == "reasoning-receipt/1" for s in info["supported_schemas"])


def test_create_proof_requires_target():
    doc = create_receipt(**DOC_SPEC)
    with pytest.raises(ValueError):
        create_proof(doc)
