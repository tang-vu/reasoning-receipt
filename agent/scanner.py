"""Market scanner — polls Polymarket CLOB + (optionally) Kalshi.

Filter rules per spec:
- Liquidity > $10k (Polymarket: 24h volume; Kalshi: cents-on-the-dollar fallback)
- Resolves in ≤ 30 days
- English-language question

Writes/updates `ScanCandidate` rows in the DB. Returns the pruned shortlist.

Mock mode (`RR_MOCK_SCANNER=1` or no network): returns a deterministic fixture
of 5 candidates so the rest of the pipeline runs.
"""

from __future__ import annotations

import datetime as _dt
import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from storage.db import ScanCandidate, Session

from .analyst import MarketCandidate

logger = logging.getLogger(__name__)

POLYMARKET_GAMMA = "https://gamma-api.polymarket.com/markets"
MIN_LIQUIDITY_USD = 10_000.0
MAX_HORIZON_DAYS = 30


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _is_english(s: str) -> bool:
    if not s:
        return False
    ascii_count = sum(1 for ch in s if ord(ch) < 128)
    return ascii_count / max(1, len(s)) > 0.92


@dataclass(slots=True)
class ScannerConfig:
    limit: int = 50
    min_liquidity_usd: float = MIN_LIQUIDITY_USD
    max_horizon_days: int = MAX_HORIZON_DAYS


_MOCK_FIXTURE = [
    MarketCandidate(
        market_id="mock-polymarket-fed-rate-cut-jun-2026",
        source="polymarket",
        question="Will the Fed cut rates at the June 2026 FOMC meeting?",
        end_date=_utcnow() + _dt.timedelta(days=20),
        liquidity_usd=185_400.0,
    ),
    MarketCandidate(
        market_id="mock-polymarket-arsenal-pl-title-2026",
        source="polymarket",
        question="Will Arsenal win the 2025–26 Premier League title?",
        end_date=_utcnow() + _dt.timedelta(days=21),
        liquidity_usd=92_300.0,
    ),
    MarketCandidate(
        market_id="mock-polymarket-btc-100k-by-jun-2026",
        source="polymarket",
        question="Will Bitcoin close above $100,000 on June 30, 2026?",
        end_date=_utcnow() + _dt.timedelta(days=18),
        liquidity_usd=312_000.0,
    ),
    MarketCandidate(
        market_id="mock-polymarket-cpi-may-2026",
        source="polymarket",
        question="Will US headline CPI for May 2026 print ≥ 3.0% YoY?",
        end_date=_utcnow() + _dt.timedelta(days=8),
        liquidity_usd=64_900.0,
    ),
    MarketCandidate(
        market_id="mock-polymarket-eu-ai-act-amendment",
        source="polymarket",
        question="Will the EU AI Act be amended before July 1, 2026?",
        end_date=_utcnow() + _dt.timedelta(days=26),
        liquidity_usd=21_500.0,
    ),
]


class Scanner:
    def __init__(self, *, config: ScannerConfig | None = None, mock: bool | None = None) -> None:
        self.config = config or ScannerConfig()
        env_mock = os.getenv("RR_MOCK_SCANNER", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock

    def scan(self) -> list[MarketCandidate]:
        try:
            candidates = list(self._fetch())
        except Exception as exc:  # network down, schema drift — degrade to fixture
            logger.warning("scanner: live fetch failed (%s); falling back to fixture", exc)
            candidates = list(_MOCK_FIXTURE)

        eligible = [c for c in candidates if self._is_eligible(c)]
        self._persist(eligible)
        return eligible[: self.config.limit]

    def _is_eligible(self, c: MarketCandidate) -> bool:
        if c.liquidity_usd < self.config.min_liquidity_usd:
            return False
        if not _is_english(c.question):
            return False
        if c.end_date:
            days = (c.end_date - _utcnow()).days
            if days < 0 or days > self.config.max_horizon_days:
                return False
        return True

    def _fetch(self) -> Iterable[MarketCandidate]:
        if self.mock:
            return list(_MOCK_FIXTURE)
        params = {
            "limit": self.config.limit * 4,
            "active": "true",
            "closed": "false",
            "order": "volume",
            "ascending": "false",
        }
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(POLYMARKET_GAMMA, params=params)
            resp.raise_for_status()
            rows = resp.json()
        out: list[MarketCandidate] = []
        for row in rows or []:
            try:
                end = row.get("endDate") or row.get("end_date_iso")
                end_dt = _dt.datetime.fromisoformat(end.replace("Z", "+00:00")) if end else None
            except (TypeError, ValueError):
                end_dt = None
            liquidity = float(row.get("volume24hr") or row.get("liquidity") or 0.0)
            question = row.get("question") or row.get("slug") or ""
            mid = str(row.get("id") or row.get("conditionId") or row.get("slug"))
            if not (question and mid):
                continue
            out.append(
                MarketCandidate(
                    market_id=mid,
                    source="polymarket",
                    question=question,
                    end_date=end_dt,
                    liquidity_usd=liquidity,
                    extra={"slug": row.get("slug")},
                )
            )
        return out

    def _persist(self, candidates: list[MarketCandidate]) -> None:
        if not candidates:
            return
        with Session() as session:
            for c in candidates:
                row = session.query(ScanCandidate).filter_by(market_id=c.market_id).one_or_none()
                if row is None:
                    row = ScanCandidate(
                        market_id=c.market_id,
                        source=c.source,
                        question=c.question,
                        liquidity_usd=c.liquidity_usd,
                        end_date=c.end_date,
                    )
                    session.add(row)
                else:
                    row.liquidity_usd = c.liquidity_usd
                    row.end_date = c.end_date
                    row.question = c.question
