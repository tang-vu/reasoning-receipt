"""Bounded cron entry points for serverless deployments."""

from __future__ import annotations

import asyncio
import hmac
import os

from fastapi import APIRouter, HTTPException, Request

from agent.loop import AgentLoop, LoopConfig

router = APIRouter(prefix="/cron", tags=["operations"])


def _authorize(request: Request) -> None:
    secret = os.getenv("CRON_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="CRON_SECRET is not configured")
    supplied = request.headers.get("authorization", "")
    expected = f"Bearer {secret}"
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="invalid cron authorization")


@router.get("/agent-batch")
async def run_agent_batch(request: Request) -> dict:
    """Run one bounded scanner/agent batch, suitable for Vercel Cron."""
    _authorize(request)
    if os.getenv("RR_CRON_AGENT_ENABLED", "0").lower() not in {"1", "true", "yes"}:
        return {"ok": True, "status": "disabled", "processed": 0}

    config = LoopConfig.from_env()
    config.per_tick = max(1, min(int(os.getenv("RR_CRON_PER_TICK", "1")), 3))
    config.enable_trader = os.getenv("RR_CRON_TRADER", "0").lower() in {"1", "true", "yes"}
    loop = AgentLoop(config=config)
    loop._resolver_every = max(0, int(os.getenv("RR_CRON_RESOLVER_EVERY", "1")))
    timeout_s = max(30, int(os.getenv("RR_CRON_TIMEOUT_S", "240")))
    result = await asyncio.wait_for(loop.run_once(), timeout=timeout_s)
    return {"ok": True, "status": "completed", **result}
