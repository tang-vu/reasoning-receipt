"""Settlement acceptance: published audits only, configured transfer only,
simulation gate, verified finality, and one linked outcome receipt per audit."""

from __future__ import annotations

import itertools
import json
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select, text

from protocol.receipt import verify_receipt
from server.settlement import TRANSFER_TOPIC
from server.settlement import router as settlement_router
from storage.db import Audit as AuditRow
from storage.db import Session
from storage.db import Settlement as SettlementRow

RPC = "https://rpc.test/arc"
CHAIN = 5_042_002
USDC = "0x3600000000000000000000000000000000000000"
RECIPIENT = "0x" + "22" * 20
PAYER = "0x" + "33" * 20
AUTH = {"Authorization": "Bearer settlement-test-token"}
TX = "0x" + "aa" * 32
OTHER_TX = "0x" + "bb" * 32

app = FastAPI()
app.include_router(settlement_router)
client = TestClient(app)


def word(value: str | int) -> str:
    return "0x" + (value[2:] if isinstance(value, str) else f"{value:x}").rjust(64, "0")


def transfer_log(*, frm=PAYER, to=RECIPIENT, amount=10_000, token=USDC, index=0) -> dict:
    return {
        "address": token,
        "topics": [TRANSFER_TOPIC, word(frm), word(to)],
        "data": word(amount),
        "logIndex": hex(index),
    }


class FakeChain:
    """Just enough JSON-RPC for the settlement routes."""

    def __init__(self) -> None:
        self.chain_id = CHAIN
        self.call = {"result": word(1)}
        self.receipts: dict[str, dict] = {}
        self.finalized = 100
        self.latest = 80
        self.blocks = {hex(n): "0x" + f"{n:064x}" for n in range(1, 200)}

    def mine(self, tx: str, *, status="0x1", block=90, logs=None) -> None:
        self.receipts[tx] = {
            "status": status,
            "blockNumber": hex(block),
            "blockHash": self.blocks[hex(block)],
            "logs": [transfer_log()] if logs is None else logs,
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method, params = body["method"], body["params"]
        if method == "eth_chainId":
            reply = {"result": hex(self.chain_id)}
        elif method == "eth_call":
            reply = self.call
        elif method == "eth_getTransactionReceipt":
            reply = {"result": self.receipts.get(params[0])}
        elif params[0] == "finalized":
            reply = {"result": {"number": hex(self.finalized)}}
        elif params[0] == "latest":
            reply = {"result": {"number": hex(self.latest), "hash": self.blocks[hex(self.latest)]}}
        else:
            reply = {"result": {"hash": self.blocks[params[0]]}}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, **reply})


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "settlement-deployment.json"
    config.write_text(
        json.dumps(
            {
                "enabled": True,
                "chain_id": CHAIN,
                "token": USDC,
                "recipient": RECIPIENT,
                "amount_units": "10000",
                "api_url": "https://api.example",
            }
        )
    )
    monkeypatch.setenv("RR_SETTLEMENT_CONFIG", str(config))
    monkeypatch.setenv("RR_SETTLEMENT_API_TOKEN", "settlement-test-token")
    monkeypatch.setenv("RR_SETTLEMENT_RPC_URL", RPC)
    fake = FakeChain()
    with respx.mock(assert_all_called=False) as mock:
        mock.post(RPC).mock(side_effect=fake)
        yield fake


_serial = itertools.count(1)


def audit(status: str = "published") -> int:
    """Store one audit in ``status``; only ``published`` ones went on chain."""
    n = next(_serial)
    done = status == "published"
    with Session() as s:
        row = AuditRow(
            market_id=f"market-{n}",
            status=status,
            trace="{}",
            auditor="0x" + "77" * 20,
            chain_id=CHAIN,
            registry="0x" + "88" * 20,
            trace_hash="0x" + f"{n:064x}" if status != "pending" else None,
            merkle_root="0x" + f"{n + 1000:064x}" if status != "pending" else None,
            trace_cid=f"ar://trace-{n}" if done else None,
            transaction_hash="0x" + f"{n + 5000:064x}" if done else None,
            receipt_id=n if done else None,
        )
        s.add(row)
        s.commit()
        return row.id


def prepare(audit_id: int, **overrides):
    body = {"audit_id": audit_id, "execution_account": PAYER, "chain_id": CHAIN, **overrides}
    return client.post("/v1/settlements/prepare", json=body, headers=AUTH)


def verify(audit_id: int, tx: str = TX):
    return client.post(
        "/v1/settlements/verify",
        json={"audit_id": audit_id, "transaction_hash": tx},
        headers=AUTH,
    )


def settled_rows() -> list[SettlementRow]:
    with Session() as s:
        return list(s.scalars(select(SettlementRow).where(SettlementRow.status == "settled")))


