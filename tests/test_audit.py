"""Independent audit acceptance: the oracle stops at the raw trace, only an
approved audit by the configured auditor is sealed, the oracle's nodes keep
their hashes, and one finalized ReceiptV2 from the auditor records one receipt."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
import respx
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from agent import merkle
from agent.analyst import MarketCandidate
from agent.loop import AgentLoop
from server.audit import MAX_SOURCES, PUBLISH_V2_SELECTOR, PUBLISH_V2_TYPES, RECEIPT_V2_TOPIC
from server.audit import router as audit_router
from server.verify import _find_node_in_trace
from storage.db import Audit as AuditRow
from storage.db import Receipt as ReceiptRow
from storage.db import Session
from storage.irys import canonical_bytes, sha256_hex

RPC = "https://rpc.test/arc"
CHAIN = 5_042_002
REGISTRY = "0x" + "44" * 20
AUDITOR = "0x" + "55" * 20
AUTH = {"Authorization": "Bearer audit-test-token"}
TX = "0x" + "aa" * 32
OTHER_TX = "0x" + "bb" * 32

app = FastAPI()
app.include_router(audit_router)
client = TestClient(app)


def word(value: str | int) -> str:
    return "0x" + (value[2:] if isinstance(value, str) else f"{value:x}").rjust(64, "0")


class FakeChain:
    """Just enough JSON-RPC for the publish confirmation."""

    def __init__(self) -> None:
        self.receipts: dict[str, dict] = {}
        self.finalized = 100
        self.blocks = {hex(n): "0x" + f"{n:064x}" for n in range(1, 200)}

    def mine(self, tx: str, *, status="0x1", block=90, logs=None) -> None:
        self.receipts[tx] = {
            "status": status,
            "blockNumber": hex(block),
            "blockHash": self.blocks[hex(block)],
            "logs": logs or [],
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method, params = body["method"], body["params"]
        if method == "eth_chainId":
            reply = {"result": hex(CHAIN)}
        elif method == "eth_getTransactionReceipt":
            reply = {"result": self.receipts.get(params[0])}
        elif params[0] == "finalized":
            reply = {"result": {"number": hex(self.finalized)}}
        else:
            reply = {"result": {"hash": self.blocks[params[0]]}}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, **reply})


def receipt_log(calldata: str, *, publisher=AUDITOR, registry=REGISTRY, receipt_id=7) -> dict:
    """The ReceiptV2 event the registry emits for these publishV2 arguments."""
    sent = abi_decode(PUBLISH_V2_TYPES, bytes.fromhex(calldata[10:]))
    data = abi_encode(
        ["bytes32", "uint32", "uint32", "bytes32", "bytes32", "bytes16", "string", "uint64"],
        [*sent[1:], 1_700_000_000],
    )
    return {
        "address": registry,
        "topics": [RECEIPT_V2_TOPIC, word(receipt_id), word(publisher), word(sent[0])],
        "data": "0x" + data.hex(),
    }


@pytest.fixture
def chain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    config = tmp_path / "audit-deployment.json"
    config.write_text(
        json.dumps(
            {
                "enabled": True,
                "chain_id": CHAIN,
                "registry": REGISTRY,
                "auditor": AUDITOR,
                "api_url": "https://api.example",
            }
        )
    )
    monkeypatch.setenv("RR_AUDIT_CONFIG", str(config))
    monkeypatch.setenv("RR_AUDIT_API_TOKEN", "audit-test-token")
    monkeypatch.setenv("RR_AUDIT_RPC_URL", RPC)
    fake = FakeChain()
    with respx.mock(assert_all_called=False) as mock:
        mock.post(RPC).mock(side_effect=fake)
        yield fake


@pytest.fixture
def handed_off(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Run the real ensemble path (mocked models) in audit mode."""
    monkeypatch.setenv("RR_USE_ENSEMBLE", "1")
    monkeypatch.setenv("RR_AUDIT_MODE", "aomi")
    loop = AgentLoop()
    loop._process_candidate(
        MarketCandidate(
            market_id="m-audit-1",
            source="polymarket",
            question="Will the audit pass?",
            end_date=None,
            liquidity_usd=50_000.0,
        )
    )
    with Session() as s:
        row = s.scalars(select(AuditRow)).one()
        return json.loads(row.trace)


