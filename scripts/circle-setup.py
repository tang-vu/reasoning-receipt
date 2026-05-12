"""circle-setup.py — provision Circle developer-controlled wallets via API.

Headless setup, no UI clicks. In one shot:

  1. GET Circle's RSA public key.
  2. Generate a random 32-byte entity secret (hex).
  3. RSA-OAEP encrypt the secret to produce entity-secret-ciphertext.
  4. Register the ciphertext via /config/entity/entitySecret (one-time).
  5. Persist the entity-secret recovery file Circle returns.
  6. Create a wallet set.
  7. Create two wallets in the set (portfolio + consumer) on Arc Testnet.
  8. Write all credentials into .env.

Idempotent: detects already-registered entity-secret and skips registration.
Re-runs on existing wallet set / wallets are safe — won't duplicate.

Requires:
  - CIRCLE_API_KEY in .env (already populated)

Outputs:
  - notes/circle-recovery-{ts}.json  (entity secret recovery — SAFE, gitignored)
  - .env populated with CIRCLE_ENTITY_SECRET, CIRCLE_WALLET_SET_ID,
    CIRCLE_PORTFOLIO_WALLET_ID, CIRCLE_CONSUMER_WALLET_ID,
    X402_RECEIVER_ADDRESS (= portfolio wallet address)
"""

from __future__ import annotations

import argparse
import base64
import logging
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from dotenv import load_dotenv

logger = logging.getLogger("rr.circle-setup")

CIRCLE_BASE = "https://api.circle.com/v1/w3s"
BLOCKCHAIN = "ARC-TESTNET"  # change to ARC-SEPOLIA if Circle renamed
ACCOUNT_TYPE = "EOA"


