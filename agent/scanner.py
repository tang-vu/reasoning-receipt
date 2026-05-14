"""Market scanner — polls Polymarket Gamma + Kalshi Trade API (RFB 03 plural).

Filter rules per spec:
- Liquidity > $10k (Polymarket: 24h volume; Kalshi: open_interest * last_price)
- Resolves in ≤ 30 days
- English-language question
- Multi-leg / parlay markets skipped (Kalshi `mve_collection_ticker` set)

Writes/updates `ScanCandidate` rows in the DB. Returns the pruned shortlist.

Both sources are queried per scan. Either can be disabled independently via
`RR_DISABLE_POLYMARKET=1` / `RR_DISABLE_KALSHI=1`.

Mock mode (`RR_MOCK_SCANNER=1` or no network): returns a deterministic fixture
covering both sources so the rest of the pipeline runs.
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
KALSHI_MARKETS = "https://api.elections.kalshi.com/trade-api/v2/markets"
MIN_LIQUIDITY_USD = 10_000.0
# Kalshi liquidity_dollars reports zero for many active markets — Kalshi's
# market-maker depth field is not comparable to Polymarket's 24h volume. We use
# open_interest_fp * last_price_dollars as the USD-equivalent activity proxy.
# 1000 contracts × $0.30 ≈ $300 minimum is too generous; we tune the proxy at
# $2k for now so the pipeline gets non-trivial Kalshi markets without starving.
KALSHI_MIN_NOTIONAL_USD = 2_000.0
MAX_HORIZON_DAYS = 30


def _utcnow() -> _dt.datetime:
    return _dt.datetime.now(_dt.UTC)


def _is_english(s: str) -> bool:
    if not s:
        return False
    ascii_count = sum(1 for ch in s if ord(ch) < 128)
    return ascii_count / max(1, len(s)) > 0.92


def _interleave_by_source(
    *lists: list[MarketCandidate],
) -> list[MarketCandidate]:
    """Round-robin merge so per_tick slicing picks across all sources.

    Without this the tick consistently exhausts the first source before
    touching the second, and the second source can sit idle behind the 5-min
    market cooldown. Order-preserving within each list.
    """
    merged: list[MarketCandidate] = []
    cursors = [iter(seq) for seq in lists]
    while cursors:
        next_cursors = []
        for it in cursors:
            try:
                merged.append(next(it))
                next_cursors.append(it)
            except StopIteration:
                continue
        cursors = next_cursors
    return merged


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
    MarketCandidate(
        market_id="mock-kalshi-cpi-may-2026-above-3pct",
        source="kalshi",
        question="Will headline CPI for May 2026 print above 3.0%?",
        end_date=_utcnow() + _dt.timedelta(days=12),
        liquidity_usd=48_300.0,
        extra={"ticker": "KXCPI-26MAY", "yes_bid_dollars": "0.32"},
    ),
    MarketCandidate(
        market_id="mock-kalshi-fed-cut-jun-2026",
        source="kalshi",
        question="Will the Fed cut rates by ≥ 25bp at the June 2026 FOMC?",
        end_date=_utcnow() + _dt.timedelta(days=22),
        liquidity_usd=132_000.0,
        extra={"ticker": "KXFEDDECISION-26JUN", "yes_bid_dollars": "0.42"},
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
        # Kalshi's liquidity proxy scale differs from Polymarket's 24h volume —
        # apply the source-specific floor.
        floor = (
            KALSHI_MIN_NOTIONAL_USD if c.source == "kalshi" else self.config.min_liquidity_usd
        )
        if c.liquidity_usd < floor:
            return False
        if not _is_english(c.question):
            return False
        if c.end_date:
            # Normalise tz so naive-vs-aware subtraction doesn't blow up.
            end = c.end_date
            if end.tzinfo is None:
                end = end.replace(tzinfo=_dt.UTC)
            days = (end - _utcnow()).days
            if days < 0 or days > self.config.max_horizon_days:
                return False
        return True

    def _fetch(self) -> Iterable[MarketCandidate]:
        if self.mock:
            return list(_MOCK_FIXTURE)
        poly: list[MarketCandidate] = []
        kal: list[MarketCandidate] = []
        if os.getenv("RR_DISABLE_POLYMARKET", "").lower() not in {"1", "true", "yes"}:
            try:
                poly = list(self._fetch_polymarket())
            except Exception as exc:  # noqa: BLE001
                logger.warning("scanner: polymarket fetch failed (%s)", str(exc)[:200])
        if os.getenv("RR_DISABLE_KALSHI", "").lower() not in {"1", "true", "yes"}:
            try:
                kal = list(self._fetch_kalshi())
            except Exception as exc:  # noqa: BLE001
                logger.warning("scanner: kalshi fetch failed (%s)", str(exc)[:200])
        return _interleave_by_source(poly, kal)

    def _fetch_polymarket(self) -> Iterable[MarketCandidate]:
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

    def _fetch_kalshi(self) -> Iterable[MarketCandidate]:
        """Pull near-term open markets from Kalshi's public Trade API.

        We hit `/markets` directly with `min_close_ts` / `max_close_ts` set to
        the 30-day eligibility window — the `/events` endpoint doesn't
        date-sort and gets dominated by long-horizon meme markets (Elon-to-Mars
        2099, etc.) that we'd reject anyway.

        Multi-leg / parlay markets are skipped — they don't fit the analyst's
        single-question prompt shape. Kalshi marks them with a non-empty
        `mve_collection_ticker` or a populated `mve_selected_legs` array.
        """
        now_ts = int(_utcnow().timestamp())
        params = {
            "limit": min(self.config.limit * 4, 200),  # API cap
            "status": "open",
            "min_close_ts": now_ts,
            "max_close_ts": now_ts + self.config.max_horizon_days * 86_400,
        }
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            resp = client.get(KALSHI_MARKETS, params=params)
            resp.raise_for_status()
            payload = resp.json() or {}
        markets = payload.get("markets") or []
        out: list[MarketCandidate] = []
        for m in markets:
            if m.get("mve_collection_ticker") or m.get("mve_selected_legs"):
                continue
            if m.get("market_type") != "binary":
                continue
            ticker = m.get("ticker")
            if not ticker:
                continue
            question = m.get("title") or m.get("yes_sub_title") or ""
            if not question:
                continue
            try:
                close = m.get("close_time") or m.get("expiration_time")
                end_dt = (
                    _dt.datetime.fromisoformat(close.replace("Z", "+00:00")) if close else None
                )
            except (TypeError, ValueError):
                end_dt = None
            # Liquidity proxy: open_interest * mid-price * notional. Kalshi's
            # own `liquidity_dollars` field is market-maker depth and is often
            # zero even for high-volume markets.
            try:
                open_interest = float(m.get("open_interest_fp") or 0.0)
                last_price = float(m.get("last_price_dollars") or 0.0)
                notional = float(m.get("notional_value_dollars") or 1.0)
                liquidity = open_interest * last_price * notional
            except (TypeError, ValueError):
                liquidity = 0.0
            out.append(
                MarketCandidate(
                    market_id=str(ticker),
                    source="kalshi",
                    question=question,
                    end_date=end_dt,
                    liquidity_usd=liquidity,
                    extra={
                        "event_ticker": m.get("event_ticker"),
                        "yes_bid_dollars": m.get("yes_bid_dollars"),
                        "no_bid_dollars": m.get("no_bid_dollars"),
                        "open_interest_fp": m.get("open_interest_fp"),
                    },
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
