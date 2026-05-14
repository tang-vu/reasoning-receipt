"""Paywalled MCP-style HTTP endpoint — agents pay x402 to query the oracle.

Mirrors the convention competitor projects use ("pay $0.01 USDC to call the
auditor tool"): a single HTTP endpoint behind the same x402 paywall as
`/price/{market_id}`, but returning the **cached** latest reasoning trace
for a market instead of triggering a fresh ensemble run. Lets a downstream
agent buy the most-recent verified probability without paying the upstream
cost of regenerating it.

Two tools exposed at `/mcp/v1/...`:

  GET /mcp/v1/get_price/{market_id}
    → latest cached price + trace pointer + Arc tx hash + Merkle root,
      gated by 0.01 USDC x402 settlement.

  GET /mcp/v1/audit/{receipt_id}
    → byte-for-byte re-verification of a given receipt against Irys.
      Gated by the same x402 paywall.

The free `/receipts` and `/verify/{id}` endpoints still work for the public
dashboard; this router is the agent-to-agent commercial path.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import desc, select

from storage.db import Receipt as ReceiptRow
from storage.db import Session
from storage.irys import canonical_bytes, sha256_hex

from .verify import _fetch_trace_via_cid

router = APIRouter(tags=["mcp"], prefix="/mcp/v1")


class CachedPrice(BaseModel):
    market_id: str
    market_question: str | None
    probability: float
    confidence: float
    schema_version: str | None
    disagreement_pp: float | None
    merkle_root: str | None
    trace_hash: str
    trace_cid: str
    arc_tx_hash: str | None
    receipt_id: int
    paid_by_caller: float  # USDC paid for THIS call
    created_at: str | None


class AuditResult(BaseModel):
    receipt_id: int
    verified: bool
    reason: str
    stored_hash: str
    recomputed_hash: str | None
    irys_gateway_url: str | None
    paid_by_caller: float


@router.get("/get_price/{market_id}", response_model=CachedPrice)
async def get_price_paywalled(market_id: str, request: Request) -> CachedPrice:
    """Return the freshest cached receipt for a market. x402-gated."""
    paywall = request.app.state.paywall
    payment_header = request.headers.get("x-payment")
    if not payment_header:
        return paywall.challenge_response(f"/mcp/v1/get_price/{market_id}")
    evidence = paywall.verify(request, payment_header)

    with Session() as session:
        row = session.execute(
            select(ReceiptRow)
            .where(ReceiptRow.market_id == market_id)
            .order_by(desc(ReceiptRow.created_at))
            .limit(1)
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail=f"no receipt for market_id={market_id}")

        return CachedPrice(
            market_id=row.market_id,
            market_question=row.market_question,
            probability=row.probability,
            confidence=row.confidence,
            schema_version=row.schema_version,
            disagreement_pp=row.disagreement_pp,
            merkle_root=row.merkle_root,
            trace_hash=row.trace_hash,
            trace_cid=row.trace_cid,
            arc_tx_hash=row.arc_tx_hash,
            receipt_id=row.id,
            paid_by_caller=evidence.settled_amount_micro_usdc / 1_000_000,
            created_at=_iso_utc(row.created_at),
        )


@router.get("/audit/{receipt_id}", response_model=AuditResult)
async def audit_receipt_paywalled(receipt_id: int, request: Request) -> AuditResult:
    """Re-fetch the trace from Irys, re-canonicalise, re-hash, compare. x402-gated."""
    paywall = request.app.state.paywall
    payment_header = request.headers.get("x-payment")
    if not payment_header:
        return paywall.challenge_response(f"/mcp/v1/audit/{receipt_id}")
    evidence = paywall.verify(request, payment_header)

    with Session() as session:
        row = session.get(ReceiptRow, receipt_id)
        if row is None:
            raise HTTPException(status_code=404, detail="receipt not found")
        stored_hash = row.trace_hash
        trace_cid = row.trace_cid

    fetched = _fetch_trace_via_cid(trace_cid)
    if fetched is None:
        return AuditResult(
            receipt_id=receipt_id,
            verified=False,
            reason="trace fetch via Irys gateway failed",
            stored_hash=stored_hash,
            recomputed_hash=None,
            irys_gateway_url=(
                f"https://gateway.irys.xyz/{trace_cid.removeprefix('ar://')}"
                if trace_cid
                else None
            ),
            paid_by_caller=evidence.settled_amount_micro_usdc / 1_000_000,
        )

    recomputed = sha256_hex(canonical_bytes(fetched))
    matches = recomputed.lower() == stored_hash.lower()
    return AuditResult(
        receipt_id=receipt_id,
        verified=matches,
        reason="byte-for-byte match" if matches else "hash mismatch — trace tampered or stale",
        stored_hash=stored_hash,
        recomputed_hash=recomputed,
        irys_gateway_url=f"https://gateway.irys.xyz/{trace_cid.removeprefix('ar://')}",
        paid_by_caller=evidence.settled_amount_micro_usdc / 1_000_000,
    )


def _iso_utc(dt) -> str | None:
    """ISO with explicit UTC suffix — matches routes._iso_utc convention."""
    if dt is None:
        return None
    s = dt.isoformat()
    if not s.endswith("Z") and "+" not in s[10:]:
        s += "Z"
    return s