def _encrypt_entity_secret(plain_hex: str, pem_pub_key: str) -> str:
    """RSA-OAEP encrypt the 32-byte entity secret with Circle's public key.

    Returns base64-encoded ciphertext suitable for `entitySecretCiphertext`.
    """
    secret_bytes = bytes.fromhex(plain_hex)
    if len(secret_bytes) != 32:
        raise ValueError(f"entity secret must be 32 bytes, got {len(secret_bytes)}")

    public_key = serialization.load_pem_public_key(pem_pub_key.encode("utf-8"))
    ciphertext = public_key.encrypt(
        secret_bytes,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return base64.b64encode(ciphertext).decode("ascii")


def _headers(api_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def get_public_key(client: httpx.Client, api_key: str) -> str:
    resp = client.get(f"{CIRCLE_BASE}/config/entity/publicKey", headers=_headers(api_key))
    resp.raise_for_status()
    return resp.json()["data"]["publicKey"]


def register_entity_secret(client: httpx.Client, api_key: str, plain_hex: str, pem: str) -> dict:
    """Register the encrypted secret. Returns the recovery payload Circle sends back.

    If a secret is already registered, returns the existing recovery file or
    a stub indicating that — caller decides.
    """
    ciphertext = _encrypt_entity_secret(plain_hex, pem)
    payload = {
        "entitySecretCiphertext": ciphertext,
        "idempotencyKey": str(uuid.uuid4()),
    }
    resp = client.post(
        f"{CIRCLE_BASE}/config/entity/entitySecret",
        headers=_headers(api_key),
        json=payload,
    )
    if resp.status_code == 409 or "already" in resp.text.lower():
        logger.warning("entity-secret already registered for this account — reusing")
        return {"data": {"alreadyRegistered": True}}
    resp.raise_for_status()
    return resp.json()


def make_ciphertext(api_key: str, plain_hex: str, pem: str) -> str:
    """Fresh ciphertext per call — Circle rejects reused ciphertexts."""
    return _encrypt_entity_secret(plain_hex, pem)


def create_wallet_set(
    client: httpx.Client,
    api_key: str,
    plain_hex: str,
    pem: str,
    name: str,
) -> dict:
    payload = {
        "name": name,
        "idempotencyKey": str(uuid.uuid4()),
        "entitySecretCiphertext": make_ciphertext(api_key, plain_hex, pem),
    }
    resp = client.post(
        f"{CIRCLE_BASE}/developer/walletSets",
        headers=_headers(api_key),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()["data"]["walletSet"]


def list_wallets(client: httpx.Client, api_key: str, wallet_set_id: str) -> list[dict]:
    resp = client.get(
        f"{CIRCLE_BASE}/wallets",
        headers=_headers(api_key),
        params={"walletSetId": wallet_set_id},
    )
    resp.raise_for_status()
    return resp.json()["data"]["wallets"]


def create_wallets(
    client: httpx.Client,
    api_key: str,
    plain_hex: str,
    pem: str,
    wallet_set_id: str,
    *,
    count: int = 2,
    blockchain: str = BLOCKCHAIN,
    account_type: str = ACCOUNT_TYPE,
) -> list[dict]:
    payload = {
        "walletSetId": wallet_set_id,
        "blockchains": [blockchain],
        "count": count,
        "accountType": account_type,
        "idempotencyKey": str(uuid.uuid4()),
        "entitySecretCiphertext": make_ciphertext(api_key, plain_hex, pem),
    }
    resp = client.post(
        f"{CIRCLE_BASE}/developer/wallets",
        headers=_headers(api_key),
        json=payload,
    )
    resp.raise_for_status()
    return resp.json()["data"]["wallets"]


def _write_env(updates: dict[str, str]) -> None:
    p = Path(".env")
    text = p.read_text(encoding="utf-8")
    for key, value in updates.items():
        # Replace any existing line, otherwise append.
        marker_blank = f"{key}=\n"
        if marker_blank in text:
            text = text.replace(marker_blank, f"{key}={value}\n", 1)
        else:
            # find any existing populated line and replace
            import re

            new_text, n = re.subn(rf"^{re.escape(key)}=.*$", f"{key}={value}", text, count=1, flags=re.MULTILINE)
            if n:
                text = new_text
            else:
                text += f"\n{key}={value}\n"
    p.write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Provision Circle dev-controlled wallets via API.")
    parser.add_argument("--blockchain", default=BLOCKCHAIN, help="Circle blockchain ID")
    parser.add_argument("--wallet-set-name", default="reasoning-receipt-prod")
    parser.add_argument("--reuse-secret", help="Hex entity secret to reuse instead of generating")
    args = parser.parse_args(argv)

    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
    load_dotenv()
    api_key = os.getenv("CIRCLE_API_KEY")
    if not api_key:
        logger.error("CIRCLE_API_KEY missing from .env")
        return 1

    plain_hex = args.reuse_secret or secrets.token_hex(32)
    if not args.reuse_secret:
        logger.info("generated fresh entity secret (32 bytes)")
    else:
        logger.info("reusing supplied entity secret")

    with httpx.Client(timeout=20.0) as client:
        logger.info("fetching Circle public key…")
        pem = get_public_key(client, api_key)

        logger.info("registering entity secret…")
        registration = register_entity_secret(client, api_key, plain_hex, pem)
        already = registration.get("data", {}).get("alreadyRegistered", False)
        recovery_b64 = registration.get("data", {}).get("recoveryFile")

        # Persist recovery file to local-only notes/
        if recovery_b64 and not already:
            Path("notes").mkdir(exist_ok=True)
            ts = int(time.time())
            recovery_path = Path(f"notes/circle-recovery-{ts}.json")
            recovery_path.write_text(recovery_b64, encoding="utf-8")
            logger.info("saved recovery file → %s (KEEP SAFE, NOT committed)", recovery_path)

        logger.info("creating wallet set '%s'…", args.wallet_set_name)
        wallet_set = create_wallet_set(client, api_key, plain_hex, pem, args.wallet_set_name)
        wallet_set_id = wallet_set["id"]
        logger.info("walletSetId: %s", wallet_set_id)

        logger.info("creating 2 wallets (portfolio + consumer) on %s…", args.blockchain)
        wallets = create_wallets(
            client, api_key, plain_hex, pem, wallet_set_id, count=2, blockchain=args.blockchain
        )
        if len(wallets) < 2:
            logger.error("expected 2 wallets back, got %d", len(wallets))
            return 1

        portfolio, consumer = wallets[0], wallets[1]
        logger.info("portfolio wallet: id=%s address=%s", portfolio["id"], portfolio["address"])
        logger.info("consumer  wallet: id=%s address=%s", consumer["id"], consumer["address"])

    _write_env(
        {
            "CIRCLE_ENTITY_SECRET": plain_hex,
            "CIRCLE_WALLET_SET_ID": wallet_set_id,
            "CIRCLE_PORTFOLIO_WALLET_ID": portfolio["id"],
            "CIRCLE_CONSUMER_WALLET_ID": consumer["id"],
            "X402_RECEIVER_ADDRESS": portfolio["address"],
        }
    )
    logger.info("wrote .env updates ✓")

    print()
    print("---  Funding instructions  ---")
    print("Fund these two addresses at https://faucet.circle.com (Arc Testnet, USDC):")
    print(f"  portfolio:  {portfolio['address']}    [paywall recipient + trader bankroll]")
    print(f"  consumer:   {consumer['address']}     [agent's own oracle consumer wallet]")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
