"""resolver — back-fill `resolved_outcome` on receipts whose market has closed.

Polls Polymarket Gamma + Kalshi Trade API for each distinct unresolved market
the agent has priced. When the venue reports the market as closed and the
outcome is known, writes `resolved_at` + `resolved_outcome` (0.0 or 1.0) to
every receipt for that market. After enough markets resolve, `agent.calibration`
can compute Brier / reliability curves split by source.

Heuristics:

* **Polymarket** (Gamma): a market has `closed=true` plus `outcomePrices`. For
  binary outcomes (["Yes","No"]) the close price within 5% of 1.0 → YES,
  within 5% of 0.0 → NO, else ambiguous (skip).
* **Kalshi** (Trade API): a finalized binary market has
  `status in {"finalized", "settled", "determined"}` plus `result in {"yes", "no"}`.

Mock-friendly: if a fetch fails or returns nothing useful, the resolver logs a
warning and continues with the next market — never crashes the caller.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlalchemy import update

from storage.db import Receipt as ReceiptRow
from storage.db import Session

logger = logging.getLogger("rr.resolver")

POLYMARKET_GAMMA_MARKET = "https://gamma-api.polymarket.com/markets"
KALSHI_MARKET = "https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}"
RESOLVED_THRESHOLD = 0.95  # how close to 1.0 / 0.0 a close price must be to count
_KALSHI_FINAL_STATES = {"finalized", "settled", "determined"}


@dataclass(slots=True)
class ResolverReport:
    polled: int  # markets we tried
    newly_resolved_markets: int
    rows_updated: int  # receipt rows written


def _parse_outcome(market: dict) -> float | None:
    """Map a Polymarket market dict → YES probability at resolution, or None."""
    if not market.get("closed"):
        return None
    prices_raw = market.get("outcomePrices") or market.get("outcome_prices") or []
    try:
        # Gamma returns prices as JSON-encoded list-of-strings in a string, or list-of-strings.
        if isinstance(prices_raw, str):
            import json

            prices_raw = json.loads(prices_raw)
        prices = [float(p) for p in prices_raw]
    except (TypeError, ValueError):
        return None
    if not prices:
        return None
    yes_price = prices[0]
    if yes_price >= RESOLVED_THRESHOLD:
        return 1.0
    if yes_price <= (1 - RESOLVED_THRESHOLD):
        return 0.0
    return None  # too ambiguous (e.g. 0.5 / 0.5 — hasn't actually resolved cleanly)


def _fetch_market(client: httpx.Client, market_id: str, url: str = POLYMARKET_GAMMA_MARKET) -> dict | None:
    """Pull a single market by id from Gamma."""
    try:
        resp = client.get(url, params={"id": market_id}, timeout=10.0)
        if resp.status_code != 200:
            return None
        rows = resp.json()
    except Exception as exc:
        logger.debug("resolver: gamma fetch %s failed (%s)", market_id, exc)
        return None
    if isinstance(rows, list) and rows:
        return rows[0]
    if isinstance(rows, dict):
        return rows
    return None


def _fetch_kalshi(client: httpx.Client, ticker: str) -> dict | None:
    """Pull a single Kalshi market by ticker. Returns the inner `market` dict."""
    try:
        resp = client.get(KALSHI_MARKET.format(ticker=ticker), timeout=10.0)
        if resp.status_code != 200:
            return None
        body = resp.json() or {}
    except Exception as exc:
        logger.debug("resolver: kalshi fetch %s failed (%s)", ticker, exc)
        return None
    return body.get("market") if isinstance(body, dict) else None


def _parse_kalshi_outcome(market: dict) -> float | None:
    """Map a Kalshi market dict → YES probability at resolution, or None."""
    status = (market.get("status") or "").lower()
    if status not in _KALSHI_FINAL_STATES:
        return None
    result = (market.get("result") or "").lower()
    if result == "yes":
        return 1.0
    if result == "no":
        return 0.0
    return None


def resolve_open_markets(*, limit: int | None = None, base_url: str | None = None) -> ResolverReport:
    """Visit every distinct unresolved (market_id, source) pair and try to resolve it."""
    url = base_url or POLYMARKET_GAMMA_MARKET
    polled = 0
    newly_resolved = 0
    rows_updated_total = 0

    with Session() as session:
        # Distinct (market_id, source) pairs that have no resolved_outcome yet.
        rows = (
            session.execute(
                ReceiptRow.__table__.select()
                .with_only_columns(ReceiptRow.market_id, ReceiptRow.market_source)
                .distinct()
                .where(ReceiptRow.resolved_outcome.is_(None))
            )
            .all()
        )
    # Skip mock markets (prefixed `mock-`): they never resolve via either venue.
    pairs: list[tuple[str, str]] = [
        (m, s or "polymarket")
        for (m, s) in rows
        if m and not m.startswith("mock-")
    ]
    if limit is not None:
        pairs = pairs[:limit]

    if not pairs:
        return ResolverReport(polled=0, newly_resolved_markets=0, rows_updated=0)

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for market_id, source in pairs:
            polled += 1
            if source == "kalshi":
                data = _fetch_kalshi(client, market_id)
                outcome = _parse_kalshi_outcome(data) if data else None
            else:  # polymarket / unknown → use Gamma path
                data = _fetch_market(client, market_id, url=url)
                outcome = _parse_outcome(data) if data else None
            if outcome is None:
                continue
            with Session() as session:
                stmt = (
                    update(ReceiptRow)
                    .where(
                        ReceiptRow.market_id == market_id,
                        ReceiptRow.resolved_outcome.is_(None),
                    )
                    .values(resolved_at=datetime.now(UTC), resolved_outcome=outcome)
                )
                result = session.execute(stmt)
                rows_updated_total += result.rowcount or 0
            newly_resolved += 1
            logger.info(
                "resolver[%s]: market %s resolved → outcome=%s, rows updated=%s",
                source,
                market_id,
                outcome,
                rows_updated_total,
            )

    return ResolverReport(
        polled=polled,
        newly_resolved_markets=newly_resolved,
        rows_updated=rows_updated_total,
    )


def main() -> int:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)-7s %(message)s")
    from storage.db import init_db

    init_db()
    report = resolve_open_markets()
    logger.info(
        "resolver done: polled=%d newly_resolved=%d rows_updated=%d",
        report.polled,
        report.newly_resolved_markets,
        report.rows_updated,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
