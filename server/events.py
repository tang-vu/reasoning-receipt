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
