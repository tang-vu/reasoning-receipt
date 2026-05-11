"""Canonical-trace hashing invariants — order-independence, float rounding, idempotence."""

from __future__ import annotations

import hashlib

from storage.irys import canonical_bytes, sha256_hex


def test_key_order_does_not_change_hash() -> None:
    a = {"z": 1, "a": 2, "m": {"y": 3, "b": 4}}
    b = {"a": 2, "z": 1, "m": {"b": 4, "y": 3}}
    assert canonical_bytes(a) == canonical_bytes(b)
    assert sha256_hex(canonical_bytes(a)) == sha256_hex(canonical_bytes(b))


def test_floats_are_rounded_to_6_decimals() -> None:
    a = {"p": 0.1234567}
    b = {"p": 0.1234568}
    # Both round down to 0.123457 — canonicalization makes them equal.
    assert canonical_bytes(a) == canonical_bytes(b)
    # And further-precision noise drops out:
    assert canonical_bytes({"p": 0.123457000001}) == canonical_bytes({"p": 0.123457})


def test_hash_has_0x_prefix_and_64_hex_chars() -> None:
    digest = sha256_hex(b"")
    assert digest.startswith("0x")
    assert len(digest) == 66
    assert hashlib.sha256(b"").hexdigest() == digest[2:]


def test_empty_dict_is_stable() -> None:
    h1 = sha256_hex(canonical_bytes({}))
    h2 = sha256_hex(canonical_bytes({}))
    assert h1 == h2
