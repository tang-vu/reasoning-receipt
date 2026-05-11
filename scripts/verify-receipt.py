"""verify-receipt.py — command-line proof that a receipt is honest.

Demo-friendly: in one terminal frame, prove the wedge.

  $ uv run python -m scripts.verify-receipt 42 --base-url http://localhost:8000

Pulls the trace from Irys, re-canonicalises, re-hashes, compares to the
on-chain hash. Exit code 0 iff the receipt verifies byte-for-byte.

Works against either:
  - A live FastAPI server (uses its /verify endpoint)
  - The raw Irys gateway + an on-chain hash (no server needed)
"""

from __future__ import annotations

import argparse
import json
import sys

import httpx

from storage.irys import canonical_bytes, sha256_hex

DEFAULT_GATEWAY = "https://gateway.irys.xyz"


def verify_via_server(base_url: str, receipt_id: int) -> int:
    url = f"{base_url.rstrip('/')}/verify/{receipt_id}"
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(url)
    if resp.status_code != 200:
        print(f"❌ HTTP {resp.status_code}: {resp.text}", file=sys.stderr)
        return 2
    body = resp.json()
    _print_report(body)
    return 0 if body.get("verified") else 1


def verify_offline(cid: str, expected_hash: str, gateway: str = DEFAULT_GATEWAY) -> int:
    """Verify without trusting our server: pull trace from Irys, re-hash, compare."""
    tx_id = cid.removeprefix("ar://").removeprefix("ipfs://")
    url = f"{gateway.rstrip('/')}/{tx_id}"
    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        resp = client.get(url)
    if resp.status_code != 200:
        print(f"❌ Irys gateway returned {resp.status_code}", file=sys.stderr)
        return 2

    trace = resp.json()
    recomputed = sha256_hex(canonical_bytes(trace))
    ok = recomputed.lower() == expected_hash.lower()
    print(f"trace cid         : {cid}")
    print(f"expected hash     : {expected_hash}")
    print(f"recomputed hash   : {recomputed}")
    print(f"trace bytes (B)   : {len(canonical_bytes(trace))}")
    print(f"verdict           : {'VERIFIED ✓' if ok else 'TAMPERED / STALE ✗'}")
    return 0 if ok else 1


def _print_report(body: dict) -> None:
    stored = body.get("stored") or {}
    print(f"receipt id        : {stored.get('id')}")
    print(f"market            : {stored.get('market_question') or stored.get('market_id')}")
    print(f"probability       : {stored.get('probability'):.4f}" if stored.get("probability") is not None else "probability       : —")
    print(f"confidence        : {stored.get('confidence'):.4f}" if stored.get("confidence") is not None else "confidence        : —")
    print(f"trace hash        : {stored.get('trace_hash')}")
    print(f"trace cid         : {stored.get('trace_cid')}")
    print(f"arc tx            : {stored.get('arc_tx_hash')}")
    if body.get("recomputed_hash"):
        print(f"recomputed hash   : {body['recomputed_hash']}")
    print(f"verdict           : {'VERIFIED ✓' if body.get('verified') else 'UNVERIFIED ✗'}")
    print(f"reason            : {body.get('reason')}")
    if body.get("irys_gateway_url"):
        print(f"irys gateway      : {body['irys_gateway_url']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Re-derive a receipt's trace hash and prove it on-chain.")
    parser.add_argument("receipt_id", nargs="?", type=int, help="Receipt id (when verifying via server)")
    parser.add_argument("--base-url", default="http://localhost:8000", help="FastAPI server base URL")
    parser.add_argument("--cid", help="(offline mode) Trace CID to fetch from Irys gateway")
    parser.add_argument("--expected-hash", help="(offline mode) Hash that should match the recomputed value")
    parser.add_argument("--gateway", default=DEFAULT_GATEWAY)
    parser.add_argument("--json", action="store_true", help="Emit verify JSON instead of human report")
    args = parser.parse_args(argv)

    if args.cid and args.expected_hash:
        return verify_offline(args.cid, args.expected_hash, args.gateway)

    if args.receipt_id is None:
        parser.error("provide either RECEIPT_ID (server mode) or --cid + --expected-hash (offline mode)")

    if args.json:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(f"{args.base_url.rstrip('/')}/verify/{args.receipt_id}")
        print(json.dumps(resp.json(), indent=2))
        return 0 if resp.json().get("verified") else 1

    return verify_via_server(args.base_url, args.receipt_id)


if __name__ == "__main__":
    sys.exit(main())
