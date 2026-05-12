"""Demo runner — fresh consumer wallet, 5 oracle queries, receipts printed.

Used both for the recorded demo (Phase 4) and as a smoke-test of the full
pipeline. Hits the FastAPI server over HTTP, exercises the 402 → pay → receipt
flow, and prints a markdown-ready receipt table.

Usage:
    uv run python -m scripts.demo-runner --base-url http://localhost:8000
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from dataclasses import dataclass

import httpx

DEFAULT_MARKETS = [
    "mock-polymarket-fed-rate-cut-jun-2026",
    "mock-polymarket-arsenal-pl-title-2026",
    "mock-polymarket-btc-100k-by-jun-2026",
    "mock-polymarket-cpi-may-2026",
    "mock-polymarket-eu-ai-act-amendment",
]


@dataclass(slots=True)
class DemoResult:
    market_id: str
    receipt_id: int
    probability: float
    confidence: float
    trace_hash: str
    trace_cid: str
    arc_tx_hash: str
    paid_usdc: float
    latency_ms: int


def _build_payment_header(challenge_body: dict, payer: str, resource: str) -> tuple[str, str]:
    """Compose an X-PAYMENT payload that satisfies the server's verifier.

    The on-the-wire shape mirrors Circle's x402-v2 settle envelope:
        { scheme, network, payload: { from, to, value, validAfter, validBefore, nonce, signature } }

    In mock mode the signature is synthetic; the server accepts any signature
    when RR_MOCK_X402=1. When wired to the real Circle facilitator, replace
    `signature` with an EIP-3009 TransferWithAuthorization signature.
    """
    accept = challenge_body["accepts"][0]
    extra = accept.get("extra", {})
    resource_url = resource
    inner = {
        "from": payer,
        "to": accept.get("payTo", accept.get("recipient", "")),
        "value": str(accept["amount"]),
        "validAfter": "0",
        "validBefore": str(int(__import__("time").time()) + accept.get("maxTimeoutSeconds", 604900)),
        "nonce": accept["nonce"],
        "signature": "0x" + "ab" * 32,
    }
    payment = {
        "scheme": "exact",
        "network": accept["network"],
        "asset": accept["asset"],
        "amount": str(accept["amount"]),
        "nonce": accept["nonce"],
        "resource": resource_url,
        "payer": payer,
        "payload": inner,
        "extra": extra,
    }
    return base64.b64encode(json.dumps(payment).encode("utf-8")).decode("ascii"), accept["nonce"]


def query_oracle(client: httpx.Client, base_url: str, market_id: str, payer: str) -> DemoResult:
    start = time.perf_counter()

    r1 = client.get(f"{base_url}/price/{market_id}")
    if r1.status_code != 402:
        raise SystemExit(f"expected 402, got {r1.status_code}: {r1.text}")

    body = r1.json()
    payment_header, _ = _build_payment_header(body, payer, resource=f"/price/{market_id}")
    challenge_token = r1.headers["x-payment-challenge"]

    r2 = client.get(
        f"{base_url}/price/{market_id}",
        headers={"X-Payment": payment_header, "X-Payment-Challenge": challenge_token},
    )
    if r2.status_code != 200:
        raise SystemExit(f"paid request failed: {r2.status_code} {r2.text}")
    data = r2.json()
    latency_ms = int((time.perf_counter() - start) * 1000)

    return DemoResult(
        market_id=market_id,
        receipt_id=int(data["receipt_id"]),
        probability=float(data["probability"]),
        confidence=float(data["confidence"]),
        trace_hash=str(data["trace_hash"]),
        trace_cid=str(data["trace_cid"]),
        arc_tx_hash=str(data["arc_tx_hash"]),
        paid_usdc=float(data["paid_usdc"]),
        latency_ms=latency_ms,
    )


def print_results(results: list[DemoResult]) -> None:
    print("\n| # | Market | Prob | Conf | Paid | Latency | Arc tx |")
    print("|---|---|---:|---:|---:|---:|---|")
    for i, r in enumerate(results, start=1):
        short_tx = (r.arc_tx_hash[:10] + "…") if r.arc_tx_hash else "n/a"
        print(
            f"| {i} | `{r.market_id}` | {r.probability:.3f} | {r.confidence:.3f} | "
            f"${r.paid_usdc:.3f} | {r.latency_ms} ms | `{short_tx}` |"
        )
    total_paid = sum(r.paid_usdc for r in results)
    print(f"\n**Total spent:** ${total_paid:.4f} USDC over {len(results)} queries.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Demo runner — 5 oracle queries end-to-end.")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--payer", default="0x" + "D" * 40)
    parser.add_argument("--markets", nargs="*", default=DEFAULT_MARKETS)
    args = parser.parse_args(argv)

    with httpx.Client(timeout=120.0) as client:
        results = [query_oracle(client, args.base_url, m, args.payer) for m in args.markets]
    print_results(results)
    return 0


if __name__ == "__main__":
    sys.exit(main())
