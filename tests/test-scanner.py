"""Scanner eligibility tests — liquidity, language, horizon filters."""

from __future__ import annotations

import datetime as _dt

from agent.analyst import MarketCandidate
from agent.scanner import MAX_HORIZON_DAYS, MIN_LIQUIDITY_USD, Scanner


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def test_mock_scanner_returns_eligible_candidates() -> None:
    scanner = Scanner(mock=True)
    results = scanner.scan()
    assert len(results) >= 1
    for c in results:
        assert c.liquidity_usd >= MIN_LIQUIDITY_USD
        if c.end_date:
            days = (c.end_date - _utcnow()).days
            assert 0 <= days <= MAX_HORIZON_DAYS


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
