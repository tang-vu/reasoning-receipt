"""One-shot smoke test: build an rr-trace/3 trace in mock mode, upload to
Irys, emit ReceiptV2 on Arc Testnet. Verifies the full V2 emit path without
committing the daemon to it.

Usage:
    uv run python -m scripts.smoke-publish-v2

Cost: ~$0.002 USDC (one Arc tx) + a few KB Irys upload.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from dotenv import load_dotenv

from agent.analyst import MarketCandidate
from agent.ensemble import Ensemble
from server.chain import ChainClient
from storage.irys import IrysClient


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s")
    log = logging.getLogger("smoke")

    candidate = MarketCandidate(
        market_id="smoke-v2-test-1",
        source="smoke",
        question="Smoke test: is the V2 emit path live?",
        end_date=datetime(2026, 12, 31, tzinfo=UTC),
        liquidity_usd=0.0,
    )

    log.info("step 1/3: ensemble.analyse (mock mode — no Gemini cost)")
    trace = Ensemble(mock=True).analyse(candidate)
    log.info("  schema:      %s", trace.schema_version)
    log.info("  category:    %s", trace.category)
    log.info("  probability: %.4f", trace.claim.probability)
    log.info("  disagreement:%.2fpp", trace.supervisor_synthesis.disagreement_pp)
    log.info("  critic:      %s", trace.critic_audit.verdict)

    log.info("step 2/3: irys upload (real — ~3KB bundle)")
    irys = IrysClient()
    upload = irys.upload(trace.to_dict())
    log.info("  cid:         %s", upload.cid)
    log.info("  size_bytes:  %d", upload.size_bytes)
    log.info("  hash:        %s", upload.hash_hex)
    log.info("  is_mock:     %s", upload.is_mock)

    log.info("step 3/3: publish_v2 to Arc Testnet")
    merkle_root = trace.merkle_root_hex()
    log.info("  merkle_root: %s", merkle_root)
    chain = ChainClient()
    if chain.mock:
        log.warning("chain is in mock mode — won't hit Arc. Check .env.")
    log.info("  v2 addr:     %s", chain.registry_v2_address)
    result = chain.publish_v2(
        consumer_address=None,
        market_id=candidate.market_id,
        probability=trace.claim.probability,
        confidence=trace.claim.confidence,
        trace_hash_hex=upload.hash_hex,
        merkle_root_hex=merkle_root,
        schema_version=trace.schema_version,
        trace_cid=upload.cid,
    )
    log.info("  receipt_id:  %d", result.receipt_id)
    log.info("  tx_hash:     %s", result.tx_hash)
    log.info("  block:       %s", result.block_number)
    log.info("  is_mock:     %s", result.is_mock)
    if not result.is_mock:
        log.info("DONE. https://testnet.arcscan.app/tx/%s", result.tx_hash)
    else:
        log.warning("DONE in mock mode — no real Arc tx. Set RPC/V2 address to test real path.")


if __name__ == "__main__":
    main()
