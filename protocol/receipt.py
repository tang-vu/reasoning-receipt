"""Domain-neutral, portable ReasoningReceipt envelope.

The prediction-market trace remains one application of ReasoningReceipt. This
module exposes the reusable primitive underneath it: ordered, typed evidence
nodes committed by canonical SHA-256 hashes and a sorted-pair Merkle root.

No chain, model provider, storage backend, or market schema is required.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from agent import merkle
from storage.irys import canonical_bytes, sha256_hex

SCHEMA_VERSION = "reasoning-receipt/1"


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bytes32(value: str) -> bytes:
    raw = value[2:] if value.startswith("0x") else value
    decoded = bytes.fromhex(raw)
    if len(decoded) != 32:
        raise ValueError(f"expected bytes32 hex, got {len(decoded)} bytes")
    return decoded


@dataclass(frozen=True, slots=True)
class ReceiptNode:
    """One independently provable fact in an AI decision or action trace."""

    id: str
    kind: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        if not self.id.strip():
            raise ValueError("receipt node id must not be empty")
        if not self.kind.strip():
            raise ValueError("receipt node kind must not be empty")
        return asdict(self)

    def hash_hex(self) -> str:
        return sha256_hex(canonical_bytes(self.to_dict()))


@dataclass(frozen=True, slots=True)
class ReceiptProof:
    """Portable inclusion proof for exactly one receipt node."""

    schema_version: str
    receipt_id: str
    subject: str
    node: dict[str, Any]
    node_hash: str
    merkle_root: str
    proof: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PortableReceipt:
    """A domain-neutral commitment to evidence behind an AI decision/action.

    Node order does not affect the commitment: nodes are always ordered by
    stable id before their hashes are folded into the Merkle tree. Node ids
    must therefore be unique within a receipt.
    """

    subject: str
    nodes: list[ReceiptNode]
    metadata: dict[str, Any] = field(default_factory=dict)
    receipt_id: str = field(default_factory=lambda: str(uuid4()))
    produced_at: str = field(default_factory=_utcnow_iso)
    schema_version: str = SCHEMA_VERSION

    def _ordered_nodes(self) -> list[ReceiptNode]:
        if not self.subject.strip():
            raise ValueError("receipt subject must not be empty")
        if not self.nodes:
            raise ValueError("receipt must contain at least one node")
        ids = [node.id for node in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("receipt node ids must be unique")
        return sorted(self.nodes, key=lambda node: node.id)

    def node_hashes(self) -> dict[str, str]:
        return {node.id: node.hash_hex() for node in self._ordered_nodes()}

    def merkle_root_hex(self) -> str:
        hashes = self.node_hashes()
        leaves = [_bytes32(hashes[node_id]) for node_id in sorted(hashes)]
        return "0x" + merkle.merkle_root(leaves).hex()

    def proof_for(self, node_id: str) -> ReceiptProof:
        ordered = self._ordered_nodes()
        ids = [node.id for node in ordered]
        if node_id not in ids:
            raise KeyError(f"node {node_id!r} not in receipt")
        hashes = {node.id: node.hash_hex() for node in ordered}
        leaves = [_bytes32(hashes[current_id]) for current_id in ids]
        index = ids.index(node_id)
        node = ordered[index]
        return ReceiptProof(
            schema_version=self.schema_version,
            receipt_id=self.receipt_id,
            subject=self.subject,
            node=node.to_dict(),
            node_hash=hashes[node_id],
            merkle_root="0x" + merkle.merkle_root(leaves).hex(),
            proof=["0x" + sibling.hex() for sibling in merkle.merkle_proof(leaves, index)],
        )

    def to_dict(self) -> dict[str, Any]:
        ordered = self._ordered_nodes()
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "subject": self.subject,
            "produced_at": self.produced_at,
            "metadata": self.metadata,
            "nodes": [node.to_dict() for node in ordered],
            "node_hashes": {node.id: node.hash_hex() for node in ordered},
            "merkle_root": self.merkle_root_hex(),
        }

    def receipt_hash(self) -> str:
        """Hash the full portable envelope for byte-level integrity checks."""
        return sha256_hex(canonical_bytes(self.to_dict()))


def verify_receipt_proof(proof: ReceiptProof | dict[str, Any]) -> bool:
    """Verify a standalone node proof without trusting the receipt producer."""
    data = proof.to_dict() if isinstance(proof, ReceiptProof) else proof
    try:
        node = data["node"]
        expected_hash = data["node_hash"]
        actual_hash = sha256_hex(canonical_bytes(node))
        if actual_hash != expected_hash:
            return False
        siblings = [_bytes32(value) for value in data["proof"]]
        return merkle.verify_proof(
            _bytes32(actual_hash),
            siblings,
            _bytes32(data["merkle_root"]),
        )
    except (KeyError, TypeError, ValueError):
        return False


def verify_receipt(receipt: dict[str, Any]) -> bool:
    """Recompute every derived commitment in a serialized receipt envelope."""
    try:
        if receipt.get("schema_version") != SCHEMA_VERSION:
            return False
        raw_nodes = receipt["nodes"]
        if not isinstance(raw_nodes, list) or not raw_nodes:
            return False
        nodes = [ReceiptNode(id=n["id"], kind=n["kind"], payload=n["payload"]) for n in raw_nodes]
        rebuilt = PortableReceipt(
            receipt_id=receipt["receipt_id"],
            subject=receipt["subject"],
            produced_at=receipt["produced_at"],
            metadata=receipt.get("metadata", {}),
            nodes=nodes,
        )
        return (
            rebuilt.node_hashes() == receipt["node_hashes"]
            and rebuilt.merkle_root_hex() == receipt["merkle_root"]
        )
    except (KeyError, TypeError, ValueError):
        return False
