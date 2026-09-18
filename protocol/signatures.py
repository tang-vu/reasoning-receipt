"""Optional Ed25519 signatures for `reasoning-receipt/1` (spec §8).

Signatures bind a key to a committed value — `receipt` scope signs the
32-byte receipt_hash, `node:<id>` scope signs one node leaf. They live
outside the committed envelope, so signatures compose: an agent signs the
receipt, a human signs an approval node, an auditor countersigns later.

A valid signature proves key possession over the exact commitment — never
identity, authority, or truth.

Backend: `cryptography`'s Ed25519 when installed; otherwise a compact
RFC 8032 reference implementation (pure Python, slower but identical
outputs — cross-checked against RFC test vectors in tests/).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from .errors import E_BAD_SIGNATURE, SignatureError
from .receipt import node_leaf, receipt_hash_of, valid_timestamp

ALG_ED25519 = "ed25519"
SIG_DOMAIN_RECEIPT = b"RR1:sig:receipt\x00"
SIG_DOMAIN_NODE = b"RR1:sig:node\x00"

SIG_FIELDS = {"alg", "scope", "public_key", "sig", "signed_at", "key_id", "meta"}
SIG_REQUIRED = {"alg", "scope", "public_key", "sig"}


# ---------------------------------------------------------------- backend

try:  # pragma: no cover - backend selection is environment-dependent
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )

    _BACKEND = "cryptography"

    def _derive_public(seed: bytes) -> bytes:
        priv = Ed25519PrivateKey.from_private_bytes(seed)
        return priv.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )

    def _sign(seed: bytes, message: bytes) -> bytes:
        return Ed25519PrivateKey.from_private_bytes(seed).sign(message)

    def _verify(public: bytes, message: bytes, signature: bytes) -> bool:
        try:
            Ed25519PublicKey.from_public_bytes(public).verify(signature, message)
            return True
        except (InvalidSignature, ValueError):
            return False

except ImportError:  # pure-Python RFC 8032 fallback
    _BACKEND = "pure-python"
    import hashlib as _hashlib

    _q = 2**255 - 19
    _l = 2**252 + 27742317777372353535851937790883648493
    _d = (-121665 * pow(121666, _q - 2, _q)) % _q
    _I = pow(2, (_q - 1) // 4, _q)

    def _xrecover(y: int) -> int:
        xx = (y * y - 1) * pow(_d * y * y + 1, _q - 2, _q)
        x = pow(xx, (_q + 3) // 8, _q)
        if (x * x - xx) % _q != 0:
            x = (x * _I) % _q
        return x if x % 2 == 0 else _q - x

    _By = 4 * pow(5, _q - 2, _q) % _q
    _Bx = _xrecover(_By)
    _B = (_Bx % _q, _By % _q)

    def _H(m: bytes) -> bytes:
        return _hashlib.sha512(m).digest()

    def _edwards_add(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
        x1, y1 = p
        x2, y2 = q
        denom = pow(1 + _d * x1 * x2 * y1 * y2, _q - 2, _q)
        x3 = (x1 * y2 + x2 * y1) * denom % _q
        denom_y = pow(1 - _d * x1 * x2 * y1 * y2, _q - 2, _q)
        y3 = (y1 * y2 + x1 * x2) * denom_y % _q
        return (x3, y3)

    def _scalarmult(p: tuple[int, int], e: int) -> tuple[int, int]:
        if e == 0:
            return (0, 1)
        q_ = _scalarmult(p, e // 2)
        q_ = _edwards_add(q_, q_)
        if e & 1:
            q_ = _edwards_add(q_, p)
        return q_

    def _encodepoint(p: tuple[int, int]) -> bytes:
        x, y = p
        raw = bytearray(y.to_bytes(32, "little"))
        raw[31] |= (x & 1) << 7
        return bytes(raw)

    def _decodepoint(s: bytes) -> tuple[int, int]:
        y = int.from_bytes(s, "little") & ((1 << 255) - 1)
        x = _xrecover(y)
        if x & 1 != (s[31] >> 7):
            x = _q - x
        p = (x, y)
        # on-curve check
        if (-x * x + y * y - 1 - _d * x * x * y * y) % _q != 0:
            raise ValueError("point not on curve")
        return p

    def _hint(m: bytes) -> int:
        return int.from_bytes(_H(m), "little")

    def _publickey(seed: bytes) -> bytes:
        h = _H(seed)
        a = 2 ** (len(h) * 8 - 2 - 256) + sum(2**i * ((h[i // 8] >> (i % 8)) & 1) for i in range(3, 254))
        return _encodepoint(_scalarmult(_B, a))

    def _derive_public(seed: bytes) -> bytes:
        return _publickey(seed)

    def _sign(seed: bytes, message: bytes) -> bytes:
        h = _H(seed)
        a = 2 ** (len(h) * 8 - 2 - 256) + sum(
            2**i * ((h[i // 8] >> (i % 8)) & 1) for i in range(3, 254)
        )
        r = _hint(h[32:64] + message) % _l
        big_r = _encodepoint(_scalarmult(_B, r))
        s = (r + _hint(big_r + _publickey(seed) + message) * a) % _l
        return big_r + s.to_bytes(32, "little")

    def _verify(public: bytes, message: bytes, signature: bytes) -> bool:
        try:
            if len(signature) != 64 or len(public) != 32:
                return False
            r = _decodepoint(signature[:32])
            a = _decodepoint(public)
            s = int.from_bytes(signature[32:], "little")
            if s >= _l:
                return False
            h = _hint(signature[:32] + public + message) % _l
            return _scalarmult(_B, s) == _edwards_add(r, _scalarmult(a, h))
        except (ValueError, IndexError):
            return False


def signature_backend() -> str:
    """Which Ed25519 backend is active ('cryptography' or 'pure-python')."""
    return _BACKEND


# ------------------------------------------------------------------- API


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_keypair() -> tuple[str, str]:
    """Return (private_key_hex, public_key_hex) — 32-byte Ed25519 seed pair."""
    import os

    seed = os.urandom(32)
    return "0x" + seed.hex(), "0x" + _derive_public(seed).hex()


def _decode_key(hex_value: str, *, length: int, what: str) -> bytes:
    if not isinstance(hex_value, str):
        raise SignatureError(f"{what} is not a string", code=E_BAD_SIGNATURE)
    raw = hex_value[2:] if hex_value.startswith("0x") else hex_value
    try:
        decoded = bytes.fromhex(raw)
    except ValueError as exc:
        raise SignatureError(f"{what} is not hex", code=E_BAD_SIGNATURE) from exc
    if len(decoded) != length:
        raise SignatureError(f"{what} must be {length} bytes", code=E_BAD_SIGNATURE)
    return decoded


def sign_preimage(scope: str, target: bytes, *, node_id: str | None = None) -> bytes:
    """Domain-separated signing preimage (spec §8)."""
    if scope == "receipt":
        return SIG_DOMAIN_RECEIPT + target
    if scope == "node":
        return SIG_DOMAIN_NODE + target
    raise SignatureError(f"unknown signature scope {scope!r}", code=E_BAD_SIGNATURE)


def sign(
    committed_envelope: dict[str, Any],
    private_key_hex: str,
    *,
    scope: str = "receipt",
    key_id: str | None = None,
    signed_at: str | None = None,
    meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Produce a signature object for the committed envelope.

    `scope` is `"receipt"` (signs the receipt_hash) or `"node:<id>"`
    (signs that node's leaf within this envelope).
    """
    seed = _decode_key(private_key_hex, length=32, what="private_key")
    public = _derive_public(seed)

    if scope == "receipt":
        target = bytes.fromhex(receipt_hash_of(committed_envelope)[2:])
        preimage = SIG_DOMAIN_RECEIPT + target
    elif scope.startswith("node:"):
        node_id = scope[len("node:") :]
        leaves = {nd["id"]: node_leaf(nd) for nd in committed_envelope.get("nodes", [])}
        if node_id not in leaves:
            raise SignatureError(f"node {node_id!r} not in envelope", code=E_BAD_SIGNATURE)
        preimage = SIG_DOMAIN_NODE + leaves[node_id]
    else:
        raise SignatureError(f"unknown signature scope {scope!r}", code=E_BAD_SIGNATURE)

    if signed_at is None:
        signed_at = _utcnow_iso()
    elif not valid_timestamp(signed_at):
        raise SignatureError(f"invalid signed_at {signed_at!r}", code=E_BAD_SIGNATURE)

    sig: dict[str, Any] = {
        "alg": ALG_ED25519,
        "scope": scope,
        "public_key": "0x" + public.hex(),
        "sig": "0x" + _sign(seed, preimage).hex(),
        "signed_at": signed_at,
    }
    if key_id is not None:
        sig["key_id"] = key_id
    if meta is not None:
        sig["meta"] = meta
    return sig


