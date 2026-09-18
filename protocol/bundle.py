"""`.rrbundle` — portable receipt bundle format (spec §15, §17).

A bundle is a **single JSON object** carrying a receipt plus optional
attachments, proofs, and signature metadata. No archive formats — there is
no path traversal, no symlinks, no zip bombs: paths are validated and
contents are base64 in a manifest-hashed container.

```json
{
  "bundle_version": "rr-bundle/1",
  "manifest": { "receipt.json": {"sha256": "<hex>", "bytes": 1234} },
  "files": { "receipt.json": "<base64>" }
}
```

A receipt is always valid without a bundle; bundles are transport, not
commitment.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any

from .canon import canonical_bytes
from .errors import E_BAD_TYPE, E_LIMIT, E_MISSING_FIELD, ReceiptError, ShapeError

BUNDLE_VERSION = "rr-bundle/1"

MAX_FILES = 256
MAX_TOTAL_BYTES = 32 << 20  # 32 MiB decoded
MAX_PATH = 512
_PATH_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-/]*$")


def validate_bundle_path(path: str) -> None:
    """Reject traversal, absolute paths, and anything surprising."""
    if not isinstance(path, str) or not path:
        raise ShapeError("bundle path is not a string", code=E_BAD_TYPE)
    if len(path) > MAX_PATH:
        raise ShapeError("bundle path too long", code=E_LIMIT)
    if not _PATH_RE.match(path):
        raise ShapeError(f"bundle path {path!r} has invalid characters")
    if path.startswith("/") or "\\" in path or ":" in path:
        raise ShapeError(f"bundle path {path!r} must be relative POSIX")
    segments = path.split("/")
    if any(seg in ("", ".", "..") for seg in segments):
        raise ShapeError(f"bundle path {path!r} contains traversal segments")


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=True)
    except (ValueError, TypeError) as exc:
        raise ShapeError("bundle file is not valid base64") from exc


def build_bundle(
    files: dict[str, bytes | str],
    *,
    extra_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a bundle from {path: bytes|str}. Deterministic manifest."""
    if not files:
        raise ShapeError("bundle needs at least one file", code=E_MISSING_FIELD)
    if len(files) > MAX_FILES:
        raise ShapeError(f"bundle exceeds {MAX_FILES} files", code=E_LIMIT)
    manifest: dict[str, Any] = {}
    encoded: dict[str, str] = {}
    total = 0
    for path in sorted(files):
        validate_bundle_path(path)
        data = files[path]
        blob = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        total += len(blob)
        if total > MAX_TOTAL_BYTES:
            raise ShapeError(f"bundle exceeds {MAX_TOTAL_BYTES} decoded bytes", code=E_LIMIT)
        manifest[path] = {"sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)}
        encoded[path] = _b64(blob)
    if extra_manifest:
        manifest["_extra"] = extra_manifest
    return {
        "bundle_version": BUNDLE_VERSION,
        "manifest": manifest,
        "files": encoded,
    }


def receipt_bundle(
    receipt: dict[str, Any],
    *,
    proofs: dict[str, dict[str, Any]] | None = None,
    attachments: dict[str, bytes | str] | None = None,
) -> dict[str, Any]:
    """Bundle a receipt + per-name proof documents + raw attachments."""
    files: dict[str, bytes | str] = {"receipt.json": json.dumps(receipt, ensure_ascii=False)}
    for name, proof in (proofs or {}).items():
        files[f"proofs/{name}.json"] = json.dumps(proof, ensure_ascii=False)
    for name, blob in (attachments or {}).items():
        files[f"attachments/{name}"] = blob
    return build_bundle(files)


@dataclass(slots=True)
class BundleReport:
    valid: bool
    errors: list[str]
    file_count: int = 0
    total_bytes: int = 0
    checked: dict[str, bool] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return self.valid


def extract_bundle(bundle: dict[str, Any]) -> dict[str, bytes]:
    """Validate + decode a bundle into {path: bytes}. Raises on any violation."""
    if not isinstance(bundle, dict):
        raise ShapeError("bundle is not an object", code=E_BAD_TYPE)
    if bundle.get("bundle_version") != BUNDLE_VERSION:
        raise ShapeError(
            f"unsupported bundle_version {bundle.get('bundle_version')!r}"
        )
    manifest = bundle.get("manifest")
    files = bundle.get("files")
    if not isinstance(manifest, dict) or not isinstance(files, dict):
        raise ShapeError("bundle missing manifest/files", code=E_MISSING_FIELD)

    out: dict[str, bytes] = {}
    total = 0
    for path in sorted(files):
        validate_bundle_path(path)
        if len(out) >= MAX_FILES:
            raise ShapeError(f"bundle exceeds {MAX_FILES} files", code=E_LIMIT)
        blob = _unb64(files[path])
        total += len(blob)
        if total > MAX_TOTAL_BYTES:
            raise ShapeError(f"bundle exceeds {MAX_TOTAL_BYTES} decoded bytes", code=E_LIMIT)
        entry = manifest.get(path)
        if not isinstance(entry, dict):
            raise ShapeError(f"no manifest entry for {path!r}", code=E_MISSING_FIELD)
        if entry.get("bytes") != len(blob) or entry.get("sha256") != hashlib.sha256(blob).hexdigest():
            raise ShapeError(f"manifest mismatch for {path!r}")
        out[path] = blob
    return out


def verify_bundle(bundle: dict[str, Any]) -> BundleReport:
    """Validate a bundle without extracting: manifest hashes all match."""
    errors: list[str] = []
    checked: dict[str, bool] = {}
    try:
        files = extract_bundle(bundle)
    except ReceiptError as exc:
        return BundleReport(valid=False, errors=[f"{exc.code}: {exc}"])
    total = 0
    for path, blob in files.items():
        entry = bundle["manifest"][path]
        checked[path] = (
            entry.get("sha256") == hashlib.sha256(blob).hexdigest()
            and entry.get("bytes") == len(blob)
        )
        if not checked[path]:
            errors.append(f"manifest_mismatch: {path}")
        total += len(blob)
    return BundleReport(
        valid=all(checked.values()),
        errors=errors,
        file_count=len(files),
        total_bytes=total,
        checked=checked,
    )


def bundle_canonical_bytes(bundle: dict[str, Any]) -> bytes:
    """Canonical form of a bundle (for hashing a bundle as a unit)."""
    return canonical_bytes(bundle)