def findings(trace: dict, **overrides) -> dict:
    sources = [
        {
            "evidence_id": e["id"],
            "url": e["url"],
            "http_status": 200,
            "final_url": e["url"],
            "content_sha256": "0x" + "ab" * 32,
            "page_title": e["title"],
            "title_matches": True,
            "fetched_at": "2026-10-18T06:00:00Z",
            "error": None,
            "supports": True,
            "note": "states the cited figure",
        }
        for stance in trace["stances"]
        for e in stance["evidence"]
    ]
    return {
        "auditor": AUDITOR,
        "chain_id": CHAIN,
        "verdict": "approved",
        "notes": "",
        "sources": sources,
        **overrides,
    }


def seal(body: dict, audit_id: int = 1):
    return client.post(f"/v1/audits/{audit_id}/seal", json=body, headers=AUTH)


def confirm(tx: str = TX, audit_id: int = 1):
    return client.post(f"/v1/audits/{audit_id}/published", json={"transaction_hash": tx}, headers=AUTH)


def receipts() -> list[ReceiptRow]:
    with Session() as s:
        return list(s.scalars(select(ReceiptRow)))


def test_audit_mode_hands_off_the_raw_trace_and_publishes_nothing(handed_off):
    assert handed_off["schema_version"] == "rr-trace/3"
    assert "external_audit" not in handed_off
    assert receipts() == []


def test_disabled_by_default_and_requires_credentials(handed_off, monkeypatch):
    assert client.get("/v1/audits/next", headers=AUTH).status_code == 503
    monkeypatch.setenv("RR_AUDIT_CONFIG", "")
    assert seal(findings(handed_off)).status_code == 503


def test_wrong_token_or_auditor_or_network_is_refused(chain, handed_off):
    assert client.get("/v1/audits/next", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert seal(findings(handed_off, auditor="0x" + "66" * 20)).status_code == 403
    assert seal(findings(handed_off, chain_id=1)).status_code == 409
    with Session() as s:
        assert s.get(AuditRow, 1).status == "pending"


def test_next_serves_the_trace_and_every_cited_source(chain, handed_off):
    pending = client.get("/v1/audits/next", headers=AUTH).json()
    assert pending["status"] == "pending" and pending["audit_id"] == 1
    cited = {e["id"] for s in handed_off["stances"] for e in s["evidence"]}
    assert {e["id"] for e in pending["evidence"]} == cited and cited


@pytest.mark.parametrize(
    "change",
    [
        lambda b: b["sources"].pop(),
        lambda b: b["sources"].append(dict(b["sources"][0])),
        lambda b: b["sources"][0].update(url="https://elsewhere.example"),
    ],
)
def test_audit_must_cover_every_cited_source_exactly(chain, handed_off, change):
    body = findings(handed_off)
    change(body)
    assert seal(body).status_code == 422


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda b: [c.update(http_status=404) for c in b["sources"]], "no cited source could be read"),
        (
            lambda b: [
                c.update(http_status=None, content_sha256=None, error="timeout") for c in b["sources"]
            ],
            "no cited source could be read",
        ),
        (lambda b: [c.update(supports=False) for c in b["sources"]], "only 0 of"),
        (
            lambda b: (
                [c.update(supports=i == 0) for i, c in enumerate(b["sources"])]
                + [b["sources"][1].update(http_status=410)]
            ),
            "readable sources support",
        ),
        (lambda b: b.update(verdict="rejected", notes="claim ignores the bear case"), "auditor rejected"),
    ],
)
def test_failed_audit_is_recorded_and_never_sealed(chain, handed_off, change, reason):
    body = findings(handed_off)
    change(body)
    rejected = seal(body).json()
    assert rejected["status"] == "rejected"
    assert any(reason in r for r in rejected["reasons"])
    with Session() as s:
        row = s.get(AuditRow, 1)
        assert row.status == "rejected" and row.calldata is None and row.trace_hash is None
    assert client.get("/v1/audits/next", headers=AUTH).json() == {"status": "empty"}
    assert seal(findings(handed_off)).status_code == 409
    assert client.get("/v1/audits/1", headers=AUTH).json() == rejected