def verify_signatures(
    committed_envelope: dict[str, Any], signatures: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Check every signature object; one result per signature, order kept.

    Never raises on a merely-invalid signature — returns
    {"valid": False, "reason": ...} so one bad signature cannot mask the
    state of the others.
    """
    results: list[dict[str, Any]] = []
    for index, sig in enumerate(signatures):
        result: dict[str, Any] = {"index": index, "valid": False}
        try:
            if not isinstance(sig, dict):
                raise SignatureError("signature is not an object")
            missing = SIG_REQUIRED - set(sig)
            if missing:
                raise SignatureError(f"signature missing {sorted(missing)}")
            extra = set(sig) - SIG_FIELDS
            if extra:
                raise SignatureError(f"signature has unknown fields {sorted(extra)}")
            result["scope"] = sig["scope"]
            result["public_key"] = sig["public_key"]
            if sig["alg"] != ALG_ED25519:
                raise SignatureError(f"unsupported alg {sig['alg']!r}")
            if "signed_at" in sig and not valid_timestamp(sig["signed_at"]):
                raise SignatureError("invalid signed_at")

            public = _decode_key(sig["public_key"], length=32, what="public_key")
            signature = _decode_key(sig["sig"], length=64, what="sig")

            if sig["scope"] == "receipt":
                preimage = SIG_DOMAIN_RECEIPT + bytes.fromhex(
                    receipt_hash_of(committed_envelope)[2:]
                )
            elif sig["scope"].startswith("node:"):
                node_id = sig["scope"][len("node:") :]
                leaves = {
                    nd["id"]: node_leaf(nd) for nd in committed_envelope.get("nodes", [])
                }
                if node_id not in leaves:
                    raise SignatureError(f"node {node_id!r} not in envelope")
                preimage = SIG_DOMAIN_NODE + leaves[node_id]
            else:
                raise SignatureError(f"unknown scope {sig['scope']!r}")

            result["valid"] = _verify(public, preimage, signature)
            if not result["valid"]:
                result["reason"] = "signature verification failed"
        except SignatureError as exc:
            result["reason"] = str(exc)
        results.append(result)
    return results
