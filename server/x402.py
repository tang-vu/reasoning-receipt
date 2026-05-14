"""x402 paywall — Circle Gateway / Nanopayments spec.

Emits **x402Version 2** challenges per Circle's Gateway-batched protocol:

  HTTP/1.1 402 Payment Required
  PAYMENT-REQUIRED: <base64(JSON)>
  Content-Type: application/json

  {
    "x402Version": 2,
    "resource": { "url": "/price/<id>", "description": "...", "mimeType": "application/json" },
    "accepts": [
      {
        "scheme": "exact",
        "network": "eip155:5042002",       // CAIP-2 for Arc Testnet
        "asset":   "0x36000000…",           // USDC on Arc
        "amount":  "10000",                 // micro-units (0.01 USDC at 6dp)
        "maxTimeoutSeconds": 604900,        // ≥ 7 days
        "payTo":   "0xbc6f…",               // portfolio wallet
        "extra": {
          "name": "GatewayWalletBatched",   // EIP-712 domain name
          "version": "1",
          "verifyingContract": "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"  // Arc-Testnet Gateway Wallet
        }
      }
    ]
  }

Clients sign an **EIP-3009 TransferWithAuthorization** typed-data structure
using `extra` as the EIP-712 domain. The signed payload comes back as the
`X-PAYMENT` header (base64-encoded JSON). The server forwards it to Circle's
facilitator `POST /v1/settle`, which executes the gasless USDC transfer on
Arc and returns a settlement tx hash.

Mock mode (`RR_MOCK_X402=1` or missing facilitator) keeps the spec-correct
challenge shape but short-circuits the settlement step with a synthetic
tx hash. Lets the agent's own consumer wallet drive volume without round-
tripping Circle's facilitator for every receipt.
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

# Per-call price, in micro-USDC (USDC has 6 decimals).
DEFAULT_PRICE_MICRO_USDC = 10_000  # 0.01 USDC

# Arc Testnet via CAIP-2 + addresses (verified from circlefin-skills docs).
DEFAULT_CHAIN_ID = 5042002
DEFAULT_NETWORK_CAIP2 = f"eip155:{DEFAULT_CHAIN_ID}"
DEFAULT_USDC_ADDRESS_ARC_TESTNET = "0x3600000000000000000000000000000000000000"
# Gateway Wallet contract is the EIP-712 verifyingContract for the
# TransferWithAuthorization domain. Same address across all Circle testnets.
GATEWAY_WALLET_TESTNET = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9"

# Validity window for an EIP-3009 authorization (seconds). Circle requires
# ≥ 7 days; we add a small buffer.
DEFAULT_MAX_TIMEOUT_S = 7 * 24 * 60 * 60 + 100

# Circle facilitator default (testnet) — Gateway Nanopayments.
DEFAULT_FACILITATOR_URL = "https://gateway-api-testnet.circle.com"


@dataclass(slots=True)
class PaymentChallenge:
    """Server-side bookkeeping for an issued 402 challenge."""

    nonce: str
    issued_at: int
    expires_at: int
    amount_micro_usdc: int
    asset: str
    network: str
    receiver: str
    resource: str
    verifying_contract: str


@dataclass(slots=True)
class PaymentEvidence:
    """Verified-payment data attached to `request.state.x402`."""

    payer_address: str
    tx_hash: str
    settled_amount_micro_usdc: int
    facilitator: str
    is_mock: bool


class X402Paywall:
    """Issues x402-v2 PAYMENT-REQUIRED challenges, verifies + settles X-PAYMENT."""

    _MAC_LEN = 32  # sha256 digest length

    def __init__(
        self,
        *,
        price_micro_usdc: int = DEFAULT_PRICE_MICRO_USDC,
        chain_id: int = DEFAULT_CHAIN_ID,
        asset_address: str = DEFAULT_USDC_ADDRESS_ARC_TESTNET,
        verifying_contract: str = GATEWAY_WALLET_TESTNET,
        receiver_address: str | None = None,
        facilitator_url: str | None = None,
        signing_secret: str | None = None,
        mock: bool | None = None,
    ) -> None:
        self.price_micro_usdc = price_micro_usdc
        self.chain_id = chain_id
        self.network = f"eip155:{chain_id}"
        self.asset_address = asset_address
        self.verifying_contract = verifying_contract
        self.receiver_address = receiver_address or os.getenv(
            "X402_RECEIVER_ADDRESS",
            "0x" + "0" * 40,
        )
        self.facilitator_url = (
            facilitator_url
            or os.getenv("X402_FACILITATOR_URL", "")
            or DEFAULT_FACILITATOR_URL
        )

        env_mock = os.getenv("RR_MOCK_X402", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        # The mock branch is also forced when the facilitator URL is empty.
        if not self.facilitator_url:
            self.mock = True

        self.signing_secret = signing_secret or os.getenv(
            "X402_SIGNING_SECRET",
            "rr-x402-dev-secret",
        )

    # ----- challenge issuance ---------------------------------------------

    def issue_challenge(self, resource: str, *, ttl_seconds: int = DEFAULT_MAX_TIMEOUT_S) -> PaymentChallenge:
        now = int(time.time())
        nonce = "0x" + secrets.token_hex(32)  # EIP-3009 nonces are bytes32
        return PaymentChallenge(
            nonce=nonce,
            issued_at=now,
            expires_at=now + ttl_seconds,
            amount_micro_usdc=self.price_micro_usdc,
            asset=self.asset_address,
            network=self.network,
            receiver=self.receiver_address,
            resource=resource,
            verifying_contract=self.verifying_contract,
        )

    def challenge_body(self, challenge: PaymentChallenge) -> dict:
        """Build the Circle x402-v2 spec body — what goes in PAYMENT-REQUIRED."""
        return {
            "x402Version": 2,
            "resource": {
                "url": challenge.resource,
                "description": "ReasoningReceipt — prediction-market oracle response with hashed trace",
                "mimeType": "application/json",
            },
            "accepts": [
                {
                    "scheme": "exact",
                    "network": challenge.network,
                    "asset": challenge.asset,
                    "amount": str(challenge.amount_micro_usdc),
                    "maxTimeoutSeconds": challenge.expires_at - challenge.issued_at,
                    "payTo": challenge.receiver,
                    "nonce": challenge.nonce,
                    "extra": {
                        "name": "GatewayWalletBatched",
                        "version": "1",
                        "verifyingContract": challenge.verifying_contract,
                    },
                }
            ],
        }

    def challenge_response(self, resource: str) -> Response:
        challenge = self.issue_challenge(resource)
        body = self.challenge_body(challenge)
        body_bytes = json.dumps(body, separators=(",", ":")).encode("utf-8")
        # Sign the challenge so we can verify nonce/resource/expiry on the
        # paired X-PAYMENT request without keeping server-side state.
        signed = self._sign_challenge(challenge)
        headers = {
            # Circle-spec header — base64-encoded body.
            "PAYMENT-REQUIRED": base64.b64encode(body_bytes).decode("ascii"),
            # Backwards-compat header for our earlier clients (raw JSON).
            "Accept-Payment": json.dumps(body, separators=(",", ":")),
            # Stateless challenge token bound to nonce + resource + expiry.
            "X-Payment-Challenge": signed,
            "Cache-Control": "no-store",
        }
        return Response(
            content=json.dumps(body),
            status_code=402,
            media_type="application/json",
            headers=headers,
        )

    # ----- verification ---------------------------------------------------

    def parse_payment_header(self, raw: str) -> dict:
        try:
            decoded = base64.b64decode(raw.encode("ascii"), validate=True)
            return json.loads(decoded.decode("utf-8"))
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid X-PAYMENT header: {exc}"
            ) from exc

    def verify(self, request: Request, payment_header: str) -> PaymentEvidence:
        payload = self.parse_payment_header(payment_header)

        # Replay protection via the HMAC-signed challenge token (covers nonce + resource + expiry).
        challenge_token = request.headers.get("x-payment-challenge", "")
        if not challenge_token or not self._verify_challenge(challenge_token, payload):
            raise HTTPException(status_code=402, detail="challenge invalid or expired")

        # Amount check — accepts either Circle's "payload.value" / "amount" or our legacy "amount".
        amount_str = (
            payload.get("amount")
            or payload.get("value")
            or payload.get("payload", {}).get("value")
            or "0"
        )
        try:
            paid_micro = int(amount_str)
        except (TypeError, ValueError):
            try:
                paid_micro = int(round(float(amount_str) * 1_000_000))
            except (TypeError, ValueError):
                paid_micro = 0
        if paid_micro + 1 < self.price_micro_usdc:
            raise HTTPException(
                status_code=402, detail=f"insufficient payment: {paid_micro} < {self.price_micro_usdc}"
            )

        payer = (
            payload.get("payer")
            or payload.get("from")
            or payload.get("payload", {}).get("from")
            or "0x" + "0" * 40
        )

        # Mock settlement: no Circle round-trip.
        if self.mock:
            digest = hashlib.sha256(
                (str(payer) + str(payload.get("nonce", "")) + str(time.time_ns())).encode()
            ).hexdigest()
            return PaymentEvidence(
                payer_address=str(payer),
                tx_hash="0x" + digest,
                settled_amount_micro_usdc=paid_micro,
                facilitator="mock",
                is_mock=True,
            )

        # Real settlement against Circle's Gateway facilitator.
        # `/v1/settle` accepts the full x402-v2 settlement request shape.
        settle_url = f"{self.facilitator_url.rstrip('/')}/v1/settle"
        requirements = {
            "scheme": "exact",
            "network": self.network,
            "asset": self.asset_address,
            "amount": str(self.price_micro_usdc),
            "maxTimeoutSeconds": DEFAULT_MAX_TIMEOUT_S,
            "payTo": self.receiver_address,
            "extra": {
                "name": "GatewayWalletBatched",
                "version": "1",
                "verifyingContract": self.verifying_contract,
            },
        }
        body = {"scheme": "exact", "network": self.network, "payload": payload, "requirements": requirements}
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(settle_url, json=body)
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=402,
                detail=f"facilitator rejected: HTTP {resp.status_code} {resp.text[:300]}",
            )
        data = resp.json()
        # Circle returns 200 OK even on logical failures — must inspect the
        # `success` boolean per the Gateway-Nanopayments spec.
        if data.get("success") is False:
            err_detail = data.get("error") or data.get("reason") or str(data)[:300]
            raise HTTPException(
                status_code=402,
                detail=f"facilitator settlement failed: {err_detail}",
            )
        return PaymentEvidence(
            payer_address=str(data.get("payer", payer)),
            tx_hash=str(data.get("tx_hash") or data.get("transaction") or data.get("transactionHash") or "0x"),
            settled_amount_micro_usdc=paid_micro,
            facilitator=self.facilitator_url,
            is_mock=False,
        )

    # ----- HMAC challenge signing (stateless replay protection) -----------

    def _sign_challenge(self, challenge: PaymentChallenge) -> str:
        body = json.dumps(asdict(challenge), sort_keys=True, separators=(",", ":")).encode()
        mac = hmac.new(self.signing_secret.encode(), body, hashlib.sha256).digest()
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
        # Nonce must match — accept either top-level or nested payload.nonce.
        client_nonce = (
            payment_payload.get("nonce")
            or payment_payload.get("payload", {}).get("nonce")
            or ""
        )
        if challenge.get("nonce") != client_nonce:
            return False
        if int(challenge.get("expires_at", 0)) < int(time.time()):
            return False
        return challenge.get("resource") == payment_payload.get(
            "resource", payment_payload.get("payload", {}).get("resource", "")
        )
