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


@router.get("/verify/{receipt_id}/node/{node_id}")
async def verify_node_inclusion(receipt_id: int, node_id: str) -> dict[str, Any]:
    """Return a Merkle inclusion proof for a single node of an rr-trace/3 trace.

    The whole point of the Merkle root commit: anyone can challenge ONE
    evidence URL / counter-argument / sensitivity factor / critic-dim score
    with a ~200-byte proof and the on-chain `verifyInclusion(root, leaf, proof)`
    view on ReceiptRegistryV2 — no full-trace download required.

    Response:
      verified_offchain    — sorted-pair SHA-256 fold matches root (Python-side)
      verified_onchain     — eth_call on ReceiptRegistryV2.verifyInclusion (None if V2 unavailable)
      leaf                 — sha256 of the node's canonical bytes
      proof                — list of sibling hashes, bottom-up
      root                 — merkle root from the trace
      node                 — the node dict that was hashed
    """
    from agent import merkle

    with Session() as session:
        row = session.get(ReceiptRow, receipt_id)
        if row is None:
            raise HTTPException(status_code=404, detail="receipt not found")
        cid = row.trace_cid
        v2_addr = (
            getattr(row, "merkle_root", None) and row.merkle_root
        )  # presence indicates v3 receipt

    if not v2_addr:
        raise HTTPException(
            status_code=400,
            detail="receipt is not rr-trace/3 (no merkle_root recorded)",
        )

    fetched = _fetch_trace_via_cid(cid)
    if fetched is None:
        raise HTTPException(status_code=502, detail="trace fetch via gateway failed")

    node_hashes_dict = fetched.get("node_hashes")
    stored_root = fetched.get("merkle_root") or v2_addr
    if not isinstance(node_hashes_dict, dict) or not node_hashes_dict:
        raise HTTPException(
            status_code=400,
            detail="trace has no node_hashes field — older schema or corrupt JSON",
        )
    if node_id not in node_hashes_dict:
        raise HTTPException(
            status_code=404,
            detail=f"node {node_id!r} not in trace. valid ids: {sorted(node_hashes_dict)}",
        )

    # Reconstruct ordered leaves (sorted lexicographically by id — same as agent/trace_v3.py).
    sorted_ids = sorted(node_hashes_dict)
    idx = sorted_ids.index(node_id)
    leaves = [bytes.fromhex(node_hashes_dict[i][2:]) for i in sorted_ids]
    root_bytes = merkle.merkle_root(leaves)
    computed_root = "0x" + root_bytes.hex()
    proof = merkle.merkle_proof(leaves, idx)
    leaf = leaves[idx]
    verified_offchain = merkle.verify_proof(leaf, proof, root_bytes)

    # Find the original node dict so the caller can SEE what got hashed.
    node_dict = _find_node_in_trace(fetched, node_id)

    # On-chain verifyInclusion (read-only eth_call against ReceiptRegistryV2).
    verified_onchain: bool | None = None
    onchain_error: str | None = None
    try:
        verified_onchain = _eth_call_verify_inclusion(
            root_bytes=root_bytes, leaf_bytes=leaf, proof_bytes=proof
        )
    except Exception as exc:  # noqa: BLE001
        onchain_error = str(exc)[:200]

    return {
        "receipt_id": receipt_id,
        "node_id": node_id,
        "leaf": "0x" + leaf.hex(),
        "proof": ["0x" + p.hex() for p in proof],
        "root_from_trace": stored_root,
        "root_recomputed": computed_root,
        "root_matches": stored_root == computed_root,
        "verified_offchain": verified_offchain,
        "verified_onchain": verified_onchain,
        "onchain_error": onchain_error,
        "node": node_dict,
    }


def _find_node_in_trace(trace: dict, node_id: str) -> dict | Any:
    """Walk the trace dict and return the node sub-dict matching node_id."""
    if node_id == trace.get("claim", {}).get("id"):
        return trace["claim"]
    for s in trace.get("stances", []) or []:
        if isinstance(s, dict) and s.get("id") == node_id:
            return s
        for e in (s.get("evidence", []) if isinstance(s, dict) else []) or []:
            if isinstance(e, dict) and e.get("id") == node_id:
                return e
    for ca in trace.get("counter_arguments", []) or []:
        if isinstance(ca, dict) and ca.get("id") == node_id:
            return ca
    for sn in trace.get("sensitivity", []) or []:
        if isinstance(sn, dict) and sn.get("id") == node_id:
            return sn
    for fc in trace.get("falsifiable_claims", []) or []:
        if isinstance(fc, dict) and fc.get("id") == node_id:
            return fc
    audit = trace.get("critic_audit") or {}
    if node_id.startswith("cd_"):
        dim_key = node_id[len("cd_"):]
        if isinstance(audit.get(dim_key), dict):
            return audit[dim_key]
    return {"_note": f"node {node_id} not found in canonical positions (still hashable)"}


def _eth_call_verify_inclusion(
    *, root_bytes: bytes, leaf_bytes: bytes, proof_bytes: list[bytes]
) -> bool:
    """Eth-call ReceiptRegistryV2.verifyInclusion. Returns the bool result.
    Raises if RPC / contract address are unset."""
    import os

    from web3 import HTTPProvider, Web3

    rpc = os.getenv("RPC")
    addr = os.getenv("RECEIPT_REGISTRY_V2_ADDRESS")
    if not rpc or not addr:
        raise RuntimeError("RPC / RECEIPT_REGISTRY_V2_ADDRESS not configured")
    w3 = Web3(HTTPProvider(rpc, request_kwargs={"timeout": 10}))
    abi = [
        {
            "type": "function",
            "name": "verifyInclusion",
            "stateMutability": "pure",
            "inputs": [
                {"name": "root", "type": "bytes32"},
                {"name": "leaf", "type": "bytes32"},
                {"name": "proof", "type": "bytes32[]"},
            ],
            "outputs": [{"name": "", "type": "bool"}],
        }
    ]
    contract = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=abi)
    return bool(contract.functions.verifyInclusion(root_bytes, leaf_bytes, proof_bytes).call())


# Helper so /price emits a forward-pointer to verify.
def verify_path(receipt_id: int) -> str:
    return f"/verify/{receipt_id}"