def test_blocked_pages_are_skipped_and_most_readable_sources_decide(chain, handed_off):
    body = findings(handed_off)
    body["sources"][0].update(http_status=403, content_sha256=None, supports=False)
    sealed = seal(body).json()
    assert sealed["status"] == "sealed"
    with Session() as s:
        verdict = json.loads(s.get(AuditRow, 1).sealed_trace)["external_audit"]["nodes"]["xa_verdict"]
    assert verdict["verdict"] == "approved"
    assert verdict["skipped_sources"] == [body["sources"][0]["evidence_id"]]


def test_approved_audit_adds_nodes_and_keeps_every_oracle_hash(chain, handed_off):
    sealed = seal(findings(handed_off)).json()
    assert sealed["status"] == "sealed"
    with Session() as s:
        trace = json.loads(s.get(AuditRow, 1).sealed_trace)

    # The oracle's nodes, hashes and bytes are carried over unchanged.
    for node_id, node_hash in handed_off["node_hashes"].items():
        assert trace["node_hashes"][node_id] == node_hash
    for key in handed_off.keys() - {"node_hashes", "merkle_root"}:
        assert trace[key] == handed_off[key]

    # Every node hash, the root and the uploaded hash recompute from the JSON alone.
    audit_nodes = trace["external_audit"]["nodes"]
    assert audit_nodes.keys() == {f"xa_{e['id']}" for s in handed_off["stances"] for e in s["evidence"]} | {
        "xa_verdict"
    }
    for node_id, node in audit_nodes.items():
        assert sha256_hex(canonical_bytes(node)) == trace["node_hashes"][node_id]
        assert _find_node_in_trace(trace, node_id) == node
    leaves = [bytes.fromhex(trace["node_hashes"][i][2:]) for i in sorted(trace["node_hashes"])]
    assert "0x" + merkle.merkle_root(leaves).hex() == trace["merkle_root"] == sealed["merkle_root"]
    assert sha256_hex(canonical_bytes(trace)) == sealed["trace_hash"]
    verdict = audit_nodes["xa_verdict"]
    assert verdict["auditor"] == AUDITOR and verdict["verdict"] == "approved"
    assert verdict["oracle_merkle_root"] == handed_off["merkle_root"]

    # The unsigned transaction is publishV2 to the registry with exactly these commitments.
    tx = sealed["transaction"]
    assert tx == {"to": REGISTRY, "chain_id": CHAIN, "value": "0", "data": tx["data"]}
    assert tx["data"].startswith(PUBLISH_V2_SELECTOR)
    consumer, _, prob, conf, trace_hash, root, schema, cid = abi_decode(
        PUBLISH_V2_TYPES, bytes.fromhex(tx["data"][10:])
    )
    assert consumer == "0x" + "00" * 20
    assert "0x" + trace_hash.hex() == sealed["trace_hash"] and "0x" + root.hex() == sealed["merkle_root"]
    assert prob == round(handed_off["claim"]["probability"] * 1_000_000)
    assert schema.rstrip(b"\0") == b"rr-trace/3" and cid == sealed["trace_cid"]

    # Sealing again, or asking for the next audit, re-serves the same seal.
    assert seal(findings(handed_off)).json() == sealed
    assert client.get("/v1/audits/next", headers=AUTH).json() == sealed
    assert client.get("/v1/audits/1", headers=AUTH).json() == sealed


def test_pending_reverted_or_unfinalized_never_record(chain, handed_off):
    data = seal(findings(handed_off)).json()["transaction"]["data"]
    assert confirm().json() == {"status": "pending"}
    chain.mine(TX, status="0x0", logs=[receipt_log(data)])
    assert confirm().json() == {"status": "reverted"}
    chain.mine(TX, block=150, logs=[receipt_log(data)])
    assert confirm().json() == {"status": "pending_finality"}
    chain.mine(TX, logs=[receipt_log(data)])
    chain.blocks[hex(90)] = "0x" + "ee" * 32
    chain.receipts[TX]["blockHash"] = "0x" + "dd" * 32
    assert confirm().status_code == 409
    assert receipts() == []


@pytest.mark.parametrize(
    "logs",
    [
        lambda d: [],
        lambda d: [receipt_log(d, publisher="0x" + "66" * 20)],
        lambda d: [receipt_log(d, registry="0x" + "77" * 20)],
        lambda d: [receipt_log(d), receipt_log(d, receipt_id=8)],
        lambda d: [receipt_log(d[:-64] + "00" * 32)],
    ],
)
def test_only_the_sealed_trace_from_the_auditor_counts(chain, handed_off, logs):
    data = seal(findings(handed_off)).json()["transaction"]["data"]
    chain.mine(TX, logs=logs(data))
    assert confirm().status_code == 409
    assert receipts() == []


