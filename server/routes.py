"""FastAPI routes — paywalled /price, public /receipts, /stats, /traces.

`GET /price/{market_id}` is the headline endpoint:
1. Issues a 402 challenge if `X-PAYMENT` is missing.
2. Verifies + settles the payment via the x402 paywall.
3. Runs the analyst (cached per market_id for a short TTL).
4. Seals the trace (canonical → SHA-256 → Irys upload).
5. Emits Receipt on Arc.
6. Persists the row.
7. Returns price + trace pointer + on-chain refs.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import desc, func, select

from agent.analyst import Analyst, MarketCandidate
from agent.scanner import Scanner
from agent.trace import TraceSealer
from storage.db import Receipt as ReceiptRow
from storage.db import Session

router = APIRouter(tags=["oracle"])
logger = logging.getLogger(__name__)


class PriceResponse(BaseModel):
    market_id: str
    market_source: str
    question: str
    probability: float
    confidence: float
    claim: str
    summary: str
    trace_hash: str
    trace_cid: str
    receipt_id: int
    arc_tx_hash: str | None
    consumer_address: str | None
    paid_usdc: float
    latency_ms: int


class TraceRow(BaseModel):
    id: int
    market_id: str
    market_source: str
    market_question: str | None
    probability: float
    confidence: float
    trace_hash: str
    trace_cid: str
    consumer_address: str | None
    arc_tx_hash: str | None
    paid_micro_usdc: int
    created_at: str


class StatsResponse(BaseModel):
    total_receipts: int
    total_paid_micro_usdc: int
    distinct_markets: int
    distinct_consumers: int
    latest_receipt_at: str | None


@router.get("/price/{market_id}")
async def get_price(market_id: str, request: Request) -> PriceResponse:
    start = time.perf_counter()
    paywall = request.app.state.paywall
    payment_header = request.headers.get("x-payment")

    if not payment_header:
        return paywall.challenge_response(f"/price/{market_id}")

    evidence = paywall.verify(request, payment_header)

    candidate = _candidate_for(market_id)
    analyst: Analyst = request.app.state.analyst
    trace = analyst.analyse(candidate, consumer_address=evidence.payer_address)

    sealer: TraceSealer = request.app.state.sealer
    sealed = sealer.seal(trace)

    chain = request.app.state.chain
    publish = chain.publish(
        consumer_address=evidence.payer_address,
        market_id=market_id,
        probability=trace.probability,
        confidence=trace.confidence,
        trace_hash_hex=sealed.hash_hex,
        trace_cid=sealed.cid,
    )

    latency_ms = int((time.perf_counter() - start) * 1000)
    with Session() as session:
        row = ReceiptRow(
            chain_receipt_id=publish.receipt_id,
            market_id=market_id,
            market_question=candidate.question,
            market_source=candidate.source,
            probability=trace.probability,
            confidence=trace.confidence,
            trace_hash=sealed.hash_hex,
            trace_cid=sealed.cid,
            consumer_address=evidence.payer_address,
            publisher_address=chain.publisher_address,
            paid_micro_usdc=int(evidence.settled_amount_micro_usdc),
            arc_tx_hash=publish.tx_hash,
            arc_block_number=publish.block_number,
            latency_ms=latency_ms,
        )
        session.add(row)
        session.flush()
        broker_payload = _to_trace_row(row).model_dump()

    broker = getattr(request.app.state, "broker", None)
    if broker is not None:
        await broker.publish(broker_payload)

    return PriceResponse(
        market_id=market_id,
        market_source=candidate.source,
        question=candidate.question,
        probability=trace.probability,
        confidence=trace.confidence,
        claim=trace.claim,
        summary=trace.summary,
        trace_hash=sealed.hash_hex,
        trace_cid=sealed.cid,
        receipt_id=publish.receipt_id,
        arc_tx_hash=publish.tx_hash,
        consumer_address=evidence.payer_address,
        paid_usdc=evidence.settled_amount_micro_usdc / 1_000_000,
        latency_ms=latency_ms,
    )


@router.get("/receipts", response_model=list[TraceRow])
async def list_receipts(limit: int = Query(50, ge=1, le=500)) -> list[TraceRow]:
    rows: list[TraceRow] = []
    with Session() as session:
        for r in session.execute(
            select(ReceiptRow).order_by(desc(ReceiptRow.created_at)).limit(limit)
        ).scalars():
            rows.append(_to_trace_row(r))
    return rows


@router.get("/receipts/{receipt_id}", response_model=TraceRow)
async def get_receipt(receipt_id: int) -> TraceRow:
    with Session() as session:
        r = session.get(ReceiptRow, receipt_id)
        if r is None:
            raise HTTPException(status_code=404, detail="receipt not found")
        return _to_trace_row(r)


@router.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    with Session() as session:
        total = session.scalar(select(func.count(ReceiptRow.id))) or 0
        paid = session.scalar(select(func.coalesce(func.sum(ReceiptRow.paid_micro_usdc), 0))) or 0
        distinct_markets = session.scalar(
            select(func.count(func.distinct(ReceiptRow.market_id)))
        ) or 0
        distinct_consumers = session.scalar(
            select(func.count(func.distinct(ReceiptRow.consumer_address)))
        ) or 0
        latest = session.scalar(select(func.max(ReceiptRow.created_at)))
    return StatsResponse(
        total_receipts=total,
        total_paid_micro_usdc=int(paid),
        distinct_markets=distinct_markets,
        distinct_consumers=distinct_consumers,
        latest_receipt_at=latest.isoformat() if latest else None,
    )


@router.get("/healthz")
async def healthz(request: Request) -> dict:
    chain = request.app.state.chain
    return {
        "ok": True,
        "chain_mock": chain.mock,
        "publisher": chain.publisher_address,
    }


def _candidate_for(market_id: str) -> MarketCandidate:
    """Look up a previously-scanned candidate, else synthesize one."""
    scanner: Scanner | None = None
    try:
        scanner = Scanner()
    except Exception:
        scanner = None
    if scanner is not None and scanner.mock:
        for c in scanner.scan():
            if c.market_id == market_id:
                return c
    return MarketCandidate(
        market_id=market_id,
        source="polymarket",
        question=f"Will the outcome of '{market_id}' resolve YES?",
        end_date=None,
        liquidity_usd=50_000.0,
    )


def _to_trace_row(r: ReceiptRow) -> TraceRow:
    return TraceRow(
        id=r.id,
        market_id=r.market_id,
        market_source=r.market_source,
        market_question=r.market_question,
        probability=r.probability,
        confidence=r.confidence,
        trace_hash=r.trace_hash,
        trace_cid=r.trace_cid,
        consumer_address=r.consumer_address,
        arc_tx_hash=r.arc_tx_hash,
        paid_micro_usdc=r.paid_micro_usdc,
        created_at=r.created_at.isoformat() if r.created_at else "",
    )
