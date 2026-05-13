"""Binary Merkle tree over SHA-256, OpenZeppelin-style sorted-pair proofs.

Used by rr-trace/3 to commit a single root over the hashes of every node in
the reasoning DAG (claim, stances, evidence, counter-arguments, sensitivity,
critic dimensions, falsifiable claims). One Merkle root on Arc lets anyone
prove inclusion of any single node with a ~200-byte proof — without
downloading the full trace.

Design notes:
- **Hash function:** SHA-256 throughout (Solidity has a `sha256` precompile,
  60 gas). Mirrors `storage.irys.sha256_hex` so off-chain and on-chain agree
  on the byte interpretation.
- **Pair ordering:** sorted-pair concat (`sha256(min(a,b) || max(a,b))`).
  Matches OpenZeppelin's MerkleProof.sol convention except for the hash —
  swap `keccak256` for `sha256` and the algorithm is identical. This is the
  exact algorithm `ReceiptRegistryV2.verifyInclusion` will implement in
  Phase 4.
- **Odd levels:** the lonely node is promoted (NOT duplicated).
  OZ-canonical, simpler proof generation, no second-pre-image risk.
- **Leaf format:** 32 raw bytes. Callers pass `bytes32` leaves (the hashes of
  the canonical bytes of each node).
"""

from __future__ import annotations

import hashlib


def _h(left: bytes, right: bytes) -> bytes:
    """SHA-256 of sorted-pair concat — Solidity-compatible parent hash."""
    if left <= right:
        return hashlib.sha256(left + right).digest()
    return hashlib.sha256(right + left).digest()


def merkle_root(leaves: list[bytes]) -> bytes:
    """Compute the Merkle root over a list of 32-byte leaves.

    Empty list → 32 zero bytes (sentinel; a real trace always has ≥ 1 node).
    Single leaf → the leaf itself is the root.
    """
    if not leaves:
        return b"\x00" * 32
    for leaf in leaves:
        if len(leaf) != 32:
            raise ValueError(f"merkle: leaf must be 32 bytes, got {len(leaf)}")
    level = list(leaves)
    while len(level) > 1:
        next_level: list[bytes] = []
        i = 0
        while i + 1 < len(level):
            next_level.append(_h(level[i], level[i + 1]))
            i += 2
        if i < len(level):
            # Lonely node at the end: promote up, OZ-canonical.
            next_level.append(level[i])
        level = next_level
    return level[0]


def merkle_proof(leaves: list[bytes], index: int) -> list[bytes]:
    """Generate an inclusion proof for `leaves[index]`.

    Returns a list of 32-byte sibling hashes. To verify, the caller iteratively
    folds `leaf` with each proof element using `_h` and checks the final hash
    equals the known root. Order in the proof is bottom-up.
    """
    if index < 0 or index >= len(leaves):
        raise IndexError(f"merkle: index {index} out of range for {len(leaves)} leaves")
    proof: list[bytes] = []
    level = list(leaves)
    idx = index
    while len(level) > 1:
        next_level: list[bytes] = []
        i = 0
        while i + 1 < len(level):
            pair_parent = _h(level[i], level[i + 1])
            next_level.append(pair_parent)
            if i == idx or i + 1 == idx:
                sibling = level[i + 1] if i == idx else level[i]
                proof.append(sibling)
                idx = len(next_level) - 1
            i += 2
        if i < len(level):
            # Lonely node — promote, no sibling added to proof.
            next_level.append(level[i])
            if i == idx:
                idx = len(next_level) - 1
        level = next_level
    return proof


def verify_proof(leaf: bytes, proof: list[bytes], root: bytes) -> bool:
    """Verify a sorted-pair Merkle proof. Mirrors Solidity verifyInclusion."""
    if len(leaf) != 32 or len(root) != 32:
        return False
    h = leaf
    for sibling in proof:
        if len(sibling) != 32:
            return False
        h = _h(h, sibling)
    return h == root
