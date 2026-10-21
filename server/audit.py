"""Independent audit of oracle traces by an Aomi auditor, then publication.

Flow (``RR_AUDIT_MODE=aomi``): the loop stores each critic-approved rr-trace/3
trace as a pending audit instead of sealing it -> the Aomi app takes it from
``/next``, fetches every cited source itself and reports what it found to
``/{id}/seal`` -> an approved audit becomes extra ``xa_*`` nodes in the trace,
which is re-rooted, uploaded and returned as unsigned ``publishV2`` calldata
for the auditor's wallet -> ``/{id}/published`` checks the finalized
``ReceiptV2`` event and records the receipt with the auditor as publisher.

The oracle's own nodes and their hashes are carried over unchanged, so every
existing inclusion proof still works against the new root. A rejected audit
records why and publishes nothing.

The chain, registry and auditor address come only from the deployment JSON in
``RR_AUDIT_CONFIG`` (the same file the Aomi app is built from). Without it, or
with ``enabled`` false, every route refuses.
"""

from __future__ import annotations

import hmac
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import httpx
from eth_abi import decode as abi_decode
from eth_abi import encode as abi_encode
from eth_utils import keccak
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from agent import merkle
from storage.db import Audit as AuditRow
from storage.db import Receipt as ReceiptRow
from storage.db import Session
from storage.irys import IrysClient, canonical_bytes, sha256_hex

from .chain import ZERO_ADDRESS, _hex_to_bytes32, _market_id_bytes32, _scale_unit_to_ppm

router = APIRouter(prefix="/v1/audits", tags=["audits"])

AUDIT_VERSION = "aomi-audit/1"
# The most cited sources one audit can report; the loop never hands off a larger trace.
MAX_SOURCES = 64
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
PUBLISH_V2_TYPES = ["address", "bytes32", "uint32", "uint32", "bytes32", "bytes32", "bytes16", "string"]
PUBLISH_V2_SELECTOR = "0x" + keccak(text=f"publishV2({','.join(PUBLISH_V2_TYPES)})")[:4].hex()
RECEIPT_V2_TOPIC = (
    "0x"
    + keccak(
        text="ReceiptV2(uint256,address,address,bytes32,uint32,uint32,bytes32,bytes32,bytes16,string,uint64)"
    ).hex()
)


