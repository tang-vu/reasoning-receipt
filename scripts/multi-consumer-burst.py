"""multi-consumer-burst.py — drive distinct_consumers up via fresh EOAs.

The default daemon path emits with consumer_address=None (agent-internal).
The /price HTTP path records the X-Payment `payer` field as the consumer.
This script generates N random EOAs and posts a paid query per EOA per
market, pushing the dashboard's 'Consumers' metric from 1 → N+1 and the
'Distinct markets' metric upward too.

Each call:
  1. eth_account generates a fresh EOA (private key + address)
  2. GET /price/{market_id} → 402 challenge
  3. Build a synthetic x402 v2 X-Payment header using the fresh address
     (mock-mode server accepts any signature)
  4. Retry with X-Payment → 200 OK + on-chain receipt emitted
  5. Each receipt has THIS EOA's address in consumer_address

Usage:
    uv run python -m scripts.multi-consumer-burst --consumers 20 --markets 3
"""

from __future__ import annotations

import argparse
import base64
import json
import logging
import os
import time
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import httpx
from dotenv import load_dotenv
from eth_account import Account

load_dotenv()

DEFAULT_MARKETS = [
    "0x9b3edcfa0c0f4d6cd33d8fb5d97e89be32d9c61d80f2bc7b1018d6fbe9aa1c12",
    "0xe9a40a09ad8a99a5cef7d2c0e2c1e8b8d4d3c5b6a7e8f9012345678901234567",
    "0x7a3b1f5d8e2c9b6a4d7e0f1c2d3e4b5a6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1",
    "0xc3a8f2e1d4b7c0a9e8d5b6f3a2e1d0c9b8a7f6e5d4c3b2a1e0d9c8b7a6f5e4d",
    "0x5b4a3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d3e2f1a0b9c8d7e6f5a4",
]


@dataclass(slots=True)
class CallResult:
    consumer: str
    market_id: str
    status: int
    elapsed_ms: int
    receipt_id: int | None
    tx_hash: str | None
    error: str | None


def _build_payment_header(challenge_body: dict, payer: str, resource: str) -> tuple[str, str]:
    accept = challenge_body["accepts"][0]
    extra = accept.get("extra", {})
    inner = {
        "from": payer,
        "to": accept.get("payTo", accept.get("recipient", "")),
        "value": str(accept["amount"]),
        "validAfter": "0",
        "validBefore": str(int(time.time()) + accept.get("maxTimeoutSeconds", 600)),
        "nonce": accept["nonce"],
        "signature": "0x" + "ab" * 32,
    }
    payment = {
        "scheme": "exact",
        "network": accept["network"],
        "asset": accept["asset"],
        "amount": str(accept["amount"]),
        "nonce": accept["nonce"],
        "resource": resource,
        "payer": payer,
        "payload": inner,
        "extra": extra,
    }
    return base64.b64encode(json.dumps(payment).encode()).decode("ascii"), accept["nonce"]


def _one_call(
    base_url: str,
    consumer_address: str,
    market_id: str,
    *,
    timeout_s: float = 60.0,
) -> CallResult:
    resource = f"/price/{market_id}"
    start = time.perf_counter()
    try:
        with httpx.Client(timeout=timeout_s) as client:
            r1 = client.get(f"{base_url}{resource}")
            if r1.status_code != 402:
                return CallResult(
                    consumer=consumer_address,
                    market_id=market_id,
                    status=r1.status_code,
                    elapsed_ms=int((time.perf_counter() - start) * 1000),
                    receipt_id=None,
                    tx_hash=None,
                    error=f"expected 402, got {r1.status_code}",
                )
            body = r1.json()
            header, _ = _build_payment_header(body, consumer_address, resource)
            challenge_token = r1.headers.get("x-payment-challenge", "")
            r2 = client.get(
                f"{base_url}{resource}",
                headers={"X-Payment": header, "X-Payment-Challenge": challenge_token},
            )
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if r2.status_code != 200:
                return CallResult(
                    consumer=consumer_address,
                    market_id=market_id,
                    status=r2.status_code,
                    elapsed_ms=elapsed_ms,
                    receipt_id=None,
                    tx_hash=None,
                    error=r2.text[:200],
                )
            data = r2.json()
            return CallResult(
                consumer=consumer_address,
                market_id=market_id,
                status=200,
                elapsed_ms=elapsed_ms,
                receipt_id=int(data["receipt_id"]),
                tx_hash=str(data["arc_tx_hash"]),
                error=None,
            )
    except Exception as exc:  # noqa: BLE001
        return CallResult(
            consumer=consumer_address,
            market_id=market_id,
            status=0,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
            receipt_id=None,
            tx_hash=None,
            error=str(exc)[:200],
        )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://localhost:8000"))
    parser.add_argument("--consumers", type=int, default=20, help="number of fresh EOAs")
    parser.add_argument(
        "--markets",
        type=int,
        default=3,
        help="number of distinct markets each consumer queries",
    )
    parser.add_argument("--parallel", type=int, default=4, help="concurrent in-flight calls")
    parser.add_argument("--seed", type=int, default=None, help="optional seed for reproducible EOAs")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    log = logging.getLogger("burst")

    # 1. Spawn fresh EOAs
    eoas: list[str] = []
    for i in range(args.consumers):
        if args.seed is not None:
            extra_entropy = f"rr-burst-{args.seed}-{i}"
        else:
            extra_entropy = f"rr-burst-{time.time_ns()}-{i}"
        acct = Account.create(extra_entropy)
        eoas.append(acct.address)
    log.info("spawned %d fresh EOAs (first: %s…)", len(eoas), eoas[0][:10])

    # 2. Build (consumer, market) pairs
    market_ids = [
        m[:34] if m.startswith("0x") else m
        for m in DEFAULT_MARKETS[: args.markets]
    ]
    calls: list[tuple[str, str]] = [(eoa, mid) for eoa in eoas for mid in market_ids]
    log.info("planned %d paid calls across %d consumers × %d markets", len(calls), args.consumers, args.markets)

    # 3. Dispatch
    results: list[CallResult] = []
    t_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.parallel, thread_name_prefix="burst") as pool:
        futures = {
            pool.submit(_one_call, args.base_url, consumer, market): (consumer, market)
            for consumer, market in calls
        }
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            if res.status == 200:
                log.info(
                    "  ✓ %s @ %s → receipt #%d tx=%s (%dms)",
                    res.consumer[:10],
                    res.market_id[:14],
                    res.receipt_id,
                    res.tx_hash[:12] if res.tx_hash else "?",
                    res.elapsed_ms,
                )
            else:
                log.warning(
                    "  ✗ %s @ %s → status %d (%s)",
                    res.consumer[:10],
                    res.market_id[:14],
                    res.status,
                    (res.error or "")[:80],
                )

    elapsed = time.perf_counter() - t_start
    ok = sum(1 for r in results if r.status == 200)
    log.info("=" * 60)
    log.info("DONE in %.1fs — %d/%d successful (%d distinct consumers)",
             elapsed, ok, len(results), len(set(r.consumer for r in results if r.status == 200)))
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
