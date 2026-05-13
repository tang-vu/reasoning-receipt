"""resolver — back-fill `resolved_outcome` on receipts whose market has closed.

Polls Polymarket Gamma for each distinct unresolved market the agent has
priced. When Gamma reports the market as closed and the outcome is known,
writes `resolved_at` + `resolved_outcome` (0.0 or 1.0) to every receipt for
that market. After enough markets resolve, `agent.calibration` can compute
Brier / reliability curves.

Heuristic for the YES probability at resolution:

  - Polymarket Gamma `/markets` returns `outcomes` (list of label strings)
    and `outcomePrices` (matching list of stringified close prices in [0, 1]).
  - For a binary market with outcomes = ["Yes", "No"]:
      * If `closed` is true AND `outcomePrices[0]` parses to ~1.0 → YES
      * If `closed` is true AND `outcomePrices[0]` parses to ~0.0 → NO
      * Anything else is treated as "not yet conclusively resolved".

Mock-friendly: if the Polymarket fetch fails or returns nothing useful, the
resolver logs a warning and returns 0 — never crashes the caller.
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
RESOLVED_THRESHOLD = 0.95  # how close to 1.0 / 0.0 a close price must be to count


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


def resolve_open_markets(*, limit: int | None = None, base_url: str | None = None) -> ResolverReport:
    """Visit every distinct unresolved market in the DB and try to resolve it."""
    url = base_url or POLYMARKET_GAMMA_MARKET
    polled = 0
    newly_resolved = 0
    rows_updated_total = 0

    with Session() as session:
        # Distinct markets that have no resolved_outcome anywhere yet.
        rows = (
            session.execute(
                ReceiptRow.__table__.select()
                .with_only_columns(ReceiptRow.market_id)
                .distinct()
                .where(ReceiptRow.resolved_outcome.is_(None))
            )
            .scalars()
            .all()
        )
    # Skip mock markets (prefixed `mock-`): they never resolve via Gamma.
    market_ids = [m for m in rows if m and not m.startswith("mock-")]
    if limit is not None:
        market_ids = market_ids[:limit]

    if not market_ids:
        return ResolverReport(polled=0, newly_resolved_markets=0, rows_updated=0)

    with httpx.Client(timeout=15.0, follow_redirects=True) as client:
        for market_id in market_ids:
            polled += 1
            data = _fetch_market(client, market_id, url=url)
            if data is None:
                continue
            outcome = _parse_outcome(data)
            if outcome is None:
                continue
            with Session() as session:
                stmt = (
                    update(ReceiptRow)
                    .where(ReceiptRow.market_id == market_id, ReceiptRow.resolved_outcome.is_(None))
                    .values(resolved_at=datetime.now(UTC), resolved_outcome=outcome)
                )
                result = session.execute(stmt)
                rows_updated_total += result.rowcount or 0
            newly_resolved += 1
            logger.info(
                "resolver: market %s resolved → outcome=%s, rows updated=%s",
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
