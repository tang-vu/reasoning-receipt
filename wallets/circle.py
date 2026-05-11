"""Circle developer-controlled wallet client.

Real mode: thin wrapper around the Circle Wallets REST API for wallet-set
provisioning, balance lookups, and USDC transfers. Mock mode returns
deterministic synthetic wallets so the rest of the system runs offline.

Spec calls for TWO distinct wallets:
  - portfolio wallet — holds USDC, places Polymarket trades, receives x402 fees
  - consumer wallet  — pays the oracle for its own queries (drives volume)

Both are addressable by their Circle wallet id (`CIRCLE_PORTFOLIO_WALLET_ID`,
`CIRCLE_CONSUMER_WALLET_ID`).
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

CIRCLE_BASE = "https://api.circle.com/v1/w3s"


@dataclass(slots=True)
class WalletInfo:
    id: str
    address: str
    blockchain: str
    balance_usdc: float
    is_mock: bool


def _mock_address(seed: str) -> str:
    digest = hashlib.sha256(seed.encode()).hexdigest()
    return "0x" + digest[:40]


class CircleClient:
    """Minimal Circle Wallets client (developer-controlled flow)."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        entity_secret: str | None = None,
        wallet_set_id: str | None = None,
        mock: bool | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("CIRCLE_API_KEY")
        self.entity_secret = entity_secret or os.getenv("CIRCLE_ENTITY_SECRET")
        self.wallet_set_id = wallet_set_id or os.getenv("CIRCLE_WALLET_SET_ID")
        env_mock = os.getenv("RR_MOCK_CIRCLE", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        if not (self.api_key and self.entity_secret):
            self.mock = True

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def get_wallet(self, wallet_id: str) -> WalletInfo:
        if self.mock:
            return WalletInfo(
                id=wallet_id,
                address=_mock_address(wallet_id),
                blockchain="ARC-TESTNET",
                balance_usdc=1_000.0 if "portfolio" in wallet_id else 25.0,
                is_mock=True,
            )
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{CIRCLE_BASE}/wallets/{wallet_id}", headers=self._headers())
            resp.raise_for_status()
            wallet = resp.json().get("data", {}).get("wallet", {})
            bal_resp = client.get(
                f"{CIRCLE_BASE}/wallets/{wallet_id}/balances",
                headers=self._headers(),
            )
            bal_resp.raise_for_status()
            tokens = bal_resp.json().get("data", {}).get("tokenBalances", [])
        usdc = 0.0
        for tb in tokens:
            if (tb.get("token", {}).get("symbol", "")).upper() == "USDC":
                try:
                    usdc = float(tb.get("amount", 0.0))
                except (TypeError, ValueError):
                    usdc = 0.0
        return WalletInfo(
            id=wallet.get("id", wallet_id),
            address=wallet.get("address", ""),
            blockchain=wallet.get("blockchain", "ARC-TESTNET"),
            balance_usdc=usdc,
            is_mock=False,
        )

    def transfer_usdc(self, *, from_wallet_id: str, to_address: str, amount_usdc: float) -> str:
        if self.mock:
            return f"mock-tx-{uuid.uuid4().hex[:16]}"
        payload = {
            "idempotencyKey": str(uuid.uuid4()),
            "entitySecretCiphertext": self.entity_secret,
            "amounts": [str(round(amount_usdc, 6))],
            "destinationAddress": to_address,
            "tokenId": os.getenv("CIRCLE_USDC_TOKEN_ID", ""),
            "walletId": from_wallet_id,
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{CIRCLE_BASE}/developer/transactions/transfer",
                headers=self._headers(),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json().get("data", {})
        return str(data.get("id") or "unknown")

    def faucet_usdc(self, *, wallet_id: str, amount_usdc: float = 10.0) -> bool:
        """Best-effort testnet faucet request. No-op in mock mode."""
        if self.mock:
            logger.info("circle: mock faucet credited %.2f USDC to %s", amount_usdc, wallet_id)
            return True
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(
                    f"{CIRCLE_BASE}/faucet/drips",
                    headers=self._headers(),
                    json={"blockchain": "ARC-TESTNET", "walletId": wallet_id},
                )
                return resp.status_code < 300
        except Exception as exc:
            logger.warning("circle: faucet request failed (%s)", exc)
            return False