class SourceCheck(BaseModel):
    """What the auditor found at one cited URL. Fetch fields come from the
    app's own request, ``supports`` and ``note`` from the auditor's reading."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str = Field(min_length=1, max_length=100)
    url: str = Field(max_length=500)
    http_status: int | None = None
    final_url: str | None = Field(default=None, max_length=2000)
    content_sha256: str | None = Field(default=None, max_length=66)
    page_title: str | None = Field(default=None, max_length=300)
    title_matches: bool = False
    fetched_at: str = Field(max_length=40)
    error: str | None = Field(default=None, max_length=200)
    supports: bool
    note: str = Field(default="", max_length=500)


class SealRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    auditor: str = Field(min_length=42, max_length=42)
    chain_id: int
    verdict: Literal["approved", "rejected"]
    notes: str = Field(default="", max_length=1000)
    sources: list[SourceCheck] = Field(max_length=MAX_SOURCES)


class PublishedRequest(BaseModel):
    transaction_hash: str = Field(min_length=66, max_length=66)


def _deployment(authorization: str | None) -> dict[str, Any]:
    """Authorize the caller and load the deployment-bound registry and auditor, or refuse."""
    path = os.getenv("RR_AUDIT_CONFIG", "")
    config = json.loads(Path(path).read_text()) if path else {"enabled": False}
    if config.get("enabled") is not True:
        raise HTTPException(503, "Audits are disabled until an auditor and registry are configured")
    token = os.getenv("RR_AUDIT_API_TOKEN", "")
    if not token or not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(401, "Audit access denied")
    for key in ("registry", "auditor"):
        if not ADDRESS.match(str(config.get(key, ""))) or int(config[key], 16) == 0:
            raise HTTPException(503, f"Audit deployment has no valid {key}")
    chain_id = config.get("chain_id")
    if not isinstance(chain_id, int) or chain_id <= 0:
        raise HTTPException(503, "Audit deployment has no valid chain")
    return {
        "chain_id": chain_id,
        "registry": config["registry"].lower(),
        "auditor": config["auditor"].lower(),
    }


def _rpc(method: str, params: list[Any]) -> dict[str, Any]:
    """One JSON-RPC call; the caller decides what a missing result means."""
    try:
        response = httpx.post(
            os.environ["RR_AUDIT_RPC_URL"],
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=20,
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.json()
    except (KeyError, httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Audit RPC unavailable; nothing was recorded") from exc


def _sealed(row: AuditRow, d: dict[str, Any]) -> dict[str, Any]:
    """The stored seal, re-served unchanged so a wallet can approve it later."""
    if (row.chain_id, row.registry, row.auditor) != (d["chain_id"], d["registry"], d["auditor"]):
        raise HTTPException(409, "Deployment changed since sealing; manual review required")
    sealed = json.loads(row.sealed_trace)
    return {
        "status": "sealed",
        "audit_id": row.id,
        "market_id": row.market_id,
        "market_question": row.market_question,
        "probability": sealed["claim"]["probability"],
        "confidence": sealed["claim"]["confidence"],
        "schema_version": sealed["schema_version"],
        "trace_hash": row.trace_hash,
        "merkle_root": row.merkle_root,
        "trace_cid": row.trace_cid,
        "auditor": row.auditor,
        "external_audit": sealed["external_audit"],
        "transaction": {"to": row.registry, "chain_id": row.chain_id, "value": "0", "data": row.calldata},
    }


@router.get("/next")
def next_audit(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    """The oldest trace waiting for the auditor, or a sealed one waiting for its wallet."""
    d = _deployment(authorization)
    with Session() as s:
        # Pending traces first, so a seal waiting on its wallet never blocks newer audits.
        row = s.scalars(select(AuditRow).where(AuditRow.status == "pending").order_by(AuditRow.id)).first()
        row = (
            row
            or s.scalars(select(AuditRow).where(AuditRow.status == "sealed").order_by(AuditRow.id)).first()
        )
        return {"status": "empty"} if row is None else _view(row, d)


@router.get("/{audit_id}")
def get_audit(audit_id: int, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    d = _deployment(authorization)
    with Session() as s:
        row = s.get(AuditRow, audit_id)
        if row is None:
            raise HTTPException(404, "No audit with this id")
        return _view(row, d)


def _view(row: AuditRow, d: dict[str, Any]) -> dict[str, Any]:
    """What the auditor reads: the trace and every cited source, or the stored outcome."""
    if row.status == "sealed":
        return _sealed(row, d)
    if row.status == "published":
        return _published(row)
    if row.status == "rejected":
        return {
            "status": "rejected",
            "audit_id": row.id,
            "reasons": json.loads(row.findings)["xa_verdict"]["reasons"],
        }
    trace = json.loads(row.trace)
    return {
        "status": "pending",
        "audit_id": row.id,
        "market_id": trace["market_id"],
        "market_question": trace["market_question"],
        "claim": trace["claim"],
        "stances": trace["stances"],
        "supervisor_synthesis": trace["supervisor_synthesis"],
        "counter_arguments": trace["counter_arguments"],
        "falsifiable_claims": trace["falsifiable_claims"],
        "critic_verdict": trace["critic_audit"]["verdict"],
        "evidence": [
            {**evidence, "stance": stance["role"]}
            for stance in trace["stances"]
            for evidence in stance.get("evidence", [])
        ],
    }


@router.post("/{audit_id}/seal")
def seal_audit(
    audit_id: int, request: SealRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Record the auditor's findings. Approved: re-root, upload, return unsigned publishV2."""
    d = _deployment(authorization)
    auditor = request.auditor.lower()
    if auditor != d["auditor"]:
        raise HTTPException(403, "Only the configured auditor wallet can seal audits")
    if request.chain_id != d["chain_id"]:
        raise HTTPException(409, "Auditor wallet is on the wrong network")
    with Session() as s:
        row = s.get(AuditRow, audit_id)
        if row is None:
            raise HTTPException(404, "No audit with this id")
        if row.status == "sealed":
            return _sealed(row, d)
        if row.status != "pending":
            raise HTTPException(409, f"This audit is already {row.status}; nothing was sealed")
        trace = json.loads(row.trace)

    cited = {e["id"]: e for stance in trace["stances"] for e in stance.get("evidence", [])}
    reported = {c.evidence_id: c for c in request.sources}
    if (
        len(reported) != len(request.sources)
        or reported.keys() != cited.keys()
        or any(reported[i].url != cited[i]["url"] for i in cited)
    ):
        raise HTTPException(422, "Report every cited source exactly once, at its cited URL")

    # Approval is decided here from the findings, not taken from the verdict alone.
    # Pages that refused the fetch (bot walls, rate limits, timeouts) say nothing about the
    # citation and are skipped; a dead link (404/410) counts as a source that does not support.
    # Most of the sources that were read must support what they are cited for.
    readable = [
        c for c in request.sources if c.http_status and 200 <= c.http_status < 300 and c.content_sha256
    ]
    dead = [c for c in request.sources if c.http_status in (404, 410)]
    counted_ids = {c.evidence_id for c in readable + dead}
    skipped = [c.evidence_id for c in request.sources if c.evidence_id not in counted_ids]
    supporting = sum(c.supports for c in readable)
    counted = len(readable) + len(dead)
    reasons = [] if cited else ["the trace cites no sources"]
    if cited and not readable:
        reasons.append("no cited source could be read")
    elif cited and 2 * supporting <= counted:
        reasons.append(f"only {supporting} of {counted} readable sources support what they are cited for")
    if request.verdict != "approved":
        reasons.append("auditor rejected the reasoning")
    verdict = "rejected" if reasons else "approved"

    leaves_before = [bytes.fromhex(h[2:]) for _, h in sorted(trace["node_hashes"].items())]
    if "0x" + merkle.merkle_root(leaves_before).hex() != trace["merkle_root"]:
        raise HTTPException(409, "Stored trace commitments do not verify; nothing was sealed")
    nodes: dict[str, dict[str, Any]] = {f"xa_{c.evidence_id}": c.model_dump() for c in request.sources}
    nodes["xa_verdict"] = {
        "version": AUDIT_VERSION,
        "auditor": auditor,
        "chain_id": d["chain_id"],
        "verdict": verdict,
        "reasons": reasons,
        "skipped_sources": skipped,
        "notes": request.notes,
        "audited_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "oracle_trace_hash": sha256_hex(canonical_bytes(trace)),
        "oracle_merkle_root": trace["merkle_root"],
    }
    findings = json.dumps(nodes, sort_keys=True, separators=(",", ":"))

    if verdict == "rejected":
        with Session() as s:
            s.execute(
                update(AuditRow)
                .where(AuditRow.id == audit_id, AuditRow.status == "pending")
                .values(status="rejected", findings=findings, auditor=auditor, updated_at=datetime.now(UTC))
            )
        return {"status": "rejected", "audit_id": audit_id, "reasons": reasons}

    # The oracle's nodes keep their hashes; the audit adds nodes and a new root.
    node_hashes = {**trace["node_hashes"], **{i: sha256_hex(canonical_bytes(n)) for i, n in nodes.items()}}
    leaves = [bytes.fromhex(node_hashes[i][2:]) for i in sorted(node_hashes)]
    sealed = {
        **{k: v for k, v in trace.items() if k not in ("node_hashes", "merkle_root")},
        "external_audit": {"version": AUDIT_VERSION, "nodes": nodes},
        "node_hashes": node_hashes,
        "merkle_root": "0x" + merkle.merkle_root(leaves).hex(),
    }
    upload = IrysClient().upload(sealed)
    args = (
        ZERO_ADDRESS,
        _market_id_bytes32(trace["market_id"]),
        _scale_unit_to_ppm(trace["claim"]["probability"]),
        _scale_unit_to_ppm(trace["claim"]["confidence"]),
        _hex_to_bytes32(upload.hash_hex),
        _hex_to_bytes32(sealed["merkle_root"]),
        trace["schema_version"].encode("ascii")[:16].ljust(16, b"\0"),
        upload.cid,
    )
    calldata = PUBLISH_V2_SELECTOR + abi_encode(PUBLISH_V2_TYPES, args).hex()

    with Session() as s:
        try:
            # Conditional write: concurrent seals of one audit leave exactly one seal.
            s.execute(
                update(AuditRow)
                .where(AuditRow.id == audit_id, AuditRow.status == "pending")
                .values(
                    status="sealed",
                    sealed_trace=json.dumps(sealed, sort_keys=True, separators=(",", ":")),
                    findings=findings,
                    auditor=auditor,
                    chain_id=d["chain_id"],
                    registry=d["registry"],
                    trace_hash=upload.hash_hex,
                    merkle_root=sealed["merkle_root"],
                    trace_cid=upload.cid,
                    calldata=calldata,
                    updated_at=datetime.now(UTC),
                )
            )
            s.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "This sealed trace already exists; manual review required") from exc
        row = s.get(AuditRow, audit_id)
        s.refresh(row)
        if row.status != "sealed":
            raise HTTPException(409, f"This audit is already {row.status}; nothing was sealed")
        return _sealed(row, d)


