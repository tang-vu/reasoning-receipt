"""Mock x402 facilitator — local-dev settlement endpoint.

Mounts at /facilitator/settle when `RR_LOCAL_FACILITATOR=1`. Treats every
payment payload as valid and returns a deterministic tx hash. Useful for
end-to-end demos that don't need a real Arc settlement loop.

Set `X402_FACILITATOR_URL=http://localhost:8000/facilitator` to point the
server at itself.
"""

from __future__ import annotations

import hashlib
import time

from fastapi import APIRouter

router = APIRouter(prefix="/facilitator", tags=["facilitator"])


@router.post("/settle")
async def settle(payload: dict) -> dict:
    inner = payload.get("payload", {})
    payer = inner.get("payer", "0x" + "0" * 40)
    nonce = inner.get("nonce", "")
    digest = hashlib.sha256(f"{payer}|{nonce}|{time.time_ns()}".encode()).hexdigest()
    return {
        "scheme": "exact",
        "network": payload.get("network", "arc-testnet"),
        "payer": payer,
        "tx_hash": "0x" + digest,
        "amount": inner.get("amount", "0"),
        "asset": "USDC",
    }


@router.get("/supported")
async def supported() -> dict:
    return {
        "schemes": ["exact"],
        "networks": ["arc-testnet"],
        "assets": ["USDC"],
        "max_amount_usdc": 1.0,
    }
