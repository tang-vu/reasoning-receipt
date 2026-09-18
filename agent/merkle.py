"""Compatibility shim — the Merkle implementation moved to `protocol/merkle.py`.

The sorted-pair SHA-256 Merkle tree is protocol core, not agent code; the
protocol package cannot depend on the reference adapter. This module keeps
`agent.merkle` importable for the reference implementation and its tests.
"""

from protocol.merkle import merkle_proof, merkle_root, verify_proof

__all__ = ["merkle_proof", "merkle_root", "verify_proof"]
