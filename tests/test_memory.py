"""Market-memory tests — retrieval prior from resolved receipts.

Covers: deterministic mock embedding, cosine top-k ordering, similarity floor,
self-syncing cache from resolved receipts, embed budget cap, idempotent
re-embedding, prior_text formatting + hit/miss labelling, empty-store no-op,
and the Ensemble smoke path accepting the experience prior.

Runs offline — conftest forces RR_MOCK_ANALYST=1 so MarketMemory uses the
deterministic hash-based pseudo-embedding (no network, no creds).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from agent.memory import (
    EMBED_DIM,
    MarketMemory,
    _bytes_to_vec,
    _cosine,
    _mock_embed,
    _vec_to_bytes,
)
from storage.db import MemoryItem, Receipt, Session, init_db

# ---------------------------------------------------------------------------
# embedding primitives
# ---------------------------------------------------------------------------


def test_mock_embed_is_deterministic() -> None:
    a = _mock_embed("Will BTC top 100k by 2026?")
    b = _mock_embed("Will BTC top 100k by 2026?")
    assert a == b
    assert len(a) == EMBED_DIM


def test_mock_embed_differs_by_text() -> None:
    a = _mock_embed("question one")
    b = _mock_embed("question two")
    assert a != b


def test_vec_roundtrip_through_bytes() -> None:
    vec = _mock_embed("roundtrip")
    restored = _bytes_to_vec(_vec_to_bytes(vec))
    assert len(restored) == len(vec)
    # float32 pack/unpack — tolerate tiny precision loss
    for x, y in zip(vec, restored, strict=True):
        assert abs(x - y) < 1e-6


def test_cosine_identical_is_one() -> None:
    v = _mock_embed("same")
    assert _cosine(v, v) == 1.0 or abs(_cosine(v, v) - 1.0) < 1e-6


def test_cosine_zero_vector_is_zero() -> None:
    assert _cosine([0.0] * EMBED_DIM, _mock_embed("x")) == 0.0


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def _seed_resolved_receipt(
    *,
    rid: int,
    question: str,
    probability: float,
    outcome: float,
    category: str = "crypto",
) -> None:
    """Insert one resolved receipt row directly."""
    with Session() as session:
        session.add(
            Receipt(
                id=rid,
                market_id=f"poly-{rid}",
                market_question=question,
                market_source="polymarket",
                probability=probability,
                confidence=0.7,
                trace_hash=f"0x{'a' * 64}",
                trace_cid="bafy-test",
                publisher_address="0xpub",
                paid_micro_usdc=0,
                schema_version="rr-trace/3",
                category=category,
                resolved_at=datetime.now(UTC) - timedelta(days=1),
                resolved_outcome=outcome,
            )
        )


def _seed_open_receipt(*, rid: int, question: str) -> None:
    """Insert an unresolved receipt — must be ignored by memory."""
    with Session() as session:
        session.add(
            Receipt(
                id=rid,
                market_id=f"poly-{rid}",
                market_question=question,
                market_source="polymarket",
                probability=0.5,
                confidence=0.5,
                trace_hash=f"0x{'b' * 64}",
                trace_cid="bafy-open",
                publisher_address="0xpub",
                paid_micro_usdc=0,
                schema_version="rr-trace/3",
                category="crypto",
            )
        )


# ---------------------------------------------------------------------------
# retrieval + self-sync
# ---------------------------------------------------------------------------


def test_retrieve_empty_store_returns_nothing() -> None:
    init_db()
    mem = MarketMemory(mock=True)
    assert mem.retrieve("anything") == []
    assert mem.prior_text("anything") == ""


def test_retrieve_only_embeds_resolved_receipts() -> None:
    init_db()
    _seed_resolved_receipt(rid=1, question="Will ETH flip BTC by 2027?", probability=0.2, outcome=0.0)
    _seed_open_receipt(rid=2, question="Will ETH flip BTC by 2027?")  # ignored
    mem = MarketMemory(mock=True)
    mem.retrieve("Will ETH flip BTC soon?")
    with Session() as session:
        cached = {rid for (rid,) in session.execute(select(MemoryItem.receipt_id))}
    assert cached == {1}  # only the resolved one got embedded


def test_retrieve_ranks_more_similar_first() -> None:
    init_db()
    _seed_resolved_receipt(rid=1, question="Will the Fed cut rates in June 2026?", probability=0.6, outcome=1.0)
    _seed_resolved_receipt(rid=2, question="completely unrelated sports question about tennis", probability=0.3, outcome=0.0)
    mem = MarketMemory(mock=True)
    # Query identical to receipt 1's question → it should rank first (sim ~1.0).
    hits = mem.retrieve("Will the Fed cut rates in June 2026?")
    assert hits
    assert hits[0][0].receipt_id == 1
    assert hits[0][1] >= 0.99  # near-perfect cosine on identical text


def test_similarity_floor_filters_unrelated() -> None:
    init_db()
    _seed_resolved_receipt(rid=1, question="totally different topic XYZ", probability=0.5, outcome=1.0)
    mem = MarketMemory(mock=True)
    # An unrelated query: mock vectors are near-orthogonal, cosine < MIN_SIMILARITY.
    hits = mem.retrieve("an entirely separate unrelated matter ABC")
    assert all(score >= 0.55 for _, score in hits)


def test_embed_budget_caps_per_call() -> None:
    init_db()
    for i in range(1, 6):
        _seed_resolved_receipt(rid=i, question=f"resolved market number {i}", probability=0.5, outcome=1.0)
    mem = MarketMemory(mock=True)
    mem.retrieve("query", embed_budget=2)  # only 2 of 5 embedded this call
    with Session() as session:
        n = session.scalar(select(func.count()).select_from(MemoryItem))
    assert n == 2


def test_reembedding_is_idempotent() -> None:
    init_db()
    _seed_resolved_receipt(rid=1, question="idempotent market", probability=0.5, outcome=1.0)
    mem = MarketMemory(mock=True)
    mem.retrieve("idempotent market")
    mem._invalidate()
    mem.retrieve("idempotent market")  # second pass must not duplicate
    with Session() as session:
        n = session.scalar(select(func.count()).select_from(MemoryItem))
    assert n == 1


# ---------------------------------------------------------------------------
# prior_text formatting
# ---------------------------------------------------------------------------


def test_prior_text_labels_hit_and_outcome() -> None:
    init_db()
    # Predicted 90% YES, resolved YES → hit.
    _seed_resolved_receipt(rid=1, question="Will the incumbent win the 2026 election?", probability=0.9, outcome=1.0)
    mem = MarketMemory(mock=True)
    text = mem.prior_text("Will the incumbent win the 2026 election?")
    assert text.startswith("Prior similar markets")
    assert "resolved YES" in text
    assert "hit" in text
    assert "90%" in text


def test_prior_text_labels_miss() -> None:
    init_db()
    # Predicted 85% YES, resolved NO → miss.
    _seed_resolved_receipt(rid=1, question="Will it rain on launch day in Texas?", probability=0.85, outcome=0.0)
    mem = MarketMemory(mock=True)
    text = mem.prior_text("Will it rain on launch day in Texas?")
    assert "resolved NO" in text
    assert "miss" in text


# ---------------------------------------------------------------------------
# Ensemble smoke path
# ---------------------------------------------------------------------------


def test_ensemble_accepts_experience_prior() -> None:
    """ensemble.analyse swallows an experience_prior string without error."""
    from agent.analyst import MarketCandidate
    from agent.ensemble import Ensemble

    init_db()
    _seed_resolved_receipt(rid=1, question="Will the Fed cut rates by June 2026?", probability=0.6, outcome=1.0)
    mem = MarketMemory(mock=True)
    prior = mem.prior_text("Will the Fed cut rates by June 2026?")
    assert prior  # smoke

    candidate = MarketCandidate(
        market_id="poly-exp-1",
        source="polymarket",
        question="Will the Fed cut rates by June 2026?",
        end_date=datetime(2026, 6, 30, tzinfo=UTC),
        liquidity_usd=125_000.0,
    )
    trace = Ensemble(mock=True).analyse(candidate, experience_prior=prior)
    # Mock supervisor still produces a valid trace; the prior just rode along.
    assert trace.claim.probability >= 0.0
    assert trace.supervisor_synthesis is not None


# ---------------------------------------------------------------------------
# bulk backfill script (scripts/backfill-memory.py)
# ---------------------------------------------------------------------------


def _load_backfill_module():
    """Import the hyphenated backfill script by path (not a dotted module)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "scripts" / "backfill-memory.py"
    spec = importlib.util.spec_from_file_location("backfill_memory", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_backfill_drains_entire_resolved_backlog() -> None:
    init_db()
    # More receipts than one batch — backfill must loop until all are embedded,
    # unlike a single self-syncing retrieve which stops at the budget cap.
    for i in range(1, 13):
        _seed_resolved_receipt(rid=i, question=f"backfill market {i}", probability=0.5, outcome=1.0)
    backfill = _load_backfill_module()
    added = backfill.backfill(mock=True, batch=5, sleep_s=0.0)
    assert added == 12
    with Session() as session:
        n = session.scalar(select(func.count()).select_from(MemoryItem))
    assert n == 12


def test_backfill_is_idempotent_and_resumes() -> None:
    init_db()
    for i in range(1, 6):
        _seed_resolved_receipt(rid=i, question=f"resume market {i}", probability=0.4, outcome=0.0)
    backfill = _load_backfill_module()
    first = backfill.backfill(mock=True, batch=3, sleep_s=0.0)
    assert first == 5
    # Re-run over the same DB: nothing new, no duplicates.
    second = backfill.backfill(mock=True, batch=3, sleep_s=0.0)
    assert second == 0
    with Session() as session:
        n = session.scalar(select(func.count()).select_from(MemoryItem))
    assert n == 5


def test_backfill_skips_unresolved_receipts() -> None:
    init_db()
    _seed_resolved_receipt(rid=1, question="resolved one", probability=0.5, outcome=1.0)
    _seed_open_receipt(rid=2, question="still open")
    backfill = _load_backfill_module()
    added = backfill.backfill(mock=True, batch=10, sleep_s=0.0)
    assert added == 1
