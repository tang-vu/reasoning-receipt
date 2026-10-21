"""Wallet-approved settlement of an audited receipt, prepared through Aomi.

Flow: an audit the independent auditor approved and published on chain (see
``server.audit``) -> ``/prepare`` refuses anything else, simulates the
configured USDC transfer from the connected wallet and returns unsigned
calldata -> the Aomi app stages it, the host simulates it and the
owner approves it in their wallet -> ``/verify`` checks the finalized chain
receipt independently and records a separate outcome receipt that links back
to the audited trace. Pending, sealed, rejected or unknown audits never settle,
so a failed or inconclusive audit blocks payment.

The chain, token, recipient and amount come only from the deployment JSON in
``RR_SETTLEMENT_CONFIG`` (the same file the Aomi app is built from). Without
it, or with ``enabled`` false, every route refuses: transfers stay disabled
until a recipient is configured.
"""

from __future__ import annotations

import hmac
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from protocol.receipt import PortableReceipt, ReceiptNode
from storage.db import Audit as AuditRow
from storage.db import Session
from storage.db import Settlement as SettlementRow

router = APIRouter(prefix="/v1/settlements", tags=["settlements"])

ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
TX_HASH = re.compile(r"^0x[0-9a-fA-F]{64}$")
# keccak256("transfer(address,uint256)")[:4] and keccak256("Transfer(address,address,uint256)")
TRANSFER_SELECTOR = "0xa9059cbb"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


class PrepareRequest(BaseModel):
    audit_id: int = Field(gt=0)
    execution_account: str = Field(min_length=42, max_length=42)
    chain_id: int


class VerifyRequest(BaseModel):
    audit_id: int = Field(gt=0)
    transaction_hash: str = Field(min_length=66, max_length=66)


def _deployment(authorization: str | None) -> dict[str, Any]:
    """Authorize the caller and load the deployment-bound transfer, or refuse."""
    path = os.getenv("RR_SETTLEMENT_CONFIG", "")
    config = json.loads(Path(path).read_text()) if path else {"enabled": False}
    if config.get("enabled") is not True:
        raise HTTPException(503, "Settlement transfers are disabled until a recipient is configured")
    token = os.getenv("RR_SETTLEMENT_API_TOKEN", "")
    if not token or not hmac.compare_digest(authorization or "", f"Bearer {token}"):
        raise HTTPException(401, "Settlement access denied")
    if not os.getenv("RR_SETTLEMENT_RPC_URL"):
        raise HTTPException(503, "Settlement RPC is not configured; do not submit a payment")
    for key in ("token", "recipient"):
        if not ADDRESS.match(str(config.get(key, ""))) or int(config[key], 16) == 0:
            raise HTTPException(503, f"Settlement deployment has no valid {key}")
    amount = str(config.get("amount_units", ""))
    chain_id = config.get("chain_id")
    if not amount.isdigit() or int(amount) == 0 or not isinstance(chain_id, int) or chain_id <= 0:
        raise HTTPException(503, "Settlement deployment has no valid chain or amount")
    return {
        "chain_id": chain_id,
        "token": config["token"].lower(),
        "recipient": config["recipient"].lower(),
        "amount_units": str(int(amount)),
    }


