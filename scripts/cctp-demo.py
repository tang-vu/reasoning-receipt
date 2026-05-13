"""cctp-demo.py — one-shot Ethereum Sepolia → Arc Testnet USDC transfer via CCTP V2.

Demonstrates Circle's cross-chain transfer protocol in three on-chain steps:
  1. approve TokenMessengerV2 to spend USDC on Sepolia
  2. depositForBurn — locks USDC on Sepolia, emits a Burn message
  3. once Circle's attestation service signs the burn, call receiveMessage on
     Arc Testnet — mints the same USDC on Arc

Output: three tx hashes (approve, burn, mint) + the Iris attestation id. Each
explorer link is printed so a judge can verify the transfer on both chains.

Prerequisites:
  - .env has DEPLOYER_PRIVATE_KEY (same key works on both chains)
  - Deployer address funded with:
      * Sepolia ETH (gas) — https://cloud.google.com/application/web3/faucet/ethereum/sepolia
      * Sepolia USDC      — https://faucet.circle.com
      * Arc Testnet USDC  — https://faucet.circle.com (gas on Arc is paid in USDC)

Usage:
    uv run python -m scripts.cctp-demo --amount-usdc 1.0
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

import httpx
from dotenv import load_dotenv
from eth_account import Account
from web3 import HTTPProvider, Web3
from web3.middleware import SignAndSendRawMiddlewareBuilder

logger = logging.getLogger("rr.cctp")

# --- network constants (testnet CCTP V2, common across all testnets) ---
SEPOLIA_RPC_DEFAULT = "https://ethereum-sepolia-rpc.publicnode.com"

SEPOLIA_USDC = "0x1c7D4B196Cb0C7B01d743Fbc6116a902379C7238"
SEPOLIA_TOKEN_MESSENGER = "0x8FE6B999Dc680CcFDD5Bf7EB0974218be2542DAA"
ARC_MESSAGE_TRANSMITTER = "0xE737e5cEBEEBa77EFE34D4aa090756590b1CE275"

SEPOLIA_DOMAIN = 0
ARC_TESTNET_DOMAIN = 26

IRIS_API = "https://iris-api-sandbox.circle.com"

_ABI_ERC20_APPROVE = [
    {
        "type": "function",
        "name": "approve",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function",
        "name": "balanceOf",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

_ABI_DEPOSIT_FOR_BURN = [
    {
        "type": "function",
        "name": "depositForBurn",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "amount", "type": "uint256"},
            {"name": "destinationDomain", "type": "uint32"},
            {"name": "mintRecipient", "type": "bytes32"},
            {"name": "burnToken", "type": "address"},
            {"name": "destinationCaller", "type": "bytes32"},
            {"name": "maxFee", "type": "uint256"},
            {"name": "minFinalityThreshold", "type": "uint32"},
        ],
        "outputs": [],
    }
]

_ABI_RECEIVE_MESSAGE = [
    {
        "type": "function",
        "name": "receiveMessage",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "message", "type": "bytes"},
            {"name": "attestation", "type": "bytes"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    }
]


def _bytes32(addr: str) -> bytes:
    """Left-pad a 20-byte address into 32 bytes for CCTP `mintRecipient`."""
    return bytes(12) + bytes.fromhex(addr.removeprefix("0x"))


def _connect(rpc: str, account) -> Web3:
    w3 = Web3(HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    w3.middleware_onion.inject(SignAndSendRawMiddlewareBuilder.build(account), layer=0)
    w3.eth.default_account = account.address
    return w3


def _approve_usdc(w3: Web3, account, amount: int) -> str:
    contract = w3.eth.contract(address=Web3.to_checksum_address(SEPOLIA_USDC), abi=_ABI_ERC20_APPROVE)
    fn = contract.functions.approve(Web3.to_checksum_address(SEPOLIA_TOKEN_MESSENGER), amount)
    tx_hash = fn.transact({"from": account.address})
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    logger.info("sepolia approve mined: block=%s tx=%s", rcpt["blockNumber"], tx_hash.hex())
    return tx_hash.hex() if isinstance(tx_hash, bytes) else str(tx_hash)


def _deposit_for_burn(w3: Web3, account, amount: int, max_fee: int) -> str:
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(SEPOLIA_TOKEN_MESSENGER),
        abi=_ABI_DEPOSIT_FOR_BURN,
    )
    fn = contract.functions.depositForBurn(
        amount,
        ARC_TESTNET_DOMAIN,
        _bytes32(account.address),
        Web3.to_checksum_address(SEPOLIA_USDC),
        bytes(32),  # empty destinationCaller → anyone can mint
        max_fee,
        1000,  # minFinalityThreshold: 1000 = fast transfer
    )
    tx_hash = fn.transact({"from": account.address})
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    logger.info("sepolia depositForBurn mined: block=%s tx=%s", rcpt["blockNumber"], tx_hash.hex())
    return tx_hash.hex() if isinstance(tx_hash, bytes) else str(tx_hash)


def _wait_for_attestation(burn_tx_hash: str, max_wait_s: int = 600) -> tuple[str, str]:
    """Poll Iris API for the attestation of the burn. Returns (message_hex, attestation_hex)."""
    if not burn_tx_hash.startswith("0x"):
        burn_tx_hash = "0x" + burn_tx_hash
    url = f"{IRIS_API}/v2/messages/{SEPOLIA_DOMAIN}?transactionHash={burn_tx_hash}"
    deadline = time.time() + max_wait_s
    last_status = None
    with httpx.Client(timeout=15.0) as client:
        while time.time() < deadline:
            try:
                resp = client.get(url)
            except Exception as exc:
                logger.warning("iris poll error (%s); retrying", exc)
                time.sleep(5)
                continue
            if resp.status_code == 200:
                data = resp.json()
                msg = (data.get("messages") or [{}])[0]
                status = msg.get("status")
                if status != last_status:
                    logger.info("iris attestation status: %s", status)
                    last_status = status
                if status == "complete" and msg.get("attestation"):
                    return msg["message"], msg["attestation"]
            time.sleep(5)
    raise TimeoutError(f"attestation not ready within {max_wait_s}s")


def _receive_on_arc(w3: Web3, account, message_hex: str, attestation_hex: str) -> str:
    contract = w3.eth.contract(
        address=Web3.to_checksum_address(ARC_MESSAGE_TRANSMITTER),
        abi=_ABI_RECEIVE_MESSAGE,
    )
    fn = contract.functions.receiveMessage(
        bytes.fromhex(message_hex.removeprefix("0x")),
        bytes.fromhex(attestation_hex.removeprefix("0x")),
    )
    tx_hash = fn.transact({"from": account.address})
    rcpt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    logger.info("arc receiveMessage mined: block=%s tx=%s", rcpt["blockNumber"], tx_hash.hex())
    return tx_hash.hex() if isinstance(tx_hash, bytes) else str(tx_hash)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CCTP V2 Sepolia → Arc Testnet demo.")
    parser.add_argument("--amount-usdc", type=float, default=1.0, help="USDC to transfer (default: 1.0)")
    parser.add_argument("--max-fee-usdc", type=float, default=0.0005, help="Max protocol fee (default 0.0005)")
    parser.add_argument("--sepolia-rpc", default=os.getenv("SEPOLIA_RPC", SEPOLIA_RPC_DEFAULT))
    parser.add_argument(
        "--skip-approve",
        action="store_true",
        help="Skip the ERC20 approve step (use when allowance already set)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)-7s %(message)s")
    load_dotenv()

    pk = os.getenv("DEPLOYER_PRIVATE_KEY")
    arc_rpc = os.getenv("RPC")
    if not pk or not arc_rpc:
        print("DEPLOYER_PRIVATE_KEY and RPC (Arc Testnet) must be set in .env", file=sys.stderr)
        return 1

    account = Account.from_key(pk)
    amount = int(round(args.amount_usdc * 1_000_000))
    max_fee = int(round(args.max_fee_usdc * 1_000_000))

    print(f"deployer       : {account.address}")
    print(f"transfer       : {args.amount_usdc} USDC ({amount} micro)")
    print(f"max protocol fee: {args.max_fee_usdc} USDC ({max_fee} micro)")
    print(f"source         : Ethereum Sepolia (domain {SEPOLIA_DOMAIN})")
    print(f"destination    : Arc Testnet (domain {ARC_TESTNET_DOMAIN})")
    print()

    print("--- connecting to Ethereum Sepolia ---")
    sepolia = _connect(args.sepolia_rpc, account)
    block = sepolia.eth.block_number
    print(f"sepolia block: {block}")

    usdc = sepolia.eth.contract(address=Web3.to_checksum_address(SEPOLIA_USDC), abi=_ABI_ERC20_APPROVE)
    bal = usdc.functions.balanceOf(account.address).call()
    print(f"sepolia USDC balance: {bal / 1e6} ({bal} micro)")
    if bal < amount + max_fee:
        print(
            "INSUFFICIENT Sepolia USDC. Fund via https://faucet.circle.com → "
            "Ethereum Sepolia → USDC, then retry.",
            file=sys.stderr,
        )
        return 2

    print()
    if not args.skip_approve:
        print("--- 1/3 approve USDC on Sepolia ---")
        approve_tx = _approve_usdc(sepolia, account, amount + max_fee)
        print(f"  https://sepolia.etherscan.io/tx/{approve_tx}")
    else:
        print("--- 1/3 approve: SKIPPED (--skip-approve) ---")

    print()
    print("--- 2/3 depositForBurn on Sepolia ---")
    burn_tx = _deposit_for_burn(sepolia, account, amount, max_fee)
    print(f"  https://sepolia.etherscan.io/tx/{burn_tx}")

    print()
    print("--- waiting for Circle attestation ---")
    message, attestation = _wait_for_attestation(burn_tx)
    print(f"  attestation received ({len(attestation)//2} bytes)")

    print()
    print("--- 3/3 receiveMessage on Arc Testnet ---")
    arc = _connect(arc_rpc, account)
    mint_tx = _receive_on_arc(arc, account, message, attestation)
    print(f"  arc tx: {mint_tx}")
    print(f"  (explorer: https://testnet.arcscan.app/tx/{mint_tx})")

    print()
    print("--- DONE ---")
    print(f"  burn (Sepolia): {burn_tx}")
    print(f"  mint (Arc)    : {mint_tx}")
    print(f"  {args.amount_usdc} USDC moved Sepolia -> Arc Testnet via CCTP V2")
    return 0


if __name__ == "__main__":
    sys.exit(main())
