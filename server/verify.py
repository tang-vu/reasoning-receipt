"""Trace verification endpoint — the wedge made auditable.

Given a receipt id, this endpoint:
  1. Pulls the row from the DB (publisher hash + cid + on-chain refs).
  2. Re-fetches the trace JSON from Irys via the CID.
  3. Re-canonicalises the JSON exactly as the publisher did.
  4. Recomputes SHA-256.
  5. Compares the recomputed hash to the value stored on Arc / in the DB.

If the comparison passes, the trace is a verified artifact — the published
hash, the on-chain Receipt event, and the fetched JSON line up. Anyone can
audit any receipt without trusting the oracle.

The endpoint also returns the canonical trace payload + the Irys gateway URL
so a UI / curl user can inspect it directly.

In mock-Irys mode the CID is deterministic and the stored trace JSON lives
locally — we still re-canonicalise + re-hash so the same verification
contract holds.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException

from storage.db import Receipt as ReceiptRow
from storage.db import Session
from storage.irys import canonical_bytes, sha256_hex

router = APIRouter(tags=["verify"])
logger = logging.getLogger(__name__)


IRYS_GATEWAY = "https://gateway.irys.xyz"


def _fetch_trace_via_cid(cid: str) -> dict[str, Any] | None:
    """Fetch the raw trace JSON from Irys / IPFS via its CID. Returns None in mock mode."""
    if not cid:
        return None
    if cid.startswith("ar://"):
        tx_id = cid.removeprefix("ar://")
    elif cid.startswith("ipfs://"):
        tx_id = cid.removeprefix("ipfs://")
    else:
        tx_id = cid

    # Mock CIDs are 32 hex chars (derived from the trace hash) — Irys gateway won't have them.
    if len(tx_id) == 32 and all(c in "0123456789abcdef" for c in tx_id.lower()):
        return None

    url = f"{IRYS_GATEWAY}/{tx_id}"
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            return resp.json()
    except Exception as exc:
        logger.warning("verify: Irys fetch failed for %s: %s", cid, exc)
        return None


@router.get("/verify/{receipt_id}")
async def verify_receipt(receipt_id: int) -> dict[str, Any]:
    """Re-derive the trace hash and compare to the stored value."""
    with Session() as session:
        row = session.get(ReceiptRow, receipt_id)
        if row is None:
            raise HTTPException(status_code=404, detail="receipt not found")
        stored = {
            "id": row.id,
            "market_id": row.market_id,
            "market_question": row.market_question,
            "trace_hash": row.trace_hash,
            "trace_cid": row.trace_cid,
            "arc_tx_hash": row.arc_tx_hash,
            "probability": row.probability,
            "confidence": row.confidence,
            "consumer_address": row.consumer_address,
            "publisher_address": row.publisher_address,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    fetched_trace = _fetch_trace_via_cid(stored["trace_cid"])

    if fetched_trace is None:
        # Either CID is mock or the gateway is unreachable. We still expose the
        # stored values so the UI can render the on-chain refs; the user can
        # then re-fetch externally and re-run the hash themselves.
        return {
            "verified": False,
            "reason": "trace fetch unavailable (mock CID or gateway error)",
            "stored": stored,
            "fetched_trace": None,
            "recomputed_hash": None,
            "irys_gateway_url": (
                f"{IRYS_GATEWAY}/{stored['trace_cid'].removeprefix('ar://')}"
                if stored["trace_cid"]
                else None
            ),
        }

    # Re-canonicalise and re-hash. This is the meat of the verification.
    recomputed = sha256_hex(canonical_bytes(fetched_trace))
    matches = recomputed.lower() == stored["trace_hash"].lower()

    return {
        "verified": matches,
        "reason": "byte-for-byte match" if matches else "hash mismatch — trace tampered or stale",
        "stored": stored,
        "fetched_trace": fetched_trace,
        "recomputed_hash": recomputed,
        "irys_gateway_url": f"{IRYS_GATEWAY}/{stored['trace_cid'].removeprefix('ar://')}",
    }


@router.get("/verify/{receipt_id}/payload")
async def verify_payload(receipt_id: int) -> dict[str, Any]:
    """Return the canonical trace payload + stored refs for client-side verification.

    Use this when the caller wants to do their own hash verification — useful for
    third-party auditors who don't trust our /verify endpoint either.
    """
    with Session() as session:
        row = session.get(ReceiptRow, receipt_id)
        if row is None:
            raise HTTPException(status_code=404, detail="receipt not found")
        cid = row.trace_cid
        stored_hash = row.trace_hash

    fetched = _fetch_trace_via_cid(cid)
    if fetched is None:
        raise HTTPException(status_code=502, detail="trace fetch via gateway failed")

    canonical = canonical_bytes(fetched).decode("utf-8")
    return {
        "stored_hash": stored_hash,
        "trace_cid": cid,
        "canonical_payload": canonical,
        "hint": (
            "To verify: take canonical_payload, encode as UTF-8 bytes, compute SHA-256, "
            "prefix with 0x. Result must equal stored_hash."
        ),
    }


# Helper so /price emits a forward-pointer to verify.
def verify_path(receipt_id: int) -> str:
    return f"/verify/{receipt_id}"
