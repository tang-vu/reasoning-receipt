"""Receipt broker + SSE endpoint tests."""

from __future__ import annotations

import asyncio

import pytest

from server.events import ReceiptBroker


@pytest.mark.asyncio
async def test_broker_fan_out() -> None:
    """A single publish reaches every subscriber's queue."""
    broker = ReceiptBroker()

    async with broker.subscribe() as q1, broker.subscribe() as q2:
        assert broker.subscriber_count() == 2
        await broker.publish({"id": 1, "market_id": "test"})
        ev1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        ev2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert ev1["id"] == 1
        assert ev2["id"] == 1

    assert broker.subscriber_count() == 0


@pytest.mark.asyncio
async def test_broker_drops_slow_subscriber() -> None:
    """A subscriber whose queue is full gets dropped silently."""
    broker = ReceiptBroker()
    async with broker.subscribe() as q:
        # Fill the queue to maxsize — pull source of truth from the queue itself.
        capacity = q.maxsize
        for i in range(capacity):
            await broker.publish({"id": i})
        assert q.qsize() == capacity
        # One more publish must NOT raise — it just discards this subscriber.
        await broker.publish({"id": 9999})
    # Subscriber dropped after the overflow.
    assert broker.subscriber_count() == 0


def test_sse_router_is_registered() -> None:
    """The /events/stream route exists in the FastAPI app and is mounted by the SSE router.

    Integration testing the SSE response itself requires a running uvicorn + a real HTTP
    client — TestClient buffers the response, which deadlocks the never-ending stream.
    The broker unit tests above cover the fan-out semantics.
    """
    from server.main import create_app

    app = create_app()
    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/events/stream" in paths