def test_finalized_publish_records_one_receipt_by_the_auditor(chain, handed_off):
    sealed = seal(findings(handed_off)).json()
    chain.mine(TX, logs=[receipt_log(sealed["transaction"]["data"])])
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(pool.map(lambda _: confirm(), range(6)))
    assert {r.status_code for r in results} == {200}
    published = results[0].json()
    assert all(r.json() == published for r in results)
    assert published["status"] == "published" and published["publisher"] == AUDITOR

    [row] = receipts()
    assert row.publisher_address == AUDITOR and row.chain_receipt_id == 7
    assert (row.trace_hash, row.merkle_root, row.trace_cid) == (
        sealed["trace_hash"],
        sealed["merkle_root"],
        sealed["trace_cid"],
    )
    assert published["receipt_id"] == row.id
    assert confirm(OTHER_TX).status_code == 409
    assert client.get("/v1/audits/1", headers=AUTH).json() == published
    assert client.get("/v1/audits/next", headers=AUTH).json() == {"status": "empty"}


def test_a_transaction_cannot_publish_two_audits(chain, handed_off):
    with Session() as s:
        s.add(
            AuditRow(
                market_id="m-audit-2",
                market_question="Second",
                trace=json.dumps({**handed_off, "market_id": "m-audit-2"}),
                created_at=datetime.now(UTC),
            )
        )
    first = seal(findings(handed_off)).json()
    seal(findings(handed_off), audit_id=2)
    chain.mine(TX, logs=[receipt_log(first["transaction"]["data"])])
    assert confirm().json()["status"] == "published"
    assert confirm(audit_id=2).status_code == 409
    assert len(receipts()) == 1


def test_a_seal_waiting_on_its_wallet_never_blocks_newer_audits(chain, handed_off):
    sealed = seal(findings(handed_off)).json()
    with Session() as s:
        s.add(AuditRow(market_id="m-audit-2", trace=json.dumps({**handed_off, "market_id": "m-audit-2"})))
    pending = client.get("/v1/audits/next", headers=AUTH).json()
    assert pending["status"] == "pending" and pending["audit_id"] == 2
    seal(findings(handed_off), audit_id=2)
    assert client.get("/v1/audits/next", headers=AUTH).json() == sealed


def test_an_open_audit_holds_its_market_however_old(monkeypatch):
    monkeypatch.setenv("RR_USE_ENSEMBLE", "1")
    monkeypatch.setenv("RR_AUDIT_MODE", "aomi")
    loop = AgentLoop()
    candidates = loop.scanner.scan()
    assert len(candidates) >= 2
    old = datetime(2020, 1, 1, tzinfo=UTC)
    with Session() as s:
        s.add(AuditRow(market_id=candidates[0].market_id, trace="{}", created_at=old))
        s.add(AuditRow(market_id=candidates[1].market_id, trace="{}", status="rejected", created_at=old))
    priced: list[str] = []
    monkeypatch.setattr(loop.scanner, "scan", lambda: candidates)
    monkeypatch.setattr(loop, "_process_candidate", lambda c: priced.append(c.market_id))
    loop.config.per_tick = len(candidates)
    asyncio.run(loop.run_once())
    assert candidates[0].market_id not in priced
    assert candidates[1].market_id in priced


def test_a_trace_too_large_to_audit_is_not_handed_off(monkeypatch):
    monkeypatch.setenv("RR_USE_ENSEMBLE", "1")
    monkeypatch.setenv("RR_AUDIT_MODE", "aomi")
    loop = AgentLoop()
    analyse = loop._ensemble.analyse

    def flooded(*args, **kwargs):
        trace = analyse(*args, **kwargs)
        source = trace.stances[0].evidence[0]
        trace.stances[0].evidence = [replace(source, id=f"e_bull_{i}") for i in range(MAX_SOURCES + 1)]
        return trace

    monkeypatch.setattr(loop._ensemble, "analyse", flooded)
    loop._process_candidate(
        MarketCandidate(
            market_id="m-big", source="polymarket", question="?", end_date=None, liquidity_usd=1.0
        )
    )
    with Session() as s:
        assert list(s.scalars(select(AuditRow))) == []
    assert receipts() == []
