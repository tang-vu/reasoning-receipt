"""x402 paywall — minimal implementation against Circle Nanopayments.

Flow:
1. Unpaid request → respond 402 with `Accept-Payment` JSON describing the
   amount, asset, recipient, and a server-side challenge nonce.
2. Client signs an EIP-712 payment payload and retries with `X-PAYMENT` header.
3. Server verifies the payment via the facilitator and (mock or real) settles
   it on Arc, then proceeds to the handler.

The handler attaches the settlement tx hash and payer address to the request
state so the route can include them in the receipt.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass

import httpx
from fastapi import HTTPException, Request, Response

DEFAULT_PRICE_USDC = 0.01
DEFAULT_ASSET = "USDC"
DEFAULT_NETWORK = "arc-testnet"


@dataclass(slots=True)
class PaymentChallenge:
    """Server-issued challenge embedded in the 402 response."""

    nonce: str
    issued_at: int
    expires_at: int
    price_usdc: float
    asset: str
    network: str
    receiver: str
    resource: str


@dataclass(slots=True)
class PaymentEvidence:
    """Verified payment data attached to `request.state.x402`."""

    payer_address: str
    tx_hash: str
    settled_amount_usdc: float
    facilitator: str
    is_mock: bool


class X402Paywall:
    """Stateless paywall — issues challenges, verifies payments, settles."""

    def __init__(
        self,
        *,
        price_usdc: float = DEFAULT_PRICE_USDC,
        asset: str = DEFAULT_ASSET,
        network: str = DEFAULT_NETWORK,
        receiver_address: str | None = None,
        facilitator_url: str | None = None,
        signing_secret: str | None = None,
        mock: bool | None = None,
    ) -> None:
        self.price_usdc = price_usdc
        self.asset = asset
        self.network = network
        self.receiver_address = receiver_address or os.getenv(
            "X402_RECEIVER_ADDRESS",
            "0x" + "0" * 40,
        )
        self.facilitator_url = facilitator_url or os.getenv("X402_FACILITATOR_URL", "")
        env_mock = os.getenv("RR_MOCK_X402", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        if not self.facilitator_url:
            self.mock = True
        self.signing_secret = signing_secret or os.getenv(
            "X402_SIGNING_SECRET",
            "rr-x402-dev-secret",
        )

    # ------ challenge issuance ------

    def issue_challenge(self, resource: str, *, ttl_seconds: int = 300) -> PaymentChallenge:
        now = int(time.time())
        nonce = secrets.token_hex(16)
        return PaymentChallenge(
            nonce=nonce,
            issued_at=now,
            expires_at=now + ttl_seconds,
            price_usdc=self.price_usdc,
            asset=self.asset,
            network=self.network,
            receiver=self.receiver_address,
            resource=resource,
        )

    def challenge_response(self, resource: str) -> Response:
        challenge = self.issue_challenge(resource)
        body = {
            "x402_version": 1,
            "error": "payment_required",
            "accepts": [
                {
                    "scheme": "exact",
                    "network": challenge.network,
                    "asset": challenge.asset,
                    "amount": f"{challenge.price_usdc:.6f}",
                    "recipient": challenge.receiver,
                    "resource": challenge.resource,
                    "nonce": challenge.nonce,
                    "expires_at": challenge.expires_at,
                    "signature_alg": "EIP-712",
                }
            ],
        }
        signed = self._sign_challenge(challenge)
        headers = {
            "Accept-Payment": json.dumps(body, separators=(",", ":")),
            "X-Payment-Challenge": signed,
            "Cache-Control": "no-store",
        }
        return Response(
            content=json.dumps(body),
            status_code=402,
            media_type="application/json",
            headers=headers,
        )

    # ------ verification ------

    def parse_payment_header(self, raw: str) -> dict:
        try:
            decoded = base64.b64decode(raw.encode("ascii"), validate=True)
            return json.loads(decoded.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid X-PAYMENT header: {exc}") from exc

    def verify(self, request: Request, payment_header: str) -> PaymentEvidence:
        payload = self.parse_payment_header(payment_header)

        # Replay/nonce check.
        challenge_token = request.headers.get("x-payment-challenge", "")
        if not challenge_token or not self._verify_challenge(challenge_token, payload):
            raise HTTPException(status_code=402, detail="challenge invalid or expired")

        # Pricing.
        try:
            paid = float(payload.get("amount", 0))
        except (TypeError, ValueError):
            paid = 0.0
        if paid + 1e-9 < self.price_usdc:
            raise HTTPException(status_code=402, detail="insufficient payment")

        # Settlement.
        if self.mock:
            digest = hashlib.sha256(
                (payload.get("payer", "") + payload.get("nonce", "") + str(time.time_ns())).encode()
            ).hexdigest()
            return PaymentEvidence(
                payer_address=payload.get("payer", "0x" + "0" * 40),
                tx_hash="0x" + digest,
                settled_amount_usdc=paid,
                facilitator="mock",
                is_mock=True,
            )

        with httpx.Client(timeout=15.0) as client:
            resp = client.post(
                f"{self.facilitator_url.rstrip('/')}/settle",
                json={
                    "scheme": "exact",
                    "network": self.network,
                    "payload": payload,
                    "resource": payload.get("resource", ""),
                },
            )
            if resp.status_code >= 400:
                raise HTTPException(status_code=402, detail=f"facilitator rejected: {resp.text}")
            data = resp.json()
        return PaymentEvidence(
            payer_address=str(data.get("payer", payload.get("payer", ""))),
            tx_hash=str(data.get("tx_hash") or data.get("transactionHash") or "0x"),
            settled_amount_usdc=paid,
            facilitator=self.facilitator_url,
            is_mock=False,
        )

    # ------ HMAC challenge signing (keeps state stateless) ------

    _MAC_LEN = 32  # sha256 digest

    def _sign_challenge(self, challenge: PaymentChallenge) -> str:
        body = json.dumps(asdict(challenge), sort_keys=True, separators=(",", ":")).encode()
        mac = hmac.new(self.signing_secret.encode(), body, hashlib.sha256).digest()
        # Pack as raw bytes: [body || mac]; mac is fixed length so the boundary is unambiguous.
        return base64.urlsafe_b64encode(body + mac).decode("ascii")

    def _verify_challenge(self, token: str, payment_payload: dict) -> bool:
        try:
            raw = base64.urlsafe_b64decode(token.encode("ascii"))
            if len(raw) <= self._MAC_LEN:
                return False
            body, mac = raw[: -self._MAC_LEN], raw[-self._MAC_LEN :]
            expected = hmac.new(self.signing_secret.encode(), body, hashlib.sha256).digest()
            if not hmac.compare_digest(mac, expected):
                return False
            challenge = json.loads(body.decode("utf-8"))
        except Exception:
            return False
        if challenge.get("nonce") != payment_payload.get("nonce"):
            return False
        if int(challenge.get("expires_at", 0)) < int(time.time()):
            return False
        return challenge.get("resource") == payment_payload.get("resource")
