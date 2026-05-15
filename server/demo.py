"""Free-trial demo endpoint — re-emits the latest trace for a market with the
caller's wallet address attached as the on-chain consumer.

Purpose: gives an external user (someone who connected a wallet on
`/try-live`) a real, attributable on-chain receipt without making them
acquire testnet USDC or sign EIP-3009 typed-data. The agent operator covers
the ~$0.0007 USDC of gas; the user gets a Receipt event with THEIR address
in the consumer field, which surfaces them in the `distinct_consumers`
stat.

Design choices:
* **No new ensemble run.** We fetch the most recent rr-trace/3 row for the
  market and re-publish it on V2 with the caller's address. That keeps
  Gemini cost flat at zero per demo call.
* **Rate-limited per consumer_address** — in-process token bucket, 1 call
  per 60 s and 5 calls per UTC day. Enough to demo, not enough to spam.
* **Address validation** — must be a checksum-able 0x-prefixed 20-byte hex
  string. Anything else returns 400.
* **No DB row if no cached receipt exists** for that market — we 404 so the
  caller knows to pick a different market, instead of silently doing
  nothing useful.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from threading import Lock

from eth_account import Account
from eth_account.messages import encode_defunct
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import desc, select

from storage.db import Receipt as ReceiptRow
from storage.db import Session

router = APIRouter(prefix="/demo", tags=["demo"])
logger = logging.getLogger(__name__)


_ETH_ADDR = re.compile(r"^0x[0-9a-fA-F]{40}$")
_HEX_SIG = re.compile(r"^0x[0-9a-fA-F]{130}$")
_MIN_GAP_S = 60.0
_MAX_PER_DAY = 5
_MAX_SIG_AGE_S = 300  # 5-minute clock skew allowance

# Rate-limit state — in-process, fine for a single-uvicorn deployment.
# (Restart resets the limiter; that's acceptable for the trial surface.)
_lock = Lock()
_last_call: dict[str, float] = {}
_calls_per_day: dict[str, deque[float]] = defaultdict(deque)


class DemoRequest(BaseModel):
    consumer_address: str = Field(..., description="EIP-55 0x… address to attribute the receipt to.")
    signature: str = Field(..., description="65-byte hex signature over the domain message below.")
    nonce: str = Field(..., description="Random hex nonce included in the signed message.")
    timestamp: str = Field(..., description="ISO 8601 timestamp included in the signed message. Must be within 5 min of server now.")


def _build_demo_message(*, market_id: str, consumer: str, nonce: str, timestamp: str) -> str:
    """The exact plaintext the client signs. Both sides reconstruct it identically — any
    drift in whitespace, ordering, or wording breaks signature recovery."""
    return (
        "ReasoningReceipt - demo authorization\n"
        f"market: {market_id}\n"
        f"consumer: {consumer}\n"
        f"nonce: {nonce}\n"
        f"timestamp: {timestamp}\n"
        "\n"
        "By signing, I authorize the oracle to emit a demo receipt attributed to my "
        "wallet on Arc Testnet. No payment required."
    )


def _verify_signed_demo(*, market_id: str, body: DemoRequest) -> None:
    """Recover the signer from the signed domain message and assert it matches
    `body.consumer_address`. Also enforces a 5-minute timestamp window so old
    signatures can't be replayed indefinitely."""
    if not _HEX_SIG.match(body.signature):
        raise HTTPException(status_code=400, detail="invalid signature shape (expect 0x + 130 hex chars)")
    try:
        ts = datetime.fromisoformat(body.timestamp.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="invalid timestamp (need ISO 8601)") from None
    age = (datetime.now(UTC) - (ts if ts.tzinfo else ts.replace(tzinfo=UTC))).total_seconds()
    if abs(age) > _MAX_SIG_AGE_S:
        raise HTTPException(
            status_code=400,
            detail=f"timestamp out of window (Δ={int(age)}s, max ±{_MAX_SIG_AGE_S}s). Re-sign with a fresh message.",
        )
    if not body.nonce or len(body.nonce) < 8:
        raise HTTPException(status_code=400, detail="nonce too short (min 8 chars)")

    message = _build_demo_message(
        market_id=market_id,
        consumer=body.consumer_address,
        nonce=body.nonce,
        timestamp=body.timestamp,
    )
    try:
        encoded = encode_defunct(text=message)
        recovered = Account.recover_message(encoded, signature=body.signature)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"signature recovery failed: {exc!s}") from None

    if recovered.lower() != body.consumer_address.lower():
        raise HTTPException(
            status_code=401,
            detail=f"signer ({recovered}) does not match consumer_address ({body.consumer_address})",
        )


class DemoResponse(BaseModel):
    receipt_id: int
    market_id: str
    market_question: str | None
    probability: float
    confidence: float
    trace_hash: str
    trace_cid: str
    merkle_root: str | None
    arc_tx_hash: str | None
    schema_version: str
    consumer_address: str
    note: str


def _normalize_address(raw: str) -> str:
    if not _ETH_ADDR.match(raw):
        raise HTTPException(status_code=400, detail="invalid Ethereum address")
    return raw.lower()


def _check_rate_limit(addr: str) -> None:
    now = time.time()
    with _lock:
        last = _last_call.get(addr, 0.0)
        if now - last < _MIN_GAP_S:
            wait = int(_MIN_GAP_S - (now - last))
            raise HTTPException(
                status_code=429,
                detail=f"slow down — try again in ~{wait}s (1 demo call per minute per address)",
            )
        # Prune calls older than 24h, then check daily cap.
        day_ago = now - 86_400
        bucket = _calls_per_day[addr]
        while bucket and bucket[0] < day_ago:
            bucket.popleft()
        if len(bucket) >= _MAX_PER_DAY:
            raise HTTPException(
                status_code=429,
                detail=f"daily demo cap reached ({_MAX_PER_DAY}/24h). Try a different wallet, or come back tomorrow.",
            )
        _last_call[addr] = now
        bucket.append(now)