@router.post("/{audit_id}/published")
def confirm_published(
    audit_id: int, request: PublishedRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Check the finalized ReceiptV2 event and record the audited receipt once.

    Safe to repeat. Only ``published`` is success; ``pending``,
    ``pending_finality`` and ``reverted`` record nothing.
    """
    d = _deployment(authorization)
    tx_hash = request.transaction_hash.lower()
    if not TX_HASH.match(tx_hash):
        raise HTTPException(422, "Provide the wallet's 32-byte transaction hash")
    if not os.getenv("RR_AUDIT_RPC_URL"):
        raise HTTPException(503, "Audit RPC is not configured; nothing was recorded")
    with Session() as s:
        row = s.get(AuditRow, audit_id)
        if row is None:
            raise HTTPException(404, "No audit with this id")
        if row.status == "published":
            if row.transaction_hash != tx_hash:
                raise HTTPException(409, "This audit was already published by a different transaction")
            return _published(row)
        if row.status != "sealed":
            raise HTTPException(409, "This audit is not sealed; there is nothing to publish")
        if s.scalars(select(AuditRow).where(AuditRow.transaction_hash == tx_hash)).first():
            raise HTTPException(409, "This transaction already published a different audit")
        expected = _sealed(row, d)
        sealed = json.loads(row.sealed_trace)

    if _rpc("eth_chainId", []).get("result") != hex(d["chain_id"]):
        raise HTTPException(503, "Audit RPC is on a different chain; nothing was recorded")
    receipt = _rpc("eth_getTransactionReceipt", [tx_hash]).get("result")
    if not receipt:
        return {"status": "pending"}
    if receipt.get("status") != "0x1":
        return {"status": "reverted"}
    finalized = _rpc("eth_getBlockByNumber", ["finalized", False]).get("result")
    if not finalized:
        raise HTTPException(503, "RPC cannot report finality; nothing was recorded")
    block_number = int(receipt["blockNumber"], 16)
    if block_number > int(finalized["number"], 16):
        return {"status": "pending_finality"}
    canonical = _rpc("eth_getBlockByNumber", [receipt["blockNumber"], False]).get("result") or {}
    if str(canonical.get("hash", "")).lower() != str(receipt.get("blockHash", "")).lower():
        raise HTTPException(409, "Transaction is not in the canonical chain; nothing was recorded")

    events = [
        log
        for log in receipt.get("logs", [])
        if str(log.get("address", "")).lower() == d["registry"]
        and len(log.get("topics", [])) == 4
        and log["topics"][0].lower() == RECEIPT_V2_TOPIC
    ]
    sent = abi_decode(PUBLISH_V2_TYPES, bytes.fromhex(expected["transaction"]["data"][10:]))
    if len(events) != 1:
        raise HTTPException(409, "Transaction does not contain exactly one receipt from the registry")
    event = events[0]
    logged = abi_decode(
        ["bytes32", "uint32", "uint32", "bytes32", "bytes32", "bytes16", "string", "uint64"],
        bytes.fromhex(event["data"][2:]),
    )
    if (
        event["topics"][2].lower() != "0x" + d["auditor"][2:].rjust(64, "0")
        or event["topics"][3].lower() != "0x" + "0" * 64
        or tuple(logged[:7]) != tuple(sent[1:])
    ):
        raise HTTPException(409, "Published receipt is not the sealed trace from the auditor")

    with Session() as s:
        try:
            claimed = s.execute(
                update(AuditRow)
                .where(AuditRow.id == audit_id, AuditRow.status == "sealed")
                .values(status="published", transaction_hash=tx_hash, updated_at=datetime.now(UTC))
            ).rowcount
            if claimed == 1:
                published = ReceiptRow(
                    chain_receipt_id=int(event["topics"][1], 16),
                    market_id=row.market_id,
                    market_question=row.market_question,
                    market_source=row.market_source,
                    probability=sealed["claim"]["probability"],
                    confidence=sealed["claim"]["confidence"],
                    trace_hash=row.trace_hash,
                    trace_cid=row.trace_cid,
                    consumer_address=None,
                    publisher_address=d["auditor"],
                    paid_micro_usdc=0,
                    arc_tx_hash=tx_hash,
                    arc_block_number=block_number,
                    schema_version=sealed["schema_version"],
                    disagreement_pp=sealed["supervisor_synthesis"]["disagreement_pp"],
                    merkle_root=row.merkle_root,
                    category=sealed["category"],
                )
                s.add(published)
                s.flush()
                s.execute(update(AuditRow).where(AuditRow.id == audit_id).values(receipt_id=published.id))
            s.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "This transaction already published a different audit") from exc
        current = s.get(AuditRow, audit_id)
        s.refresh(current)
        if current.status != "published" or current.transaction_hash != tx_hash:
            raise HTTPException(409, "Audit changed during confirmation; manual review required")
        return _published(current)


def _published(row: AuditRow) -> dict[str, Any]:
    return {
        "status": "published",
        "audit_id": row.id,
        "receipt_id": row.receipt_id,
        "transaction_hash": row.transaction_hash,
        "trace_hash": row.trace_hash,
        "merkle_root": row.merkle_root,
        "trace_cid": row.trace_cid,
        "publisher": row.auditor,
        "verify": f"/verify/{row.receipt_id}",
    }
