"""Domain-neutral ReasoningReceipt HTTP API.

This is the product-facing surface for any AI decision or action.  The older
oracle routes remain available as one adapter built on top of the protocol.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from protocol.receipt import PortableReceipt, ReceiptNode, verify_receipt

router = APIRouter(prefix="/v1", tags=["portable receipts"])


class NodeInput(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    kind: str = Field(min_length=1, max_length=100)
    payload: dict[str, Any]


class CreateReceiptRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    nodes: list[NodeInput] = Field(min_length=1, max_length=128)
    metadata: dict[str, Any] = Field(default_factory=dict)


class VerifyReceiptRequest(BaseModel):
    receipt: dict[str, Any]


class ReceiptProofRequest(BaseModel):
    receipt: dict[str, Any]
    node_id: str = Field(min_length=1, max_length=100)


def _restore_receipt(data: dict[str, Any]) -> PortableReceipt:
    try:
        nodes = [
            ReceiptNode(id=node["id"], kind=node["kind"], payload=node["payload"])
            for node in data["nodes"]
        ]
        return PortableReceipt(
            receipt_id=data["receipt_id"],
            subject=data["subject"],
            produced_at=data["produced_at"],
            metadata=data.get("metadata", {}),
            nodes=nodes,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"invalid receipt: {exc}") from exc


@router.post("/receipts", status_code=201)
async def create_receipt(request: CreateReceiptRequest) -> dict[str, Any]:
    """Canonicalise evidence nodes and return a portable Merkle receipt."""
    try:
        receipt = PortableReceipt(
            subject=request.subject,
            metadata=request.metadata,
            nodes=[ReceiptNode(**node.model_dump()) for node in request.nodes],
        )
        envelope = receipt.to_dict()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**envelope, "receipt_hash": receipt.receipt_hash()}


@router.post("/verify")
async def verify_portable_receipt(request: VerifyReceiptRequest) -> dict[str, Any]:
    """Verify a receipt locally; no chain, storage provider, or model is trusted."""
    valid = verify_receipt(request.receipt)
    response: dict[str, Any] = {"valid": valid}
    if valid:
        response["receipt_hash"] = _restore_receipt(request.receipt).receipt_hash()
        response["node_count"] = len(request.receipt["nodes"])
    return response


@router.post("/proofs")
async def create_node_proof(request: ReceiptProofRequest) -> dict[str, Any]:
    """Create a compact inclusion proof for one node in a valid receipt."""
    if not verify_receipt(request.receipt):
        raise HTTPException(status_code=422, detail="receipt commitments do not verify")
    receipt = _restore_receipt(request.receipt)
    try:
        return receipt.proof_for(request.node_id).to_dict()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
