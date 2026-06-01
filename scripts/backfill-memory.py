"""backfill-memory.py — embed every resolved receipt into the memory store.

`agent.memory.MarketMemory` self-syncs lazily: each live `retrieve()` embeds at
most `RR_MEMORY_EMBED_BUDGET` (default 20) not-yet-cached resolved receipts. On
a cold cache with thousands of resolved markets that warm-up takes many ticks
before the retrieval prior covers the whole backlog. This one-shot script drains
the queue up front so the prior fires against the full history immediately.

It is a thin driver over `MarketMemory._embed_missing` — same write path, same
idempotency (one `memory_items` row per `receipt_id`, re-runs skip cached rows),
same mock/real embedding selection. Real mode batches with a short sleep between
batches so a few-thousand-call backfill stays inside the Gemini embed quota;
mock mode (offline / `RR_MOCK_ANALYST=1`) needs no network and runs flat out.

Usage:
    uv run python scripts/backfill-memory.py                 # real or mock per .env
    uv run python scripts/backfill-memory.py --batch 50 --sleep 1.0
    uv run python scripts/backfill-memory.py --mock          # force offline vectors
"""

from __future__ import annotations

import argparse
import logging
import sys
import time

from sqlalchemy import func, select

from agent.memory import MarketMemory
from storage.db import MemoryItem, Session, init_db
from storage.db import Receipt as ReceiptRow

logger = logging.getLogger("rr.backfill-memory")


def _resolved_count() -> int:
    with Session() as session:
        return (
            session.scalar(
                select(func.count())
                .select_from(ReceiptRow)
                .where(
                    ReceiptRow.resolved_outcome.is_not(None),
                    ReceiptRow.market_question.is_not(None),
                )
            )
            or 0
        )


def _cached_count() -> int:
    with Session() as session:
        return session.scalar(select(func.count()).select_from(MemoryItem)) or 0


def backfill(*, mock: bool | None = None, batch: int = 50, sleep_s: float = 1.0) -> int:
    """Embed all not-yet-cached resolved receipts. Returns the number embedded.

    Loops `MarketMemory._embed_missing(batch)` until it reports zero progress.
    Each batch is its own DB transaction, so an interrupted run leaves a
    consistent partial cache that a re-run resumes from (idempotent).
    """
    mem = MarketMemory(mock=mock)
    resolved = _resolved_count()
    start_cached = _cached_count()
    pending = max(resolved - start_cached, 0)
    logger.info(
        "backfill: %d resolved receipts, %d already embedded, %d pending (model=%s)",
        resolved,
        start_cached,
        pending,
        mem._model_tag,
    )
    if pending == 0:
        logger.info("backfill: nothing to do — memory is already warm")
        return 0

    total = 0
    while True:
        added = mem._embed_missing(batch)
        if added == 0:
            break
        total += added
        logger.info("backfill: embedded %d / %d", start_cached + total, resolved)
        # Real embeddings hit a remote quota; mock vectors are local CPU only.
        if not mem.mock and sleep_s > 0:
            time.sleep(sleep_s)

    logger.info("backfill: done — %d newly embedded, %d total cached", total, _cached_count())
    return total


def main(argv: list[str] | None = None) -> int:
    # Load .env before init_db() so DATABASE_URL points at the populated DB the
    # daemon writes to (mirrors scripts/export-snapshot.py).
    try:
        from dotenv import load_dotenv  # noqa: PLC0415

        load_dotenv()
    except ImportError:
        pass

    parser = argparse.ArgumentParser(description="Backfill the market-memory embedding store.")
    parser.add_argument("--batch", type=int, default=50, help="receipts embedded per transaction")
    parser.add_argument("--sleep", type=float, default=1.0, help="seconds between real-embed batches")
    parser.add_argument("--mock", action="store_true", help="force deterministic offline vectors")
    args = parser.parse_args(argv)

    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
    init_db()
    backfill(mock=True if args.mock else None, batch=args.batch, sleep_s=args.sleep)
    return 0


if __name__ == "__main__":
    sys.exit(main())
