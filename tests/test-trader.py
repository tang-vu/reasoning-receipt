"""Trader sizing tests — Kelly cap, edge floor, confidence haircut, wager floor."""

from __future__ import annotations

import datetime as _dt

import pytest

from agent.analyst import MarketCandidate
from agent.trace import ReasoningTrace
from agent.trader import KELLY_CAP, MIN_EDGE, MIN_WAGER_USDC, Trader, kelly_size


def _trace(prob: float, conf: float) -> ReasoningTrace:
    return ReasoningTrace(
        schema_version="rr-trace/1",
        market_id="m",
        market_source="polymarket",
        market_question="q?",
        claim="c",
        probability=prob,
        confidence=conf,
        horizon_days=7,
        sources=[],
        counter_arguments=[],
        sensitivity=[],
        summary="",
        model="mock",
        produced_at="2026-01-01T00:00:00Z",
        consumer_address=None,
    )


def _candidate(implied_yes: float = 0.45) -> MarketCandidate:
    return MarketCandidate(
        market_id="m",
        source="polymarket",
        question="q?",
        end_date=_dt.datetime.now(_dt.UTC) + _dt.timedelta(days=7),
        liquidity_usd=50_000.0,
        extra={"yes_price": implied_yes},
    )


def test_below_edge_floor_skips() -> None:
    size, kelly, action = kelly_size(
        bankroll_usdc=1000.0,
        probability=0.46,
        confidence=0.9,
        implied=0.45,
    )
    assert action == "SKIP"
    assert size == 0.0


def test_buy_yes_when_under_priced() -> None:
    size, kelly, action = kelly_size(
        bankroll_usdc=1000.0,
        probability=0.65,
        confidence=0.9,
        implied=0.45,
    )
    assert action == "BUY_YES"
    assert size > 0.0
    assert kelly <= KELLY_CAP + 1e-9


def test_buy_no_when_over_priced() -> None:
    size, kelly, action = kelly_size(
        bankroll_usdc=1000.0,
        probability=0.30,
        confidence=0.9,
        implied=0.55,
    )
    assert action == "BUY_NO"
    assert size > 0.0


def test_low_confidence_halves_kelly() -> None:
    # Pick (prob, implied) so raw Kelly sits *below* the cap — then the confidence
    # haircut is visible rather than swallowed by the clamp.
    _, kelly_high, _ = kelly_size(bankroll_usdc=1000.0, probability=0.14, confidence=0.9, implied=0.10)
    _, kelly_low, _ = kelly_size(bankroll_usdc=1000.0, probability=0.14, confidence=0.5, implied=0.10)
    assert 0 < kelly_high < KELLY_CAP
    assert kelly_low == pytest.approx(kelly_high / 2.0, rel=1e-6)


def test_wager_floor_skips_dust() -> None:
    size, _, action = kelly_size(
        bankroll_usdc=0.5,
        probability=0.55,
        confidence=0.9,
        implied=0.45,
    )
    assert action == "SKIP"
    assert size == 0.0


def test_decision_records_position() -> None:
    trader = Trader(bankroll_provider=lambda: 1_000.0, mock=True)
    trace = _trace(prob=0.7, conf=0.9)
    candidate = _candidate()
    decision = trader.decide(candidate=candidate, trace=trace)
    assert decision.action == "BUY_YES"
    position = trader.execute(candidate=candidate, trace=trace, decision=decision, receipt_id=1)
    assert position is not None
    assert position.size_usdc == decision.size_usdc
    assert position.polymarket_order_id.startswith("mock-")


def test_constants_are_sane() -> None:
    assert MIN_EDGE > 0
    assert 0 < KELLY_CAP < 0.5
    assert MIN_WAGER_USDC > 0
