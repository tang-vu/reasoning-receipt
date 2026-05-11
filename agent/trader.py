"""Kelly-sized portfolio trader.

Input: an analyst probability + confidence + a market candidate.
Output: a `TradeDecision`. If actionable, submits a (mock or live) order via
Polymarket CLOB.

Mock mode (`RR_MOCK_TRADER=1` or missing creds): logs decisions to the DB,
returns success without hitting Polymarket. This is how Phase 1/2 prove out
the loop before live orders.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from typing import Literal

import httpx

from storage.db import Position, Session

from .analyst import MarketCandidate
from .trace import ReasoningTrace

logger = logging.getLogger(__name__)

Action = Literal["BUY_YES", "BUY_NO", "SKIP"]

MIN_EDGE = 0.04
KELLY_CAP = 0.05
MIN_WAGER_USDC = 0.10


@dataclass(slots=True)
class TradeDecision:
    action: Action
    size_usdc: float
    limit_price: float
    edge: float
    kelly_fraction: float
    reason: str


@dataclass(slots=True)
class MarketQuote:
    """Snapshot of order-book midpoint + 24h volume."""

    yes_price: float
    no_price: float
    volume_24h_usd: float


def quote_implied(candidate: MarketCandidate) -> MarketQuote:
    """Best-effort implied quote. Mock returns 0.45 unless candidate.extra carries one."""
    if candidate.extra and "yes_price" in candidate.extra:
        yp = float(candidate.extra["yes_price"])
        return MarketQuote(yes_price=yp, no_price=max(0.0, 1.0 - yp), volume_24h_usd=candidate.liquidity_usd)
    return MarketQuote(yes_price=0.45, no_price=0.55, volume_24h_usd=candidate.liquidity_usd)


def kelly_size(
    *,
    bankroll_usdc: float,
    probability: float,
    confidence: float,
    implied: float,
) -> tuple[float, float, Action]:
    """Return (size_usdc, kelly_fraction, action). action='SKIP' if no edge."""
    edge = probability - implied
    if abs(edge) < MIN_EDGE:
        return 0.0, 0.0, "SKIP"

    if edge > 0:
        action: Action = "BUY_YES"
        kelly = edge / max(1e-6, 1.0 - implied)
    else:
        action = "BUY_NO"
        kelly = -edge / max(1e-6, implied)

    if confidence < 0.7:
        kelly *= 0.5

    kelly = max(0.0, min(KELLY_CAP, kelly))
    size = round(bankroll_usdc * kelly, 2)
    if size < MIN_WAGER_USDC:
        return 0.0, kelly, "SKIP"
    return size, kelly, action


class Trader:
    def __init__(
        self,
        *,
        bankroll_provider=None,
        polymarket_base: str = "https://clob.polymarket.com",
        mock: bool | None = None,
    ) -> None:
        self.bankroll_provider = bankroll_provider
        self.polymarket_base = polymarket_base.rstrip("/")
        env_mock = os.getenv("RR_MOCK_TRADER", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        if not os.getenv("POLYMARKET_API_KEY"):
            self.mock = True

    def decide(self, *, candidate: MarketCandidate, trace: ReasoningTrace) -> TradeDecision:
        implied = quote_implied(candidate).yes_price
        bankroll = self._bankroll()
        size, kelly, action = kelly_size(
            bankroll_usdc=bankroll,
            probability=trace.probability,
            confidence=trace.confidence,
            implied=implied,
        )
        edge = trace.probability - implied
        if action == "SKIP":
            return TradeDecision(
                action="SKIP",
                size_usdc=0.0,
                limit_price=implied,
                edge=edge,
                kelly_fraction=kelly,
                reason=f"|edge|={abs(edge):.3f} below {MIN_EDGE} or size below ${MIN_WAGER_USDC}",
            )
        return TradeDecision(
            action=action,
            size_usdc=size,
            limit_price=trace.probability if action == "BUY_YES" else 1.0 - trace.probability,
            edge=edge,
            kelly_fraction=kelly,
            reason=f"edge={edge:+.3f}, conf={trace.confidence:.2f}, kelly={kelly:.3f}",
        )

    def execute(
        self,
        *,
        candidate: MarketCandidate,
        trace: ReasoningTrace,
        decision: TradeDecision,
        receipt_id: int | None = None,
    ) -> Position | None:
        if decision.action == "SKIP":
            return None

        order_id = self._submit_order(candidate=candidate, decision=decision)
        position = Position(
            market_id=candidate.market_id,
            side=decision.action,
            outcome="YES" if decision.action == "BUY_YES" else "NO",
            size_usdc=decision.size_usdc,
            entry_price=decision.limit_price,
            receipt_id=receipt_id,
            polymarket_order_id=order_id,
            status="open",
        )
        with Session() as session:
            session.add(position)
            session.flush()
        logger.info(
            "trader: %s %s @ %.4f, size=$%.2f (order %s)",
            decision.action,
            candidate.market_id,
            decision.limit_price,
            decision.size_usdc,
            order_id,
        )
        return position

    def _bankroll(self) -> float:
        if self.bankroll_provider is not None:
            try:
                value = self.bankroll_provider()
                return max(0.0, float(value))
            except Exception as exc:
                logger.warning("trader: bankroll provider failed (%s); falling back to mock", exc)
        return 1_000.0

    def _submit_order(self, *, candidate: MarketCandidate, decision: TradeDecision) -> str:
        if self.mock:
            return f"mock-{uuid.uuid4().hex[:12]}"
        payload = {
            "marketId": candidate.market_id,
            "side": decision.action,
            "size": decision.size_usdc,
            "price": decision.limit_price,
        }
        headers = {"Authorization": f"Bearer {os.getenv('POLYMARKET_API_KEY','')}"}
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(f"{self.polymarket_base}/orders", json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        return str(data.get("orderId") or data.get("id") or "unknown")
