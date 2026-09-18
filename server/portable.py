"""Domain-neutral ReasoningReceipt HTTP API.

This is the product-facing surface for any AI decision or action. All
protocol logic lives in the `protocol` package — these routes are thin
consumers, never the source of truth. The older oracle routes remain
available as one adapter built on top of the protocol.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from protocol.receipt import (
    PortableReceipt,
    ReceiptEdge,
    ReceiptNode,
    restore_receipt,
    verify_proof_document,
)
from protocol.signatures import signature_backend
from protocol.verify import supported_schemas, verify_any

router = APIRouter(prefix="/v1", tags=["portable receipts"])


class NodeInput(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=64)
    payload: Any
    meta: dict[str, Any] | None = None


class EdgeInput(BaseModel):
    src: str = Field(min_length=1, max_length=128, alias="from")
    dst: str = Field(min_length=1, max_length=128, alias="to")
    rel: str = Field(min_length=1, max_length=64)

    model_config = {"populate_by_name": True}


class CreateReceiptRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    nodes: list[NodeInput] = Field(min_length=1, max_length=1024)
    edges: list[EdgeInput] = Field(default_factory=list, max_length=4096)
    metadata: dict[str, Any] = Field(default_factory=dict)
    receipt_id: str | None = Field(default=None, max_length=128)
    produced_at: str | None = None


class VerifyReceiptRequest(BaseModel):
    receipt: dict[str, Any]
    expected_hash: str | None = None


class ReceiptProofRequest(BaseModel):
    receipt: dict[str, Any]
    node_id: str | None = None
    edge_index: int | None = None


class ProofDocumentRequest(BaseModel):
    proof: dict[str, Any]


def _restore_receipt(data: dict[str, Any]) -> PortableReceipt:
    try:
        return restore_receipt(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"invalid receipt: {exc}") from exc


@router.post("/receipts", status_code=201)
async def create_receipt(request: CreateReceiptRequest) -> dict[str, Any]:
    """Canonicalise evidence nodes and return a portable Merkle receipt."""
    try:
        receipt = PortableReceipt(
            subject=request.subject,
            metadata=request.metadata,
            nodes=[
                ReceiptNode(id=n.id, kind=n.kind, payload=n.payload, meta=n.meta)
                for n in request.nodes
            ],
            edges=[ReceiptEdge(src=e.src, dst=e.dst, rel=e.rel) for e in request.edges],
            **({"receipt_id": request.receipt_id} if request.receipt_id else {}),
            **({"produced_at": request.produced_at} if request.produced_at else {}),
        )
        return receipt.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/verify")
async def verify_portable_receipt(request: VerifyReceiptRequest) -> dict[str, Any]:
    """Verify a receipt locally; no chain, storage provider, or model is trusted."""
    report = verify_any(request.receipt, expected_hash=request.expected_hash)
    return report.to_dict()


@router.post("/inspect")
async def inspect_receipt(request: VerifyReceiptRequest) -> dict[str, Any]:
    """Structural summary + verification state for one receipt document."""
    report = verify_any(request.receipt, expected_hash=request.expected_hash)
    doc = request.receipt if isinstance(request.receipt, dict) else {}
    return {
        "schema_version": doc.get("schema_version"),
        "receipt_id": doc.get("receipt_id"),
        "subject": doc.get("subject"),
        "produced_at": doc.get("produced_at"),
        "nodes": [
            {"id": n.get("id"), "kind": n.get("kind"), "payload": n.get("payload")}
            for n in doc.get("nodes") or []
            if isinstance(n, dict)
        ],
        "edges": doc.get("edges") or [],
        "signatures": doc.get("signatures") or [],
        "verification": report.to_dict(),
    }


@router.post("/proofs", status_code=200)
async def create_node_proof(request: ReceiptProofRequest) -> dict[str, Any]:
    """Create a compact inclusion proof for one node or edge in a receipt."""
    report = verify_any(request.receipt)
    if not report.valid:
        raise HTTPException(status_code=422, detail="receipt commitments do not verify")
    receipt = _restore_receipt(request.receipt)
    try:
        if request.node_id is not None:
            return receipt.proof_for(request.node_id)
        if request.edge_index is not None:
            return receipt.proof_for_edge(request.edge_index)
        raise HTTPException(status_code=422, detail="pass node_id or edge_index")
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/proofs/verify")
async def verify_proof(request: ProofDocumentRequest) -> dict[str, Any]:
    """Verify a standalone inclusion proof document — fully offline check."""
    return {"valid": verify_proof_document(request.proof)}


@router.get("/schemas")
async def list_schemas() -> dict[str, Any]:
    """Schema versions this server verifies, with canonicalization ids."""
    return {"schemas": supported_schemas()}


@router.get("/capabilities")
async def capabilities() -> dict[str, Any]:
    """What this deployment can do — discovery for agents and SDKs."""
    return {
        "protocol": "reasoning-receipt/1",
        "canonicalization": "rr-json-1",
        "signature_backend": signature_backend(),
        "features": [
            "create",
            "verify",
            "inspect",
            "proofs",
            "proof_verify",
            "schemas",
            "legacy_schemas",
        ],
        "schemas": [s["schema_version"] for s in supported_schemas()],
    }
