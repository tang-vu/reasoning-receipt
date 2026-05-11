"""Irys uploader for reasoning traces.

Real mode: signs an Irys transaction with `IRYS_PRIVATE_KEY`, POSTs the trace
blob to the Irys node, returns the Irys/Arweave-style CID (`ar://<txid>`).

Mock mode (no `IRYS_PRIVATE_KEY` or `RR_MOCK_IRYS=1`): returns a deterministic
synthetic CID derived from the trace hash. Lets local dev + tests succeed
without a node.

The contract is: same input → same SHA-256 → same CID. We never re-upload an
identical trace. This means demo replays are stable and the dashboard can
de-duplicate.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class TraceUpload:
    """Result of uploading a canonical trace blob."""

    hash_hex: str
    cid: str
    size_bytes: int
    is_mock: bool


def canonical_bytes(trace: dict[str, Any]) -> bytes:
    """Return canonical JSON bytes used for hashing & uploading.

    Rules:
    - Sorted keys
    - UTF-8 encoded
    - Separators '(",", ":")' (no extra whitespace)
    - Floats stringified to 6 decimal places before serialization, so any
      cross-language verifier reproduces the same bytes.
    """

    def _norm(obj: Any) -> Any:
        if isinstance(obj, float):
            return float(f"{obj:.6f}")
        if isinstance(obj, dict):
            return {k: _norm(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_norm(v) for v in obj]
        return obj

    return json.dumps(_norm(trace), sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(blob: bytes) -> str:
    """Hex-prefixed SHA-256, suitable for use as the on-chain bytes32 traceHash."""
    return "0x" + hashlib.sha256(blob).hexdigest()


class IrysClient:
    """Thin wrapper around the Irys upload endpoint."""

    def __init__(
        self,
        *,
        node_url: str | None = None,
        private_key: str | None = None,
        token: str = "ethereum",
        mock: bool | None = None,
    ) -> None:
        self.node_url = node_url or os.getenv("IRYS_NODE_URL", "https://node1.irys.xyz")
        self.private_key = private_key or os.getenv("IRYS_PRIVATE_KEY")
        self.token = token or os.getenv("IRYS_TOKEN", "ethereum")
        env_mock = os.getenv("RR_MOCK_IRYS", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        if not self.private_key:
            self.mock = True

    def upload(self, trace: dict[str, Any]) -> TraceUpload:
        """Canonicalize → hash → upload (or mock). Idempotent on identical traces."""
        blob = canonical_bytes(trace)
        h = sha256_hex(blob)
        if self.mock:
            cid = "ar://" + h[2:34]
            return TraceUpload(hash_hex=h, cid=cid, size_bytes=len(blob), is_mock=True)

        headers = {"Content-Type": "application/json", "X-Trace-Hash": h}
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(f"{self.node_url}/tx/{self.token}", content=blob, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        tx_id = data.get("id") or data.get("txId") or data.get("transactionId")
        if not tx_id:
            raise RuntimeError(f"Irys returned no tx id: {data}")
        return TraceUpload(hash_hex=h, cid=f"ar://{tx_id}", size_bytes=len(blob), is_mock=False)
