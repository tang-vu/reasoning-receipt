"""Serverless deployment configuration must match local-file semantics."""

import json

import pytest
from fastapi import HTTPException

from server.deployment import load_deployment_config


@pytest.mark.parametrize("prefix", ["RR_AUDIT", "RR_SETTLEMENT"])
def test_inline_configuration_takes_precedence_over_local_file(prefix, tmp_path, monkeypatch):
    path = tmp_path / "deployment.json"
    path.write_text('{"enabled": false}')
    expected = {"enabled": True, "chain_id": 5042002, "recipient": "configured recipient"}
    monkeypatch.setenv(f"{prefix}_CONFIG", str(path))
    monkeypatch.setenv(f"{prefix}_CONFIG_JSON", json.dumps(expected))
    assert load_deployment_config(prefix) == expected


@pytest.mark.parametrize("raw", ["not JSON", "[]", "null", '"string"'])
def test_invalid_inline_configuration_never_falls_back_or_leaks_content(raw, tmp_path, monkeypatch):
    path = tmp_path / "deployment.json"
    path.write_text('{"enabled": true}')
    monkeypatch.setenv("RR_AUDIT_CONFIG", str(path))
    monkeypatch.setenv("RR_AUDIT_CONFIG_JSON", raw)
    with pytest.raises(HTTPException) as error:
        load_deployment_config("RR_AUDIT")
    assert error.value.status_code == 503
    assert error.value.detail == "Deployment configuration is unavailable or invalid"


def test_missing_local_file_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("RR_AUDIT_CONFIG_JSON", raising=False)
    monkeypatch.setenv("RR_AUDIT_CONFIG", str(tmp_path / "absent.json"))
    with pytest.raises(HTTPException, match="503"):
        load_deployment_config("RR_AUDIT")


def test_empty_configuration_is_disabled_and_empty_inline_preserves_file(tmp_path, monkeypatch):
    monkeypatch.setenv("RR_AUDIT_CONFIG", "")
    monkeypatch.setenv("RR_AUDIT_CONFIG_JSON", "")
    assert load_deployment_config("RR_AUDIT") == {"enabled": False}
    path = tmp_path / "deployment.json"
    path.write_text('{"enabled": true}')
    monkeypatch.setenv("RR_AUDIT_CONFIG", str(path))
    assert load_deployment_config("RR_AUDIT") == {"enabled": True}


def test_audit_route_accepts_inline_configuration_and_still_requires_its_token(monkeypatch):
    from server.audit import next_audit

    config = {"enabled": True, "chain_id": 5042002, "registry": "0x" + "44" * 20, "auditor": "0x" + "55" * 20}
    monkeypatch.setenv("RR_AUDIT_CONFIG", "/absent/config.json")
    monkeypatch.setenv("RR_AUDIT_CONFIG_JSON", json.dumps(config))
    monkeypatch.setenv("RR_AUDIT_API_TOKEN", "test-audit-token")
    with pytest.raises(HTTPException) as error:
        next_audit(authorization=None)
    assert error.value.status_code == 401
    assert next_audit(authorization="Bearer test-audit-token") == {"status": "empty"}


def test_settlement_route_accepts_inline_configuration_and_keeps_the_audit_gate(monkeypatch):
    from server.settlement import PrepareRequest, prepare_settlement

    config = {"enabled": True, "chain_id": 5042002, "token": "0x" + "36" * 20,
              "recipient": "0x" + "22" * 20, "amount_units": "10000"}
    monkeypatch.setenv("RR_SETTLEMENT_CONFIG", "/absent/config.json")
    monkeypatch.setenv("RR_SETTLEMENT_CONFIG_JSON", json.dumps(config))
    monkeypatch.setenv("RR_SETTLEMENT_API_TOKEN", "test-settlement-token")
    monkeypatch.setenv("RR_SETTLEMENT_RPC_URL", "https://rpc.test")
    request = PrepareRequest(audit_id=123456, execution_account="0x" + "33" * 20, chain_id=5042002)
    with pytest.raises(HTTPException) as error:
        prepare_settlement(request, authorization="Bearer test-settlement-token")
    assert error.value.status_code == 404
