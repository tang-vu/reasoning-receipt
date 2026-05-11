"""seed-demo.py — populate the local SQLite with a believable receipt history.

For dashboard development + screen-recording: produces N agent-internal receipts
across the mock market fixture so the dashboard charts are not empty.

Usage:
    uv run python -m scripts.seed-demo --count 50
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from agent.analyst import Analyst
from agent.scanner import Scanner
from agent.trace import TraceSealer
from server.chain import ChainClient
from storage.db import Receipt as ReceiptRow
from storage.db import Session, init_db
from storage.irys import IrysClient

logger = logging.getLogger("rr.seed")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed the receipts DB with synthetic rows.")
    parser.add_argument("--count", type=int, default=50)
    parser.add_argument("--mock", action="store_true", default=True)
    args = parser.parse_args(argv)

    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
    init_db()

    scanner = Scanner(mock=args.mock)
    analyst = Analyst(mock=args.mock)
    sealer = TraceSealer(IrysClient(mock=args.mock))
    chain = ChainClient(mock=args.mock)

    candidates = scanner.scan()
    if not candidates:
        logger.error("seed: no candidates")
        return 1

    written = 0
    for i in range(args.count):
        candidate = candidates[i % len(candidates)]
        trace = analyst.analyse(candidate)
        sealed = sealer.seal(trace)
        publish = chain.publish(
            consumer_address=None,
            market_id=candidate.market_id,
            probability=trace.probability,
            confidence=trace.confidence,
            trace_hash_hex=sealed.hash_hex,
            trace_cid=sealed.cid,
        )
        with Session() as session:
            session.add(
                ReceiptRow(
                    chain_receipt_id=publish.receipt_id,
                    market_id=candidate.market_id,
                    market_question=candidate.question,
                    market_source=candidate.source,
                    probability=trace.probability,
                    confidence=trace.confidence,
                    trace_hash=sealed.hash_hex,
                    trace_cid=sealed.cid,
                    consumer_address=None,
                    publisher_address=chain.publisher_address,
                    paid_micro_usdc=0,
                    arc_tx_hash=publish.tx_hash,
                    arc_block_number=publish.block_number,
                    latency_ms=100 + (i % 50) * 3,
                )
            )
        written += 1
        if (i + 1) % 10 == 0:
            logger.info("seed: %d/%d", i + 1, args.count)
        time.sleep(0.005)
    logger.info("seed: wrote %d receipts", written)
    return 0


if __name__ == "__main__":
    sys.exit(main())