def test_transfers_are_disabled_without_a_configured_deployment(monkeypatch) -> None:
    monkeypatch.delenv("RR_SETTLEMENT_CONFIG", raising=False)
    assert prepare(audit()).status_code == 503
    assert verify(1).status_code == 503


def test_preview_matches_configuration_and_settles_with_a_linked_outcome(chain) -> None:
    audit_id = audit()
    with Session() as s:
        published = s.get(AuditRow, audit_id)
        trace_hash, merkle_root = published.trace_hash, published.merkle_root

    prepared = prepare(audit_id)
    assert prepared.status_code == 200, prepared.text
    body = prepared.json()
    data = body["transaction"]["data"]
    assert body["transaction"] == {"to": USDC, "chain_id": CHAIN, "value": "0", "data": data}
    assert data[:10] == "0xa9059cbb"
    assert "0x" + data[34:74] == RECIPIENT
    assert int(data[74:], 16) == 10_000 == int(body["amount_units"])
    assert (body["recipient"], body["token"], body["chain_id"]) == (RECIPIENT, USDC, CHAIN)

    chain.mine(TX)
    assert (body["audit_id"], body["trace_hash"]) == (audit_id, trace_hash)
    settled = verify(audit_id)
    assert settled.status_code == 200, settled.text
    outcome = settled.json()["outcome_receipt"]
    assert settled.json()["status"] == "settled"
    assert verify_receipt({k: v for k, v in outcome.items() if k != "receipt_hash"})
    nodes = {node["id"]: node["payload"] for node in outcome["nodes"]}
    assert nodes["source"]["trace_hash"] == trace_hash
    assert nodes["source"]["merkle_root"] == merkle_root
    assert nodes["source"]["audit_id"] == audit_id
    assert nodes["transfer"]["transaction_hash"] == TX
    assert "audit_published" in nodes["verification"]["checks"]
    assert outcome["metadata"]["links"]["audited_trace_hash"] == trace_hash


@pytest.mark.parametrize("status", ["pending", "sealed", "rejected"])
def test_failed_or_inconclusive_audits_block_settlement(chain, status) -> None:
    audit_id = audit(status)
    response = prepare(audit_id)
    assert response.status_code == 409
    assert "transaction" not in response.json()
    assert prepare(999_999).status_code == 404
    chain.mine(TX)
    assert verify(audit_id).status_code == 404
    with Session() as s:
        assert s.scalars(select(SettlementRow)).first() is None


def test_failed_simulation_blocks_preparation(chain) -> None:
    chain.call = {"error": {"code": 3, "message": "execution reverted: transfer amount exceeds balance"}}
    audit_id = audit()
    response = prepare(audit_id)
    assert response.status_code == 409
    assert "transaction" not in response.json()
    chain.call = {"result": word(0)}
    assert prepare(audit_id).status_code == 409
    with Session() as s:
        assert s.scalars(select(SettlementRow)).first() is None


def test_wrong_network_and_bad_credentials_are_refused(chain) -> None:
    audit_id = audit()
    assert prepare(audit_id, chain_id=1).status_code == 409
    bad = client.post(
        "/v1/settlements/prepare",
        json={"audit_id": audit_id, "execution_account": PAYER, "chain_id": CHAIN},
        headers={"Authorization": "Bearer wrong"},
    )
    assert bad.status_code == 401
    chain.chain_id = 1
    assert prepare(audit_id).status_code == 503


def test_pending_and_reverted_never_become_success(chain) -> None:
    audit_id = audit()
    assert prepare(audit_id).status_code == 200

    assert verify(audit_id).json() == {"status": "pending"}
    chain.mine(TX, status="0x0", logs=[])
    assert verify(audit_id).json() == {"status": "reverted"}
    chain.mine(TX, block=150)
    assert verify(audit_id).json() == {"status": "pending_finality"}
    assert settled_rows() == []

    # A non-canonical block hash is refused, not recorded.
    chain.mine(TX, block=90)
    chain.receipts[TX]["blockHash"] = "0x" + "ff" * 32
    assert verify(audit_id).status_code == 409
    assert settled_rows() == []

    chain.mine(TX, block=90)
    assert verify(audit_id).json()["status"] == "settled"


@pytest.mark.parametrize(
    "logs",
    [
        [transfer_log(amount=9_999)],
        [transfer_log(to="0x" + "44" * 20)],
        [transfer_log(frm="0x" + "55" * 20)],
        [transfer_log(token="0x" + "66" * 20)],
        [transfer_log(index=0), transfer_log(index=1)],
        [],
    ],
)
def test_transaction_must_contain_exactly_the_configured_transfer(chain, logs) -> None:
    audit_id = audit()
    assert prepare(audit_id).status_code == 200
    chain.mine(TX, logs=logs)
    assert verify(audit_id).status_code == 409
    assert settled_rows() == []


