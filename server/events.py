"""SSE event broker — live receipt stream.

A minimal pub/sub for in-process fan-out. Every new receipt published by
`/price` (or by the agent loop hitting the same broker) lands in every
subscriber's queue. Subscribers are SSE clients reading `/events/stream`.

This is glue, not infrastructure: when the deployment grows to multiple
workers, replace with Redis pub/sub. For the hackathon, single-process
async queues are enough.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request
from sse_starlette.sse import EventSourceResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["events"])

_HEARTBEAT_SECONDS = 15
_QUEUE_MAX = 200  # drops the oldest events if a slow client falls behind


class ReceiptBroker:
    """In-process fan-out for receipt events. Thread-safe via the asyncio loop."""

    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._lock = asyncio.Lock()

    async def publish(self, event: dict[str, Any]) -> None:
        """Push `event` to every connected subscriber. Drops on full queue."""
        async with self._lock:
            dead: list[asyncio.Queue[dict[str, Any]]] = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    dead.append(q)
            for q in dead:
                self._subscribers.discard(q)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[asyncio.Queue[dict[str, Any]]]:
        """Async-context-managed subscription. Cleans up on disconnect."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=_QUEUE_MAX)
        async with self._lock:
            self._subscribers.add(q)
        try:
            yield q
        finally:
            async with self._lock:
                self._subscribers.discard(q)

    def subscriber_count(self) -> int:
        return len(self._subscribers)


async def poll_db_and_broadcast(broker: ReceiptBroker, *, interval_s: float = 2.0) -> None:
    """Watch the DB for new receipts and fan them out to SSE subscribers.

    The agent loop emits via `chain.publish_v2` directly — it never hits the
    FastAPI `/price` endpoint, so the broker's in-process publish never
    fires for those rows. This background task closes that gap by polling
    `SELECT id FROM receipts WHERE id > last_seen` every `interval_s`
    seconds and broadcasting each new row.

    Cheap: SQLite single-row lookup, no joins. Restarts gracefully if the
    DB is briefly locked during a daemon write.
    """
    from sqlalchemy import desc, select

    from storage.db import Receipt as ReceiptRow
    from storage.db import Session

    def _to_event(r: ReceiptRow) -> dict[str, Any]:
        return {
            "id": r.id,
            "market_id": r.market_id,
            "market_source": r.market_source,
            "market_question": r.market_question,
            "probability": r.probability,
            "confidence": r.confidence,
            "trace_hash": r.trace_hash,
            "trace_cid": r.trace_cid,
            "consumer_address": r.consumer_address,
            "arc_tx_hash": r.arc_tx_hash,
            "paid_micro_usdc": r.paid_micro_usdc,
            "created_at": _iso_utc(r.created_at),
            "schema_version": r.schema_version,
            "disagreement_pp": r.disagreement_pp,
            "merkle_root": r.merkle_root,
            "category": r.category,
        }

    def _iso_utc(dt):
        if dt is None:
            return None
        s = dt.isoformat()
        return s if s.endswith("Z") or "+" in s[10:] else s + "Z"

    # Initial high-water mark = current max id so we don't replay history.
    last_seen = 0
    try:
        with Session() as session:
            top = session.execute(
                select(ReceiptRow.id).order_by(desc(ReceiptRow.id)).limit(1)
            ).scalar_one_or_none()
            if top is not None:
                last_seen = int(top)
    except Exception as exc:  # noqa: BLE001
        logger.warning("poll-broadcast: initial high-water lookup failed (%s)", exc)

    logger.info("poll-broadcast: starting from id=%d (interval=%.1fs)", last_seen, interval_s)

    while True:
        try:
            await asyncio.sleep(interval_s)
            # Build event dicts INSIDE the session so column reads don't
            # trigger DetachedInstanceError after the session closes.
            events: list[dict[str, Any]] = []
            with Session() as session:
                stmt = (
                    select(ReceiptRow)
                    .where(ReceiptRow.id > last_seen)
                    .order_by(ReceiptRow.id)
                    .limit(50)
                )
                for r in session.execute(stmt).scalars():
                    events.append(_to_event(r))
            for ev in events:
                await broker.publish(ev)
                last_seen = max(last_seen, ev["id"])
            if events:
                logger.info("poll-broadcast: fan-out %d row(s), last_seen=%d", len(events), last_seen)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("poll-broadcast: tick failed (%s); continuing", exc)


@router.get("/events/stream")
async def receipt_stream(request: Request) -> EventSourceResponse:
    """Server-Sent Events stream of receipt events.

    Emits an `event: receipt\\ndata: {...json...}` frame per receipt. Sends a
    heartbeat comment every 15 s so proxies don't close the connection.
    """

    broker: ReceiptBroker = request.app.state.broker

    async def gen():
        async with broker.subscribe() as q:
            yield {
                "event": "hello",
                "data": json.dumps(
                    {
                        "ok": True,
                        "subscribers": broker.subscriber_count(),
                        "heartbeat_seconds": _HEARTBEAT_SECONDS,
                    }
                ),
            }
            while True:
                if await request.is_disconnected():
                    return
                try:
                    event = await asyncio.wait_for(q.get(), timeout=_HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield {"comment": "heartbeat"}
                    continue
                yield {"event": "receipt", "data": json.dumps(event)}

    return EventSourceResponse(gen(), ping=20)
