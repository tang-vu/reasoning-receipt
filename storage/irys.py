"""Irys uploader for reasoning traces.

Real mode: shells out to the Node sidecar at `services/irys/upload.js`, which
uses the official `@irys/upload` + `@irys/upload-ethereum` SDK to sign and
upload a Bundlr-format data item with `IRYS_PRIVATE_KEY`. Returns the
Arweave-style CID (`ar://<txid>`).

The Bundlr signed-bundle format is non-trivial to reproduce in Python; rather
than re-implement the spec we keep a tiny Node sidecar (single dependency,
~200 ms cold start) and pass the canonical trace JSON over stdin.

Mock mode (no `IRYS_PRIVATE_KEY` or `RR_MOCK_IRYS=1`): returns a deterministic
synthetic CID derived from the trace hash so tests + offline dev still pass.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Resolve once: services/irys lives at the repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
_IRYS_SIDECAR_DIR = _REPO_ROOT / "services" / "irys"
_IRYS_SIDECAR_SCRIPT = _IRYS_SIDECAR_DIR / "upload.js"


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
    """Uploads canonical trace JSON to Irys via the Node sidecar."""

    def __init__(
        self,
        *,
        private_key: str | None = None,
        network: str | None = None,
        token: str = "ethereum",
        mock: bool | None = None,
        sidecar_script: Path | None = None,
        sidecar_timeout_s: float = 30.0,
    ) -> None:
        self.private_key = private_key or os.getenv("IRYS_PRIVATE_KEY")
        self.network = network or os.getenv("IRYS_NETWORK", "devnet")
        self.token = token or os.getenv("IRYS_TOKEN", "ethereum")
        self.sidecar_script = sidecar_script or _IRYS_SIDECAR_SCRIPT
        self.sidecar_timeout_s = sidecar_timeout_s

        env_mock = os.getenv("RR_MOCK_IRYS", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        if not self.private_key:
            self.mock = True
        if not self.mock and not self.sidecar_script.exists():
            logger.warning(
                "irys: sidecar script not found at %s — falling back to mock",
                self.sidecar_script,
            )
            self.mock = True

    def upload(self, trace: dict[str, Any]) -> TraceUpload:
        """Canonicalize → hash → upload (or mock). Idempotent on identical traces."""
        blob = canonical_bytes(trace)
        h = sha256_hex(blob)
        if self.mock:
            cid = "ar://" + h[2:34]
            return TraceUpload(hash_hex=h, cid=cid, size_bytes=len(blob), is_mock=True)

        env = {**os.environ, "IRYS_PRIVATE_KEY": self.private_key or "", "IRYS_NETWORK": self.network}
        try:
            proc = subprocess.run(
                ["node", str(self.sidecar_script)],
                input=blob,
                capture_output=True,
                env=env,
                timeout=self.sidecar_timeout_s,
                check=True,
            )
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"irys sidecar exit={exc.returncode}: {exc.stderr.decode(errors='replace')[:300]}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"irys sidecar timeout after {self.sidecar_timeout_s}s") from exc

        last = proc.stdout.decode("utf-8", errors="replace").strip().splitlines()[-1] if proc.stdout else ""
        try:
            data = json.loads(last)
        except ValueError as exc:
            raise RuntimeError(f"irys sidecar returned non-JSON: {last[:200]}") from exc
        cid = data.get("cid") or (f"ar://{data['id']}" if "id" in data else "")
        if not cid:
            raise RuntimeError(f"irys sidecar returned no id: {data}")
        return TraceUpload(hash_hex=h, cid=cid, size_bytes=len(blob), is_mock=False)
