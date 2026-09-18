"""Portable, domain-neutral ReasoningReceipt protocol primitives.

The protocol core is self-contained: no agent, server, storage, chain, or
model-provider imports. Everything needed to build, hash, prove, sign, and
verify a `reasoning-receipt/1` envelope offline lives here.
"""

from .canon import canonical_bytes, canonical_str, parse_json_object
from .merkle import merkle_proof, merkle_root, verify_proof
from .receipt import (
    SCHEMA_VERSION,
    PortableReceipt,
    ReceiptBuilder,
    ReceiptEdge,
    ReceiptNode,
    VerifyReport,
    dumps,
    edge_leaf,
    load_receipt,
    node_leaf,
    receipt_hash_of,
    restore_receipt,
    verify_proof_document,
    verify_receipt,
    verify_receipt_proof,
)
from .verify import supported_schemas, verify_any

__all__ = [
    "SCHEMA_VERSION",
    "PortableReceipt",
    "ReceiptBuilder",
    "ReceiptEdge",
    "ReceiptNode",
    "VerifyReport",
    "canonical_bytes",
    "canonical_str",
    "dumps",
    "edge_leaf",
    "load_receipt",
    "merkle_proof",
    "merkle_root",
    "node_leaf",
    "parse_json_object",
    "receipt_hash_of",
    "restore_receipt",
    "supported_schemas",
    "verify_any",
    "verify_proof",
    "verify_proof_document",
    "verify_receipt",
    "verify_receipt_proof",
]
