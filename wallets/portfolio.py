"""Portfolio accounting — bankroll, PnL, position summary.

PnL = current bankroll + unrealized position MTM − baseline_bankroll.
Baseline is fixed at the first observation (or `RR_BASELINE_USDC`).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select

from storage.db import Position, Session

from .circle import CircleClient, WalletInfo

_BASELINE_FILE_KEY = "portfolio_baseline"


@dataclass(slots=True)
class PortfolioSnapshot:
    wallet: WalletInfo
    baseline_usdc: float
    cash_usdc: float
    unrealized_pnl_usdc: float
    realized_pnl_usdc: float
    open_positions: int
    closed_positions: int
    total_pnl_usdc: float
    pnl_pct: float
    observed_at: datetime


class Portfolio:
    """Read-only accounting over the portfolio wallet + SQLite positions."""

    def __init__(
        self,
        *,
        circle: CircleClient | None = None,
        portfolio_wallet_id: str | None = None,
    ) -> None:
        self.circle = circle or CircleClient()
        self.portfolio_wallet_id = (
            portfolio_wallet_id
            or os.getenv("CIRCLE_PORTFOLIO_WALLET_ID")
            or "rr-portfolio-mock"
        )

    def snapshot(self) -> PortfolioSnapshot:
        wallet = self.circle.get_wallet(self.portfolio_wallet_id)
        baseline = self._baseline(wallet.balance_usdc)
        realized, unrealized, open_n, closed_n = self._position_pnl()
        total = (wallet.balance_usdc + unrealized) - baseline
        pct = (total / baseline * 100.0) if baseline > 0 else 0.0
        return PortfolioSnapshot(
            wallet=wallet,
            baseline_usdc=baseline,
            cash_usdc=wallet.balance_usdc,
            unrealized_pnl_usdc=unrealized,
            realized_pnl_usdc=realized,
            open_positions=open_n,
            closed_positions=closed_n,
            total_pnl_usdc=total,
            pnl_pct=pct,
            observed_at=datetime.now(UTC),
        )

    def bankroll(self) -> float:
        return self.circle.get_wallet(self.portfolio_wallet_id).balance_usdc

    def _baseline(self, current_balance: float) -> float:
        env = os.getenv("RR_BASELINE_USDC")
        if env:
            try:
                return float(env)
            except ValueError:
                pass
        return max(1.0, current_balance)

    def _position_pnl(self) -> tuple[float, float, int, int]:
        realized = 0.0
        unrealized = 0.0
        open_n = 0
        closed_n = 0
        with Session() as session:
            for row in session.execute(select(Position)).scalars():
                if row.status == "open":
                    open_n += 1
                    mtm = row.entry_price  # MTM proxy; CLOB integration is a Phase-3 extension
                    unrealized += (mtm - row.entry_price) * row.size_usdc
                else:
                    closed_n += 1
                    realized += row.realized_pnl_usdc
        return realized, unrealized, open_n, closed_n
