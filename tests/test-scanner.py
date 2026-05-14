"""Scanner eligibility tests — liquidity, language, horizon filters.

Covers both Polymarket and Kalshi adapters and the source-specific
liquidity floors that come with them.
"""

from __future__ import annotations

import datetime as _dt

from agent.analyst import MarketCandidate
from agent.scanner import (
    KALSHI_MIN_NOTIONAL_USD,
    MAX_HORIZON_DAYS,
    MIN_LIQUIDITY_USD,
    Scanner,
    _interleave_by_source,
)


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def test_mock_scanner_returns_eligible_candidates() -> None:
    scanner = Scanner(mock=True)
    results = scanner.scan()
    assert len(results) >= 1
    for c in results:
        floor = KALSHI_MIN_NOTIONAL_USD if c.source == "kalshi" else MIN_LIQUIDITY_USD
        assert c.liquidity_usd >= floor
        if c.end_date:
            end = c.end_date
            if end.tzinfo is None:
                end = end.replace(tzinfo=_dt.UTC)
            days = (end - _utcnow()).days
            assert 0 <= days <= MAX_HORIZON_DAYS


def test_mock_scanner_includes_both_sources() -> None:
    """RFB 03 reads 'markets' plural — pipeline must serve both venues."""
    scanner = Scanner(mock=True)
    results = scanner.scan()
    sources = {c.source for c in results}
    assert "polymarket" in sources
    assert "kalshi" in sources


def test_eligibility_filters() -> None:
    scanner = Scanner(mock=True)
    too_illiquid = MarketCandidate(
        market_id="x",
        source="polymarket",
        question="Q?",
        end_date=_utcnow() + _dt.timedelta(days=10),
        liquidity_usd=500.0,
    )
    too_far = MarketCandidate(
        market_id="y",
        source="polymarket",
        question="Q?",
        end_date=_utcnow() + _dt.timedelta(days=120),
        liquidity_usd=50_000.0,
    )
    not_english = MarketCandidate(
        market_id="z",
        source="polymarket",
        question="非常长的非英文问题 测试 测试 测试 测试 测试 测试",
        end_date=_utcnow() + _dt.timedelta(days=10),
        liquidity_usd=50_000.0,
    )
    fine = MarketCandidate(
        market_id="ok",
        source="polymarket",
        question="Will this be eligible?",
        end_date=_utcnow() + _dt.timedelta(days=10),
        liquidity_usd=50_000.0,
    )
    assert scanner._is_eligible(too_illiquid) is False
    assert scanner._is_eligible(too_far) is False
    assert scanner._is_eligible(not_english) is False
    assert scanner._is_eligible(fine) is True


def test_kalshi_uses_lower_liquidity_floor() -> None:
    """Polymarket 24h volume and Kalshi open-interest aren't apples-to-apples."""
    scanner = Scanner(mock=True)
    poly_borderline = MarketCandidate(
        market_id="poly-bord",
        source="polymarket",
        question="Will the borderline Polymarket case pass?",
        end_date=_utcnow() + _dt.timedelta(days=10),
        liquidity_usd=KALSHI_MIN_NOTIONAL_USD + 500.0,  # > kalshi floor, < polymarket floor
    )
    kalshi_borderline = MarketCandidate(
        market_id="kal-bord",
        source="kalshi",
        question="Will the borderline Kalshi case pass?",
        end_date=_utcnow() + _dt.timedelta(days=10),
        liquidity_usd=KALSHI_MIN_NOTIONAL_USD + 500.0,
    )
    # Same liquidity, different source — Kalshi passes, Polymarket doesn't.
    assert scanner._is_eligible(poly_borderline) is False
    assert scanner._is_eligible(kalshi_borderline) is True


def _mk(name: str, source: str) -> MarketCandidate:
    return MarketCandidate(
        market_id=name,
        source=source,
        question="q",
        end_date=None,
        liquidity_usd=1.0,
    )


def test_interleave_round_robin() -> None:
    poly = [_mk(f"p{i}", "polymarket") for i in range(3)]
    kal = [_mk(f"k{i}", "kalshi") for i in range(6)]
    merged = _interleave_by_source(poly, kal)
    # First 3 = one Polymarket, one Kalshi, one Polymarket — both sources land
    # inside the per_tick=3 slice on the very first tick.
    assert [c.source for c in merged[:3]] == ["polymarket", "kalshi", "polymarket"]
    # All inputs preserved, none dropped, original order preserved within each.
    assert len(merged) == len(poly) + len(kal)
    assert [c.market_id for c in merged if c.source == "polymarket"] == [
        c.market_id for c in poly
    ]
    assert [c.market_id for c in merged if c.source == "kalshi"] == [
        c.market_id for c in kal
    ]


def test_interleave_handles_empty_source() -> None:
    poly = [_mk(f"p{i}", "polymarket") for i in range(3)]
    merged = _interleave_by_source(poly, [])
    assert [c.market_id for c in merged] == ["p0", "p1", "p2"]


def test_kalshi_naive_close_time_does_not_crash() -> None:
    """Some Kalshi rows have stripped tz info — eligibility must be tz-safe."""
    scanner = Scanner(mock=True)
    naive = MarketCandidate(
        market_id="kal-naive",
        source="kalshi",
        question="Will tz-naive close_time be handled?",
        end_date=_dt.datetime.utcnow() + _dt.timedelta(days=10),  # noqa: DTZ003 — intentional
        liquidity_usd=20_000.0,
    )
    # Should not raise — and naive close inside the 30d horizon stays eligible.
    assert scanner._is_eligible(naive) is True
