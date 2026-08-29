from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.cron import router as cron_router
from server.main import create_app
from storage.irys import IrysClient


def test_serverless_app_does_not_expose_process_local_sse() -> None:
    paths = {route.path for route in create_app(serverless=True).routes}
    assert "/events/stream" not in paths
    assert "/cron/agent-batch" in paths
    assert "/v1/receipts" in paths


def test_cron_requires_secret_and_can_be_disabled(monkeypatch) -> None:
    app = FastAPI()
    app.include_router(cron_router)
    client = TestClient(app)
    monkeypatch.setenv("CRON_SECRET", "test-cron-secret")
    monkeypatch.setenv("RR_CRON_AGENT_ENABLED", "0")

    assert client.get("/cron/agent-batch").status_code == 401
    response = client.get(
        "/cron/agent-batch",
        headers={"Authorization": "Bearer test-cron-secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "status": "disabled", "processed": 0}


def test_irys_client_can_use_remote_serverless_uploader(monkeypatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"id": "irys-tx", "cid": "ar://irys-tx"}

    seen: dict = {}

    def fake_post(url, *, content, headers, timeout):
        seen.update(url=url, content=content, headers=headers, timeout=timeout)
        return Response()

    monkeypatch.setattr("storage.irys.httpx.post", fake_post)
    client = IrysClient(
        mock=False,
        upload_url="https://api.example.test/api/irys-upload",
        upload_secret="upload-secret",
    )
    result = client.upload({"decision": "approve", "amount": 49.0})

    assert result.cid == "ar://irys-tx"
    assert result.is_mock is False
    assert seen["headers"]["Authorization"] == "Bearer upload-secret"
    assert seen["content"] == b'{"amount":49.0,"decision":"approve"}'
