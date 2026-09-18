"""RR-Canonical-JSON-1 — authoritative canonical encoding for `reasoning-receipt/1`.

Normative definition: `spec/REASONING-RECEIPT-1.md` §7. Every conforming
implementation MUST produce byte-identical output for in-domain input and
MUST reject out-of-domain input with an error — never coerce.

Quick contract:
- UTF-8, no BOM, zero whitespace.
- Object keys sorted by UTF-8 byte sequence; duplicate keys rejected.
- Strings: minimal escaping (" \\ \\b \\f \\n \\r \\t, other C0 → \\u00XX);
  all else literal UTF-8. No Unicode normalization. Lone surrogates rejected.
- Numbers by value: |v| < 2^53, finite only; integral → decimal digits;
  non-integral → fixed 6 fraction digits; no negative zero.
"""

from __future__ import annotations

import math
from typing import Any

from .errors import E_LIMIT, E_NONCANONICAL, CanonError

PORTABLE_INT_MAX = 2**53 - 1
PORTABLE_INT_MIN = -PORTABLE_INT_MAX
PORTABLE_ABS_BOUND = float(2**53)

MAX_DEPTH = 64
MAX_KEY_LENGTH = 256
MAX_STRING_LENGTH = 1 << 20  # 1 MiB

_ESCAPES = {
    0x22: '\\"',
    0x5C: "\\\\",
    0x08: "\\b",
    0x0C: "\\f",
    0x0A: "\\n",
    0x0D: "\\r",
    0x09: "\\t",
}


def _check_string(value: str, *, what: str) -> None:
    if len(value) > MAX_STRING_LENGTH:
        raise CanonError(f"{what} exceeds {MAX_STRING_LENGTH} chars", code=E_LIMIT)
    for ch in value:
        if 0xD800 <= ord(ch) <= 0xDFFF:
            raise CanonError(
                f"{what} contains an unpaired surrogate (U+{ord(ch):04X})",
                code=E_NONCANONICAL,
            )


def _encode_string(value: str, out: list[str]) -> None:
    _check_string(value, what="string")
    out.append('"')
    for ch in value:
        code = ord(ch)
        esc = _ESCAPES.get(code)
        if esc is not None:
            out.append(esc)
        elif code < 0x20:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')


def _encode_number(value: int | float, out: list[str]) -> None:
    if isinstance(value, int):
        if value < PORTABLE_INT_MIN or value > PORTABLE_INT_MAX:
            raise CanonError(
                f"integer {value} outside portable range ±(2^53-1)",
                code=E_NONCANONICAL,
            )
        out.append(str(value))
        return
    if math.isnan(value) or math.isinf(value):
        raise CanonError("non-finite number is not canonicalizable", code=E_NONCANONICAL)
    if abs(value) >= PORTABLE_ABS_BOUND:
        raise CanonError(
            f"number {value} outside portable range 2^53",
            code=E_NONCANONICAL,
        )
    if value == math.trunc(value):
        out.append(str(int(value)))
        return
    fixed = f"{value:.6f}"
    if fixed.startswith("-") and float(fixed) == 0.0:
        fixed = fixed[1:]
    out.append(fixed)


def _encode(value: Any, out: list[str], depth: int) -> None:
    if depth > MAX_DEPTH:
        raise CanonError(f"nesting exceeds {MAX_DEPTH}", code=E_LIMIT)
    if value is None:
        out.append("null")
    elif isinstance(value, bool):
        out.append("true" if value else "false")
    elif isinstance(value, (int, float)):
        _encode_number(value, out)
    elif isinstance(value, str):
        _encode_string(value, out)
    elif isinstance(value, list):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _encode(item, out, depth + 1)
        out.append("]")
    elif isinstance(value, dict):
        pairs: list[tuple[bytes, str, Any]] = []
        seen: set[bytes] = set()
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonError("object key is not a string", code=E_NONCANONICAL)
            if len(key) > MAX_KEY_LENGTH:
                raise CanonError(f"object key exceeds {MAX_KEY_LENGTH} chars", code=E_LIMIT)
            _check_string(key, what="object key")
            encoded = key.encode("utf-8")
            if encoded in seen:
                raise CanonError(f"duplicate object key {key!r}", code=E_NONCANONICAL)
            seen.add(encoded)
            pairs.append((encoded, key, item))
        pairs.sort(key=lambda p: p[0])
        out.append("{")
        for i, (_, key, item) in enumerate(pairs):
            if i:
                out.append(",")
            _encode_string(key, out)
            out.append(":")
            _encode(item, out, depth + 1)
        out.append("}")
    else:
        raise CanonError(
            f"unsupported type {type(value).__name__} is not canonicalizable",
            code=E_NONCANONICAL,
        )


def canonical_bytes(value: Any) -> bytes:
    """Encode `value` as RR-Canonical-JSON-1 bytes, or raise CanonError."""
    out: list[str] = []
    _encode(value, out, 0)
    return "".join(out).encode("utf-8")


def canonical_str(value: Any) -> str:
    """Same encoding as str (canonical_bytes decoded — always valid UTF-8)."""
    return canonical_bytes(value).decode("utf-8")


def parse_json_object(text: str | bytes) -> dict[str, Any]:
    """Parse JSON text strictly for envelope ingest.

    Rejects duplicate keys and non-dict roots — both are noncanonical input
    for a receipt document. Integers parse as `int`, reals as `float`.
    """
    import json

    def _no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        seen: set[str] = set()
        out: dict[str, Any] = {}
        for key, item in pairs:
            if key in seen:
                raise CanonError(f"duplicate object key {key!r}", code=E_NONCANONICAL)
            seen.add(key)
            out[key] = item
        return out

    try:
        if isinstance(text, bytes):
            text = text.decode("utf-8")
        parsed = json.loads(text, object_pairs_hook=_no_dupes, parse_constant=_reject_constant)
    except CanonError:
        raise
    except (ValueError, UnicodeDecodeError) as exc:
        raise CanonError(f"invalid JSON: {exc}", code=E_NONCANONICAL) from exc
    if not isinstance(parsed, dict):
        raise CanonError("receipt document is not a JSON object", code=E_NONCANONICAL)
    return parsed


def _reject_constant(token: str) -> Any:
    raise CanonError(f"non-JSON constant {token!r}", code=E_NONCANONICAL)