def _rpc(method: str, params: list[Any]) -> dict[str, Any]:
    """One JSON-RPC call; the caller decides what a missing result means."""
    try:
        response = httpx.post(
            os.environ["RR_SETTLEMENT_RPC_URL"],
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=20,
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(503, "Settlement RPC unavailable; do not submit or record a payment") from exc


@router.post("/prepare")
def prepare_settlement(
    request: PrepareRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Require a published audit, simulate the exact transfer and return it unsigned."""
    d = _deployment(authorization)
    payer = request.execution_account.lower()
    if not ADDRESS.match(payer) or int(payer, 16) == 0:
        raise HTTPException(422, "Connect the paying wallet; no address override is accepted")
    if request.chain_id != d["chain_id"]:
        raise HTTPException(409, "Connected wallet is on the wrong network")
    # Audit gate: only a trace the auditor approved and that ``/published``
    # confirmed on chain can be paid for.
    with Session() as s:
        audit = s.get(AuditRow, request.audit_id)
        if audit is None:
            raise HTTPException(404, "No audit with this id; nothing was prepared")
        if audit.status == "rejected":
            raise HTTPException(409, "The audit rejected this trace; settlement is blocked")
        if audit.status != "published" or not audit.trace_hash or not audit.transaction_hash:
            raise HTTPException(409, "This trace has no published audit yet; settlement is blocked")
        source = {
            "audit_id": audit.id,
            "receipt_id": audit.receipt_id,
            "trace_hash": audit.trace_hash,
            "merkle_root": audit.merkle_root,
            "trace_cid": audit.trace_cid,
            "auditor": audit.auditor,
            "audit_transaction_hash": audit.transaction_hash,
            "registry": audit.registry,
            "chain_id": audit.chain_id,
        }
    source_hash = source["trace_hash"].lower()

    data = TRANSFER_SELECTOR + d["recipient"][2:].rjust(64, "0") + f"{int(d['amount_units']):064x}"
    if _rpc("eth_chainId", []).get("result") != hex(d["chain_id"]):
        raise HTTPException(503, "Settlement RPC is on a different chain; nothing was prepared")
    # Simulation gate: no calldata leaves this route unless the exact transfer
    # succeeds from the connected wallet against current chain state.
    simulated = _rpc("eth_call", [{"from": payer, "to": d["token"], "data": data, "value": "0x0"}, "latest"])
    if "error" in simulated or int(simulated.get("result") or "0x0", 16) != 1:
        raise HTTPException(409, "Simulation failed; nothing was prepared and nothing may be submitted")

    # Keep the audit reference exactly as it was when the payment was prepared.
    stored = json.dumps(source, sort_keys=True, separators=(",", ":"))
    with Session() as s:
        row = s.scalars(select(SettlementRow).where(SettlementRow.source_receipt_hash == source_hash)).first()
        if row is not None and row.status == "settled":
            raise HTTPException(
                409, "This receipt is already settled; verify its transaction instead of paying again"
            )
        if row is None:
            s.add(
                SettlementRow(
                    source_receipt_hash=source_hash,
                    source_receipt=stored,
                    payer=payer,
                    **d,
                )
            )
        else:
            row.payer = payer
            row.chain_id, row.token = d["chain_id"], d["token"]
            row.recipient, row.amount_units = d["recipient"], d["amount_units"]
        try:
            s.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "This receipt is being prepared concurrently; retry") from exc

    return {
        "status": "prepared",
        "audit_id": source["audit_id"],
        "receipt_id": source["receipt_id"],
        "trace_hash": source_hash,
        "merkle_root": source["merkle_root"],
        "payer": payer,
        **d,
        "transaction": {"to": d["token"], "chain_id": d["chain_id"], "value": "0", "data": data},
    }


@router.post("/verify")
def verify_settlement(
    request: VerifyRequest, authorization: str | None = Header(default=None)
) -> dict[str, Any]:
    """Check the finalized transfer on chain and record one linked outcome receipt.

    Safe to repeat. Only ``settled`` is success; ``pending``,
    ``pending_finality`` and ``reverted`` record nothing.
    """
    d = _deployment(authorization)
    tx_hash = request.transaction_hash.lower()
    if not TX_HASH.match(tx_hash):
        raise HTTPException(422, "Provide the audit id and the wallet's 32-byte transaction hash")
    with Session() as s:
        audit = s.get(AuditRow, request.audit_id)
        if audit is None or audit.status != "published" or not audit.trace_hash:
            raise HTTPException(404, "No prepared settlement for this receipt")
        source_hash = audit.trace_hash.lower()
        row = s.scalars(select(SettlementRow).where(SettlementRow.source_receipt_hash == source_hash)).first()
        if row is None:
            raise HTTPException(404, "No prepared settlement for this receipt")
        if row.status == "settled":
            if row.transaction_hash != tx_hash:
                raise HTTPException(409, "This receipt was already settled by a different transaction")
            return {"status": "settled", "outcome_receipt": json.loads(row.outcome_receipt)}
        if s.scalars(select(SettlementRow).where(SettlementRow.transaction_hash == tx_hash)).first():
            raise HTTPException(409, "This transaction already settled a different receipt")
        if (row.chain_id, row.token, row.recipient, row.amount_units) != (
            d["chain_id"],
            d["token"],
            d["recipient"],
            d["amount_units"],
        ):
            raise HTTPException(409, "Deployment changed since preparation; prepare and approve again")
        row_id, payer, source = row.id, row.payer, json.loads(row.source_receipt)

    if _rpc("eth_chainId", []).get("result") != hex(d["chain_id"]):
        raise HTTPException(503, "Settlement RPC is on a different chain; nothing was recorded")
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

    recipient_topic = "0x" + d["recipient"][2:].rjust(64, "0")
    transfers = [
        log
        for log in receipt.get("logs", [])
        if str(log.get("address", "")).lower() == d["token"]
        and len(log.get("topics", [])) == 3
        and log["topics"][0].lower() == TRANSFER_TOPIC
        and log["topics"][2].lower() == recipient_topic
    ]
    if (
        len(transfers) != 1
        or transfers[0]["topics"][1].lower() != "0x" + payer[2:].rjust(64, "0")
        or int(transfers[0]["data"], 16) != int(d["amount_units"])
    ):
        raise HTTPException(409, "Transaction does not contain the exact configured transfer")

    outcome = PortableReceipt(
        subject=f"settlement:{source_hash}",
        metadata={"links": {"audited_trace_hash": source_hash, "audit_id": source["audit_id"]}},
        nodes=[
            ReceiptNode(
                id="source",
                kind="reference",
                payload=source,
            ),
            ReceiptNode(
                id="transfer",
                kind="transaction",
                payload={
                    "chain_id": d["chain_id"],
                    "token": d["token"],
                    "from": payer,
                    "to": d["recipient"],
                    "amount_units": d["amount_units"],
                    "transaction_hash": tx_hash,
                    "block_number": block_number,
                    "block_hash": receipt["blockHash"].lower(),
                    "log_index": int(transfers[0]["logIndex"], 16),
                },
            ),
            ReceiptNode(
                id="verification",
                kind="policy",
                payload={
                    "finalized_block": int(finalized["number"], 16),
                    "checks": [
                        "audit_published",
                        "chain_id",
                        "receipt_status",
                        "finality",
                        "canonical_block",
                        "single_exact_transfer_log",
                    ],
                },
            ),
            ReceiptNode(id="outcome", kind="outcome", payload={"status": "settled"}),
        ],
    )
    envelope = {**outcome.to_dict(), "receipt_hash": outcome.receipt_hash()}

    with Session() as s:
        try:
            # Conditional write: only a still-prepared row for this payer can
            # settle, so concurrent or repeated verifications record one success.
            claimed = s.execute(
                update(SettlementRow)
                .where(
                    SettlementRow.id == row_id,
                    SettlementRow.status == "prepared",
                    SettlementRow.payer == payer,
                )
                .values(
                    status="settled",
                    transaction_hash=tx_hash,
                    outcome_receipt=json.dumps(envelope, sort_keys=True, separators=(",", ":")),
                    settled_at=datetime.now(UTC),
                )
            ).rowcount
            s.flush()
        except IntegrityError as exc:
            raise HTTPException(409, "This transaction already settled a different receipt") from exc
        if claimed != 1:
            row = s.get(SettlementRow, row_id)
            if row is None or row.status != "settled" or row.transaction_hash != tx_hash:
                raise HTTPException(409, "Settlement changed during verification; manual review required")
            return {"status": "settled", "outcome_receipt": json.loads(row.outcome_receipt)}
    return {"status": "settled", "outcome_receipt": envelope}
