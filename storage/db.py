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


_engine = None
_Session: sessionmaker | None = None


def init_db(url: str | None = None) -> None:
    """Create tables if missing. Idempotent. Pre-warms the global engine."""
    global _engine, _Session
    _engine = create_engine(url or _db_url(), future=True, pool_pre_ping=True)
    Base.metadata.create_all(_engine)
    _Session = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


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