def _latest_receipt_for(market_id: str) -> ReceiptRow | None:
    with Session() as session:
        stmt = (
            select(ReceiptRow)
            .where(
                ReceiptRow.market_id == market_id,
                ReceiptRow.schema_version == "rr-trace/3",
                ReceiptRow.merkle_root.isnot(None),
            )
            .order_by(desc(ReceiptRow.id))
            .limit(1)
        )
        return session.execute(stmt).scalar_one_or_none()


def _list_markets_with_receipts(limit: int = 25) -> list[dict]:
    """Return distinct market_id / market_question pairs that have at least one
    rr-trace/3 receipt — these are the only ones the demo endpoint can serve."""
    with Session() as session:
        stmt = (
            select(
                ReceiptRow.market_id,
                ReceiptRow.market_source,
                ReceiptRow.market_question,
                ReceiptRow.category,
            )
            .where(ReceiptRow.schema_version == "rr-trace/3")
            .order_by(desc(ReceiptRow.id))
        )
        seen: dict[str, dict] = {}
        for row in session.execute(stmt):
            mid = row.market_id
            if mid in seen:
                continue
            seen[mid] = {
                "market_id": mid,
                "market_source": row.market_source,
                "market_question": row.market_question,
                "category": row.category,
            }
            if len(seen) >= limit:
                break
        return list(seen.values())


@router.get("/markets")
async def list_demo_markets(limit: int = 25) -> dict:
    """Markets a /try-live caller can pick from — only those with a cached v3 receipt."""
    return {"markets": _list_markets_with_receipts(limit=limit)}


@router.get("/message")
async def get_demo_message(
    market_id: str,
    consumer: str,
    nonce: str,
    timestamp: str,
) -> dict:
    """Returns the EXACT plaintext the client should sign. Avoids any whitespace
    drift between client and server — they construct from the same source.

    The client can also build the message locally with the same template; this
    endpoint exists mainly for debugging and to keep the format authoritative.
    """
    return {
        "message": _build_demo_message(
            market_id=market_id,
            consumer=consumer,
            nonce=nonce,
            timestamp=timestamp,
        )
    }


@router.post("/price/{market_id}", response_model=DemoResponse)
async def demo_price(market_id: str, body: DemoRequest, request: Request) -> DemoResponse:
    addr = _normalize_address(body.consumer_address)
    _verify_signed_demo(market_id=market_id, body=body)
    _check_rate_limit(addr)

    cached = _latest_receipt_for(market_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=f"no cached v3 receipt for market {market_id}. Pick another market.",
        )

    chain = request.app.state.chain
    publish = chain.publish_v2(
        consumer_address=addr,
        market_id=market_id,
        probability=cached.probability,
        confidence=cached.confidence,
        trace_hash_hex=cached.trace_hash,
        merkle_root_hex=cached.merkle_root or "0x" + "00" * 32,
        schema_version=cached.schema_version or "rr-trace/3",
        trace_cid=cached.trace_cid,
    )

    with Session() as session:
        row = ReceiptRow(
            chain_receipt_id=publish.receipt_id,
            market_id=market_id,
            market_question=cached.market_question,
            market_source=cached.market_source,
            probability=cached.probability,
            confidence=cached.confidence,
            trace_hash=cached.trace_hash,
            trace_cid=cached.trace_cid,
            consumer_address=addr,
            publisher_address=chain.publisher_address,
            paid_micro_usdc=0,
            arc_tx_hash=publish.tx_hash,
            arc_block_number=publish.block_number,
            latency_ms=0,
            schema_version=cached.schema_version or "rr-trace/3",
            disagreement_pp=cached.disagreement_pp,
            merkle_root=cached.merkle_root,
            category=cached.category,
        )
        session.add(row)
        session.flush()
        new_id = row.id
        broker_row = {
            "id": row.id,
            "market_id": row.market_id,
            "market_source": row.market_source,
            "market_question": row.market_question,
            "probability": row.probability,
            "confidence": row.confidence,
            "trace_hash": row.trace_hash,
            "trace_cid": row.trace_cid,
            "consumer_address": row.consumer_address,
            "arc_tx_hash": row.arc_tx_hash,
            "paid_micro_usdc": row.paid_micro_usdc,
            "created_at": datetime.now(UTC).isoformat() + "Z",
            "schema_version": row.schema_version,
            "disagreement_pp": row.disagreement_pp,
            "merkle_root": row.merkle_root,
            "category": row.category,
        }

    broker = getattr(request.app.state, "broker", None)
    if broker is not None:
        await broker.publish(broker_row)

    logger.info(
        "demo: market=%s consumer=%s -> receipt #%d tx=%s",
        market_id,
        addr,
        new_id,
        (publish.tx_hash or "")[:12],
    )

    return DemoResponse(
        receipt_id=new_id,
        market_id=market_id,
        market_question=cached.market_question,
        probability=cached.probability,
        confidence=cached.confidence,
        trace_hash=cached.trace_hash,
        trace_cid=cached.trace_cid,
        merkle_root=cached.merkle_root,
        arc_tx_hash=publish.tx_hash,
        schema_version=cached.schema_version or "rr-trace/3",
        consumer_address=addr,
        note="Re-emitted cached v3 trace on Arc with your wallet as consumer. No payment required — the operator covers gas (~$0.0007). Receipt is real, byte-identical to the original.",
    )
