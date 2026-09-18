"""`legacy-json-6dp` — the canonicalization used by `rr-trace/*` schemas
and draft-era `reasoning-receipt/1` documents.

Frozen verbatim: 4,500+ historical receipts are anchored under this exact
encoding. It is retained for legacy verification only — new receipts use
`protocol.canon` (RR-Canonical-JSON-1). See spec §14 and docs/LEGACY.md.

Rules (historical, do not change):
- `json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=True)`
- every float first normalized via `float(f"{x:.6f}")` (round to 6 dp,
  then Python repr — including `1e+20`-style exponent forms)
- UTF-8 encoded output
"""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_bytes(trace: dict[str, Any]) -> bytes:
    """Return legacy canonical JSON bytes used for hashing & uploading."""

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
