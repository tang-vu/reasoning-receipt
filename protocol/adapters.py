"""Anchor/storage adapter interface — spec §18, §19.

The protocol core never does I/O. Anchoring a commitment (to a chain, a
database, a file, a remote API) is an adapter concern: the adapter receives
the compact commitment (merkle_root + schema_version + receipt_id) and
returns an opaque anchor record. Provider logic stays OUT of
canonicalization and hashing.

Shipped here: FileSystemAnchor (append-only JSONL) and HttpAnchor (POST).
The Arc (`server/chain.py`) and Irys (`storage/irys.py`) integrations are
service-layer adapters in the reference application — see docs/ADAPTERS.md.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class AnchorRecord:
    """What an adapter returns after anchoring a commitment."""

    adapter: str
    merkle_root: str
    schema_version: str
    receipt_id: str
    anchored_at: float
    ok: bool
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter": self.adapter,
            "merkle_root": self.merkle_root,
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "anchored_at": self.anchored_at,
            "ok": self.ok,
            "detail": self.detail,
        }


@runtime_checkable
class AnchorAdapter(Protocol):
    """The only contract: take a compact commitment, return a record."""

    name: str

    def anchor(
        self, *, merkle_root: str, schema_version: str, receipt_id: str
    ) -> AnchorRecord: ...


class FileSystemAnchor:
    """Append-only JSONL anchor — the always-available, offline adapter."""

    name = "filesystem"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def anchor(
        self, *, merkle_root: str, schema_version: str, receipt_id: str
    ) -> AnchorRecord:
        record = AnchorRecord(
            adapter=self.name,
            merkle_root=merkle_root,
            schema_version=schema_version,
            receipt_id=receipt_id,
            anchored_at=time.time(),
            ok=True,
            detail={"path": str(self.path)},
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record.to_dict(), sort_keys=True) + "\n")
        return record


class HttpAnchor:
    """POST the commitment to an HTTP endpoint (hosted API, gateway, …)."""

    name = "http"

    def __init__(self, url: str, *, timeout_s: float = 15.0, headers: dict[str, str] | None = None) -> None:
        self.url = url
        self.timeout_s = timeout_s
        self.headers = headers or {}

    def anchor(
        self, *, merkle_root: str, schema_version: str, receipt_id: str
    ) -> AnchorRecord:
        import httpx

        body = {
            "merkle_root": merkle_root,
            "schema_version": schema_version,
            "receipt_id": receipt_id,
        }
        try:
            resp = httpx.post(
                self.url, json=body, headers=self.headers, timeout=self.timeout_s
            )
            return AnchorRecord(
                adapter=self.name,
                merkle_root=merkle_root,
                schema_version=schema_version,
                receipt_id=receipt_id,
                anchored_at=time.time(),
                ok=resp.status_code < 400,
                detail={"status": resp.status_code, "url": self.url},
            )
        except Exception as exc:  # noqa: BLE001 — adapters report, never raise
            return AnchorRecord(
                adapter=self.name,
                merkle_root=merkle_root,
                schema_version=schema_version,
                receipt_id=receipt_id,
                anchored_at=time.time(),
                ok=False,
                detail={"error": str(exc)[:200], "url": self.url},
            )


class NullAnchor:
    """Explicit no-op — records intent to anchor without doing it."""

    name = "null"

    def anchor(
        self, *, merkle_root: str, schema_version: str, receipt_id: str
    ) -> AnchorRecord:
        return AnchorRecord(
            adapter=self.name,
            merkle_root=merkle_root,
            schema_version=schema_version,
            receipt_id=receipt_id,
            anchored_at=time.time(),
            ok=True,
            detail={"note": "not anchored anywhere"},
        )


def adapter_for(spec: str) -> AnchorAdapter:
    """Resolve `file:PATH`, `http(s):URL`, or `null` into an adapter."""
    if spec == "null":
        return NullAnchor()
    if spec.startswith("file:"):
        return FileSystemAnchor(spec[len("file:") :])
    if spec.startswith("http://") or spec.startswith("https://"):
        return HttpAnchor(spec)
    raise ValueError(f"unknown adapter spec {spec!r} (want file:PATH | https://URL | null)")


# Back-compat env name used by older scripts: RR_ANCHOR
def default_adapter() -> AnchorAdapter:
    spec = os.getenv("RR_ANCHOR", "null")
    return adapter_for(spec)
