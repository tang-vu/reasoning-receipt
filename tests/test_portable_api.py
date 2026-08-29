from __future__ import annotations

from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.portable import router

client = TestClient(FastAPI())
client.app.include_router(router)


def _create() -> dict:
    response = client.post(
        "/v1/receipts",
        json={
            "subject": "support:refund-approval",
            "metadata": {"workflow": "customer-support"},
            "nodes": [
                {"id": "intent", "kind": "request", "payload": {"refund_usd": 49}},
                {"id": "policy", "kind": "policy", "payload": {"limit_usd": 100}},
                {"id": "decision", "kind": "outcome", "payload": {"approved": True}},
            ],
        },
    )
    assert response.status_code == 201
    return response.json()


def test_create_verify_and_prove_domain_neutral_receipt() -> None:
    receipt = _create()
    assert receipt["schema_version"] == "reasoning-receipt/1"
    assert receipt["subject"] == "support:refund-approval"
    assert receipt["receipt_hash"]

    envelope = {key: value for key, value in receipt.items() if key != "receipt_hash"}
    verified = client.post("/v1/verify", json={"receipt": envelope})
    assert verified.status_code == 200
    assert verified.json()["valid"] is True
    assert verified.json()["node_count"] == 3

    proof = client.post("/v1/proofs", json={"receipt": envelope, "node_id": "policy"})
    assert proof.status_code == 200
    assert proof.json()["node"]["kind"] == "policy"


def test_verify_rejects_tampering() -> None:
    receipt = _create()
    receipt.pop("receipt_hash")
    tampered = deepcopy(receipt)
    tampered["nodes"][0]["payload"]["refund_usd"] = 499
    response = client.post("/v1/verify", json={"receipt": tampered})
    assert response.status_code == 200
    assert response.json() == {"valid": False}


def test_create_rejects_duplicate_node_ids() -> None:
    response = client.post(
        "/v1/receipts",
        json={
            "subject": "duplicate",
            "nodes": [
                {"id": "same", "kind": "input", "payload": {}},
                {"id": "same", "kind": "output", "payload": {}},
            ],
        },
    )
    assert response.status_code == 422
