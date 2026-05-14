"""Arc testnet client: publish receipts to ReceiptRegistry.sol.

Mock-friendly: if `RPC` or `RECEIPT_REGISTRY_ADDRESS` or `DEPLOYER_PRIVATE_KEY`
is missing, `ChainClient.publish` returns a deterministic mock tx hash so the
rest of the pipeline keeps moving in local dev. Production swaps in a real
web3.py call against Arc.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass

from eth_account import Account
from web3 import HTTPProvider, Web3
from web3.middleware import SignAndSendRawMiddlewareBuilder

_REGISTRY_ABI = [
    {
        "type": "function",
        "name": "publish",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "consumer", "type": "address"},
            {"name": "marketId", "type": "bytes32"},
            {"name": "probability", "type": "uint32"},
            {"name": "confidence", "type": "uint32"},
            {"name": "traceHash", "type": "bytes32"},
            {"name": "traceCid", "type": "string"},
        ],
        "outputs": [{"name": "id", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalReceipts",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "event",
        "name": "Receipt",
        "anonymous": False,
        "inputs": [
            {"name": "id", "type": "uint256", "indexed": True},
            {"name": "publisher", "type": "address", "indexed": True},
            {"name": "consumer", "type": "address", "indexed": True},
            {"name": "marketId", "type": "bytes32", "indexed": False},
            {"name": "probability", "type": "uint32", "indexed": False},
            {"name": "confidence", "type": "uint32", "indexed": False},
            {"name": "traceHash", "type": "bytes32", "indexed": False},
            {"name": "traceCid", "type": "string", "indexed": False},
            {"name": "publishedAt", "type": "uint64", "indexed": False},
        ],
    },
]

# V2 — Merkle-rooted reasoning DAG. publishV2 emits ReceiptV2 with merkleRoot
# + schemaVersion alongside the V1-compat traceHash. Only the surfaces the
# agent loop uses are declared (publishV2 + totalReceipts).
_REGISTRY_V2_ABI = [
    {
        "type": "function",
        "name": "publishV2",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "consumer", "type": "address"},
            {"name": "marketId", "type": "bytes32"},
            {"name": "probability", "type": "uint32"},
            {"name": "confidence", "type": "uint32"},
            {"name": "traceHash", "type": "bytes32"},
            {"name": "merkleRoot", "type": "bytes32"},
            {"name": "schemaVersion", "type": "bytes16"},
            {"name": "traceCid", "type": "string"},
        ],
        "outputs": [{"name": "id", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "totalReceipts",
        "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

ZERO_ADDRESS = "0x" + "0" * 40


@dataclass(slots=True)
class PublishResult:
    receipt_id: int
    tx_hash: str
    block_number: int | None
    is_mock: bool


def _market_id_bytes32(market_id: str) -> bytes:
    """Stable 32-byte hash of a market identifier (Polymarket token id, etc.)."""
    return hashlib.sha256(market_id.encode("utf-8")).digest()


def _hex_to_bytes32(hex_str: str) -> bytes:
    """Parse 0x-prefixed (or bare) 32-byte hex into bytes. Raises on bad input."""
    s = hex_str[2:] if hex_str.startswith("0x") else hex_str
    b = bytes.fromhex(s)
    if len(b) != 32:
        raise ValueError(f"expected 32-byte hex, got {len(b)} bytes from {hex_str!r}")
    return b


def _hex_with_prefix(tx_hash) -> str:
    """Web3 .hex() returns bare hex on some versions, 0x-prefixed on others.
    Block explorers (Blockscout / Arcscan) reject hashes without 0x — always
    return canonical 0x-prefixed form here."""
    s = tx_hash.hex() if isinstance(tx_hash, bytes) else str(tx_hash)
    return s if s.startswith("0x") else f"0x{s}"


def _scale_unit_to_ppm(x: float) -> int:
    """Clamp a 0..1 float to 0..1_000_000 (PROBABILITY_SCALE)."""
    if x < 0.0:
        x = 0.0
    if x > 1.0:
        x = 1.0
    return int(round(x * 1_000_000))


class ChainClient:
    """Web3 client for ReceiptRegistry, with mock fallback when creds absent."""

    def __init__(
        self,
        *,
        rpc_url: str | None = None,
        registry_address: str | None = None,
        registry_v2_address: str | None = None,
        private_key: str | None = None,
        mock: bool | None = None,
    ) -> None:
        self.rpc_url = rpc_url or os.getenv("RPC")
        self.registry_address = registry_address or os.getenv("RECEIPT_REGISTRY_ADDRESS")
        self.registry_v2_address = registry_v2_address or os.getenv("RECEIPT_REGISTRY_V2_ADDRESS")
        self.private_key = private_key or os.getenv("DEPLOYER_PRIVATE_KEY")
        env_mock = os.getenv("RR_MOCK_CHAIN", "").lower() in {"1", "true", "yes"}
        self.mock = env_mock if mock is None else mock
        if not (self.rpc_url and self.registry_address and self.private_key):
            self.mock = True

        self._w3: Web3 | None = None
        self._account = None
        self._contract = None
        self._contract_v2 = None  # populated only if registry_v2_address is set
        self._mock_counter = 0
        self._mock_counter_v2 = 0

        if not self.mock:
            self._connect()

    def _connect(self) -> None:
        assert self.rpc_url and self.private_key and self.registry_address
        w3 = Web3(HTTPProvider(self.rpc_url, request_kwargs={"timeout": 15}))
        acct = Account.from_key(self.private_key)
        w3.middleware_onion.inject(SignAndSendRawMiddlewareBuilder.build(acct), layer=0)
        w3.eth.default_account = acct.address
        contract = w3.eth.contract(
            address=Web3.to_checksum_address(self.registry_address),
            abi=_REGISTRY_ABI,
        )
        self._w3 = w3
        self._account = acct
        self._contract = contract
        if self.registry_v2_address:
            self._contract_v2 = w3.eth.contract(
                address=Web3.to_checksum_address(self.registry_v2_address),
                abi=_REGISTRY_V2_ABI,
            )

    @property
    def publisher_address(self) -> str:
        if self._account:
            return self._account.address
        return "0x" + b"Pu".hex().ljust(40, "0")[:40]

    def total_receipts(self) -> int:
        if self.mock or self._contract is None:
            return self._mock_counter
        return int(self._contract.functions.totalReceipts().call())

    def publish(
        self,
        *,
        consumer_address: str | None,
        market_id: str,
        probability: float,
        confidence: float,
        trace_hash_hex: str,
        trace_cid: str,
    ) -> PublishResult:
        consumer = consumer_address or ZERO_ADDRESS
        market_bytes32 = _market_id_bytes32(market_id)
        prob_ppm = _scale_unit_to_ppm(probability)
        conf_ppm = _scale_unit_to_ppm(confidence)
        if trace_hash_hex.startswith("0x"):
            trace_hash = bytes.fromhex(trace_hash_hex[2:])
        else:
            trace_hash = bytes.fromhex(trace_hash_hex)
        if len(trace_hash) != 32:
            raise ValueError(f"trace hash must be 32 bytes, got {len(trace_hash)}")

        if self.mock or self._contract is None:
            self._mock_counter += 1
            digest = hashlib.sha256(
                f"{self._mock_counter}{market_id}{trace_hash_hex}{time.time_ns()}".encode()
            ).hexdigest()
            return PublishResult(
                receipt_id=self._mock_counter,
                tx_hash="0x" + digest,
                block_number=None,
                is_mock=True,
            )

        fn = self._contract.functions.publish(
            Web3.to_checksum_address(consumer),
            market_bytes32,
            prob_ppm,
            conf_ppm,
            trace_hash,
            trace_cid,
        )
        tx_hash = fn.transact({"from": self._account.address})
        rcpt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        receipt_id = int(self._contract.functions.totalReceipts().call())
        return PublishResult(
            receipt_id=receipt_id,
            tx_hash=_hex_with_prefix(tx_hash),
            block_number=rcpt["blockNumber"],
            is_mock=False,
        )

    def publish_v2(
        self,
        *,
        consumer_address: str | None,
        market_id: str,
        probability: float,
        confidence: float,
        trace_hash_hex: str,
        merkle_root_hex: str,
        schema_version: str,
        trace_cid: str,
    ) -> PublishResult:
        """Emit a ReceiptV2 with the trace Merkle root + schema version.

        Mock mode mirrors `publish`. When the V2 contract isn't configured
        (no RECEIPT_REGISTRY_V2_ADDRESS), falls back to mock so the agent
        loop never blocks on missing V2 wiring.
        """
        consumer = consumer_address or ZERO_ADDRESS
        market_bytes32 = _market_id_bytes32(market_id)
        prob_ppm = _scale_unit_to_ppm(probability)
        conf_ppm = _scale_unit_to_ppm(confidence)
        trace_hash = _hex_to_bytes32(trace_hash_hex)
        merkle_root = _hex_to_bytes32(merkle_root_hex)
        schema_bytes16 = schema_version.encode("ascii")[:16].ljust(16, b"\0")

        if self.mock or self._contract_v2 is None:
            self._mock_counter_v2 += 1
            digest = hashlib.sha256(
                f"v2-{self._mock_counter_v2}{market_id}{merkle_root_hex}{time.time_ns()}".encode()
            ).hexdigest()
            return PublishResult(
                receipt_id=self._mock_counter_v2,
                tx_hash="0x" + digest,
                block_number=None,
                is_mock=True,
            )

        fn = self._contract_v2.functions.publishV2(
            Web3.to_checksum_address(consumer),
            market_bytes32,
            prob_ppm,
            conf_ppm,
            trace_hash,
            merkle_root,
            schema_bytes16,
            trace_cid,
        )
        tx_hash = fn.transact({"from": self._account.address})
        rcpt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        receipt_id = int(self._contract_v2.functions.totalReceipts().call())
        return PublishResult(
            receipt_id=receipt_id,
            tx_hash=_hex_with_prefix(tx_hash),
            block_number=rcpt["blockNumber"],
            is_mock=False,
        )
