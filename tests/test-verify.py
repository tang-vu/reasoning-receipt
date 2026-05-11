"""Verify endpoint — mock CID path + 404."""

from __future__ import annotations

import base64
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client() -> TestClient:
    from server.main import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


def _pay_for(client: TestClient, market_id: str) -> int:
    """Drive one full paid /price call, return the receipt_id."""
    ch = client.get(f"/price/{market_id}")
    accept = ch.json()["accepts"][0]
    payment = {
        "scheme": "exact",
        "network": accept["network"],
        "asset": accept["asset"],
        "amount": accept["amount"],
        "recipient": accept["recipient"],
        "nonce": accept["nonce"],
        "resource": accept["resource"],
        "payer": "0x" + "C" * 40,
        "signature": "0x" + "ab" * 32,
    }
    header = base64.b64encode(json.dumps(payment).encode()).decode()
    token = ch.headers["x-payment-challenge"]
    paid = client.get(
        f"/price/{market_id}",
        headers={"X-Payment": header, "X-Payment-Challenge": token},
    )
    return int(paid.json()["receipt_id"])


def test_verify_returns_404_for_unknown(client: TestClient) -> None:
    r = client.get("/verify/9999")
    assert r.status_code == 404


def test_verify_responds_for_mock_cid(client: TestClient) -> None:
    """In mock mode, the CID is a synthetic short hash so Irys fetch fails.
    The endpoint must still respond with verified=false + the stored values
    so a client can debug or re-fetch externally."""
    rid = _pay_for(client, "mock-polymarket-fed-rate-cut-jun-2026")
    r = client.get(f"/verify/{rid}")
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is False
    assert "trace fetch unavailable" in body["reason"]
    assert body["stored"]["id"] == rid
    assert body["stored"]["trace_hash"].startswith("0x")
    assert body["stored"]["trace_cid"].startswith("ar://")
    assert body["recomputed_hash"] is None