def test_repeated_processing_creates_one_success_record(chain) -> None:
    audit_id = audit()
    assert prepare(audit_id).status_code == 200
    chain.mine(TX)

    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: verify(audit_id), range(6)))
    assert {r.status_code for r in results} == {200}
    assert len({r.json()["outcome_receipt"]["receipt_hash"] for r in results}) == 1
    assert len(settled_rows()) == 1

    # Re-preparing, a second transaction, or reusing the hash elsewhere is refused.
    assert prepare(audit_id).status_code == 409
    chain.mine(OTHER_TX)
    assert verify(audit_id, OTHER_TX).status_code == 409
    other = audit()
    assert prepare(other).status_code == 200
    assert verify(other, TX).status_code == 409
    assert len(settled_rows()) == 1


def test_another_wallet_cannot_replace_an_inflight_payment(chain) -> None:
    audit_id = audit()
    assert prepare(audit_id).status_code == 200
    chain.mine(TX)
    assert prepare(audit_id, execution_account="0x" + "44" * 20).status_code == 409
    assert verify(audit_id).json()["status"] == "settled"


@pytest.mark.parametrize("block", [1, 80])
def test_a_preexisting_transfer_cannot_pay_for_a_new_audit(chain, block) -> None:
    chain.mine(TX, block=block)
    audit_id = audit()
    assert prepare(audit_id).status_code == 200
    response = verify(audit_id)
    assert response.status_code == 409
    assert "predates" in response.json()["detail"]
    assert settled_rows() == []


def test_retry_keeps_the_original_preparation_boundary(chain) -> None:
    audit_id = audit()
    first = prepare(audit_id).json()
    chain.mine(TX)
    chain.latest = 95
    repeated = prepare(audit_id)
    assert repeated.status_code == 200
    assert repeated.json() == first
    outcome = verify(audit_id).json()["outcome_receipt"]
    policy = next(n["payload"] for n in outcome["nodes"] if n["id"] == "verification")
    assert policy["prepared_after_block"] == 80
    assert "after_preparation" in policy["checks"]


def test_configuration_change_does_not_replace_an_inflight_payment(chain) -> None:
    audit_id = audit()
    assert prepare(audit_id).status_code == 200
    config = Path(os.environ["RR_SETTLEMENT_CONFIG"])
    original = config.read_text()
    deployment = json.loads(original)
    deployment["recipient"] = "0x" + "44" * 20
    config.write_text(json.dumps(deployment))
    assert prepare(audit_id).status_code == 409
    with Session() as s:
        row = s.scalars(select(SettlementRow)).one()
        assert (row.payer, row.recipient, row.prepared_after_block) == (PAYER, RECIPIENT, 80)
    config.write_text(original)
    chain.mine(TX)
    assert verify(audit_id).json()["status"] == "settled"


def test_legacy_preparation_requires_manual_review_without_rebinding(chain) -> None:
    audit_id = audit()
    assert prepare(audit_id).status_code == 200
    with Session() as s:
        row = s.scalars(select(SettlementRow)).one()
        row.prepared_after_block = None
    assert prepare(audit_id).status_code == 409
    chain.mine(TX)
    assert verify(audit_id).status_code == 409
    assert settled_rows() == []


def test_missing_chain_head_never_prepares_a_payment(chain, monkeypatch) -> None:
    from server import settlement

    original = settlement._rpc

    def missing_head(method, params):
        if method == "eth_getBlockByNumber" and params[0] == "latest":
            return {"result": None}
        return original(method, params)

    monkeypatch.setattr(settlement, "_rpc", missing_head)
    assert prepare(audit()).status_code == 503
    with Session() as s:
        assert s.scalars(select(SettlementRow)).first() is None


def test_concurrent_wallets_cannot_replace_the_winning_preparation(chain) -> None:
    audit_id = audit()
    wallets = [PAYER, "0x" + "44" * 20]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda payer: prepare(audit_id, execution_account=payer), wallets))
    assert sorted(r.status_code for r in results) == [200, 409]
    winner = next(r.json()["payer"] for r in results if r.status_code == 200)
    chain.mine(TX, logs=[transfer_log(frm=winner)])
    assert verify(audit_id).json()["status"] == "settled"


def test_existing_settlement_tables_gain_a_nullable_preparation_boundary(tmp_path) -> None:
    from storage.db import _migrate

    engine = create_engine(f"sqlite:///{(tmp_path / 'legacy.db').as_posix()}")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE settlements (id INTEGER PRIMARY KEY)"))
            connection.execute(text("INSERT INTO settlements (id) VALUES (1)"))
        _migrate(engine)
        _migrate(engine)
        columns = {column["name"]: column for column in inspect(engine).get_columns("settlements")}
        assert columns["prepared_after_block"]["nullable"]
        with engine.connect() as connection:
            assert connection.execute(text("SELECT prepared_after_block FROM settlements")).scalar() is None
    finally:
        engine.dispose()
