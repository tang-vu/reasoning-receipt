"""SQLAlchemy 2.0 ORM — receipts, positions, scan candidates.

Single engine for both SQLite (dev) and Postgres (prod via Neon). The DATABASE_URL
in `.env` decides — no code branch needed.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.orm import Session as OrmSession

_DEFAULT_DB_URL = "sqlite:///./data/reasoning_receipt.db"


def _db_url() -> str:
    url = os.getenv("DATABASE_URL", _DEFAULT_DB_URL)
    if url.startswith("sqlite:///./"):
        Path(url.replace("sqlite:///./", "")).parent.mkdir(parents=True, exist_ok=True)
    return url


class Base(DeclarativeBase):
    """ORM base."""


def _now() -> datetime:
    return datetime.now(UTC)


class Receipt(Base):
    """One row per published receipt. Mirrors the on-chain Receipt event."""

    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    chain_receipt_id = Column(Integer, nullable=True, index=True)
    market_id = Column(String(80), nullable=False, index=True)
    market_question = Column(Text, nullable=True)
    market_source = Column(String(16), nullable=False, default="polymarket")
    probability = Column(Float, nullable=False)
    confidence = Column(Float, nullable=False)
    trace_hash = Column(String(70), nullable=False, index=True)
    trace_cid = Column(String(120), nullable=False)
    consumer_address = Column(String(64), nullable=True, index=True)
    publisher_address = Column(String(64), nullable=False)
    paid_micro_usdc = Column(Integer, nullable=False, default=0)
    arc_tx_hash = Column(String(80), nullable=True, index=True)
    arc_block_number = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_now, index=True)

    # Backtest: filled in later when the underlying market resolves.
    # resolved_outcome in [0.0, 1.0] (binary outcome for YES/NO markets).
    resolved_at = Column(DateTime(timezone=True), nullable=True, index=True)
    resolved_outcome = Column(Float, nullable=True)

    # rr-trace/3 columns: schema lineage + multi-agent disagreement signal +
    # the trace's category for per-category calibration (Phase 5).
    # Defaults preserve back-compat — existing rr-trace/2 rows read as such.
    schema_version = Column(String(16), nullable=False, default="rr-trace/2", index=True)
    disagreement_pp = Column(Float, nullable=True)
    merkle_root = Column(String(70), nullable=True, index=True)
    category = Column(String(16), nullable=True, index=True)

    __table_args__ = (Index("ix_receipts_market_created", "market_id", "created_at"),)


class Position(Base):
    """One row per portfolio bet placed by the trader."""

    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String(80), nullable=False, index=True)
    side = Column(String(8), nullable=False)
    outcome = Column(String(64), nullable=True)
    size_usdc = Column(Float, nullable=False)
    entry_price = Column(Float, nullable=False)
    receipt_id = Column(Integer, nullable=True, index=True)
    polymarket_order_id = Column(String(80), nullable=True)
    status = Column(String(16), nullable=False, default="open")
    realized_pnl_usdc = Column(Float, nullable=False, default=0.0)
    opened_at = Column(DateTime(timezone=True), nullable=False, default=_now)
    closed_at = Column(DateTime(timezone=True), nullable=True)


class ScanCandidate(Base):
    """One row per market the scanner considers eligible for analysis."""

    __tablename__ = "scan_candidates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    market_id = Column(String(80), nullable=False, unique=True, index=True)
    source = Column(String(16), nullable=False, default="polymarket")
    question = Column(Text, nullable=False)
    liquidity_usd = Column(Float, nullable=False)
    end_date = Column(DateTime(timezone=True), nullable=True)
    last_priced_at = Column(DateTime(timezone=True), nullable=True)
    last_probability = Column(Float, nullable=True)
    discovered_at = Column(DateTime(timezone=True), nullable=False, default=_now)


class MemoryItem(Base):
    """Cached embedding of a resolved market, keyed by its receipt.

    The memory loop (`agent.memory`) embeds the question of each resolved
    receipt once and caches the raw float32 vector here. Retrieval loads every
    cached vector and runs cosine similarity in-process — no vector-DB
    extension needed for the small resolved-market set. One row per receipt;
    re-embedding is skipped when a row already exists (idempotent backfill).
    """

    __tablename__ = "memory_items"

    receipt_id = Column(Integer, primary_key=True)  # FK-ish to receipts.id
    market_id = Column(String(80), nullable=False, index=True)
    question = Column(Text, nullable=False)
    category = Column(String(16), nullable=True)
    probability = Column(Float, nullable=False)
    resolved_outcome = Column(Float, nullable=False)
    embedding = Column(LargeBinary, nullable=False)  # float32 bytes, model-native dim
    embed_model = Column(String(48), nullable=False, default="mock")
    embedded_at = Column(DateTime(timezone=True), nullable=False, default=_now)


_engine = None
_Session: sessionmaker | None = None


def init_db(url: str | None = None) -> None:
    """Create tables if missing. Idempotent. Pre-warms the global engine."""
    global _engine, _Session
    _engine = create_engine(url or _db_url(), future=True, pool_pre_ping=True)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    _migrate(_engine)


def _migrate(engine) -> None:
    """Idempotent ALTER TABLE migrations for columns added after table creation.

    SQLite-friendly. Each ADD COLUMN is wrapped in a try/except so re-runs are safe.
    """
    from sqlalchemy import text

    statements = [
        # rr-trace/2 backtest columns
        "ALTER TABLE receipts ADD COLUMN resolved_at DATETIME",
        "ALTER TABLE receipts ADD COLUMN resolved_outcome FLOAT",
        # rr-trace/3 columns — schema lineage + ensemble signal + category
        "ALTER TABLE receipts ADD COLUMN schema_version VARCHAR(16) DEFAULT 'rr-trace/2'",
        "ALTER TABLE receipts ADD COLUMN disagreement_pp FLOAT",
        "ALTER TABLE receipts ADD COLUMN merkle_root VARCHAR(70)",
        "ALTER TABLE receipts ADD COLUMN category VARCHAR(16)",
    ]
    import contextlib

    with engine.begin() as conn:
        for sql in statements:
            with contextlib.suppress(Exception):
                conn.execute(text(sql))


@contextmanager
def Session() -> Iterator[OrmSession]:
    """Scoped session contextmanager. Auto-commits on success, rolls back on error."""
    if _Session is None:
        init_db()
    assert _Session is not None
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
