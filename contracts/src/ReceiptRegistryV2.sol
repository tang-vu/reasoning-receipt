// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title  ReceiptRegistryV2
/// @notice Append-only registry of oracle receipts with **per-node Merkle commitment**.
///         Each receipt commits to (a) the SHA-256 of the canonical reasoning trace JSON
///         and (b) the Merkle root over the trace's reasoning-DAG nodes. Anyone can
///         prove that a single evidence URL, counter-argument, or sensitivity factor
///         was part of the on-chain commitment by submitting that node's bytes plus a
///         ~200-byte inclusion proof — no need to download the full trace.
/// @dev    Deployed alongside V1 (NOT a replacement). V1 keeps emitting for back-compat;
///         V2 adds the Merkle root + schema-version fields. Per-receipt gas overhead
///         vs V1: a single extra indexed bytes32 emit.
///
///         Hash function: **SHA-256** everywhere. Uses the Ethereum sha256 precompile
///         (~60 gas per invocation, far cheaper than alternatives). Off-chain proofs
///         are produced by `agent/merkle.py` with the same sorted-pair algorithm —
///         see `verifyInclusion` for the verifier mirror.
contract ReceiptRegistryV2 {
    /// @notice Emitted on every V2 receipt.
    /// @param  id            Monotonic receipt ID assigned by the contract.
    /// @param  publisher     Address that published the receipt.
    /// @param  consumer      Address that paid for the receipt via x402 (zero if agent-internal).
    /// @param  marketId      Stable market/event identifier.
    /// @param  probability   Implied probability scaled to 1e6.
    /// @param  confidence    Calibrated confidence scaled to 1e6.
    /// @param  traceHash     SHA-256 of the full canonical-trace JSON bytes (V1-compat field).
    /// @param  merkleRoot    SHA-256 binary-Merkle root over the trace's per-node hashes.
    /// @param  schemaVersion ASCII-packed schema version, e.g. "rr-trace/3".
    /// @param  traceCid      Content-addressed pointer (Irys/IPFS) to the full trace blob.
    /// @param  publishedAt   Block timestamp.
    event ReceiptV2(
        uint256 indexed id,
        address indexed publisher,
        address indexed consumer,
        bytes32 marketId,
        uint32 probability,
        uint32 confidence,
        bytes32 traceHash,
        bytes32 merkleRoot,
        bytes16 schemaVersion,
        string traceCid,
        uint64 publishedAt
    );

    uint256 public totalReceipts;
    uint32 public constant PROBABILITY_SCALE = 1_000_000;

    /// @notice Publish a single V2 receipt.
    function publishV2(
        address consumer,
        bytes32 marketId,
        uint32 probability,
        uint32 confidence,
        bytes32 traceHash,
        bytes32 merkleRoot,
        bytes16 schemaVersion,
        string calldata traceCid
    ) external returns (uint256 id) {
        require(probability <= PROBABILITY_SCALE, "RRv2: prob OOB");
        require(confidence <= PROBABILITY_SCALE, "RRv2: conf OOB");
        require(traceHash != bytes32(0), "RRv2: empty hash");
        require(merkleRoot != bytes32(0), "RRv2: empty root");
        require(bytes(traceCid).length > 0, "RRv2: empty cid");

        id = ++totalReceipts;
        emit ReceiptV2(
            id,
            msg.sender,
            consumer,
            marketId,
            probability,
            confidence,
            traceHash,
            merkleRoot,
            schemaVersion,
            traceCid,
            uint64(block.timestamp)
        );
    }

    /// @notice Batched V2 publish. Arrays must be parallel and non-empty.
    function publishBatchV2(
        address[] calldata consumers,
        bytes32[] calldata marketIds,
        uint32[] calldata probabilities,
        uint32[] calldata confidences,
        bytes32[] calldata traceHashes,
        bytes32[] calldata merkleRoots,
        bytes16[] calldata schemaVersions,
        string[] calldata traceCids
    ) external returns (uint256 firstId, uint256 lastId) {
        uint256 len = consumers.length;
        require(len > 0, "RRv2: empty batch");
        require(
            len == marketIds.length && len == probabilities.length && len == confidences.length
                && len == traceHashes.length && len == merkleRoots.length && len == schemaVersions.length
                && len == traceCids.length,
            "RRv2: length mismatch"
        );

        firstId = totalReceipts + 1;
        for (uint256 i = 0; i < len; ++i) {
            require(probabilities[i] <= PROBABILITY_SCALE, "RRv2: prob OOB");
            require(confidences[i] <= PROBABILITY_SCALE, "RRv2: conf OOB");
            require(traceHashes[i] != bytes32(0), "RRv2: empty hash");
            require(merkleRoots[i] != bytes32(0), "RRv2: empty root");
            require(bytes(traceCids[i]).length > 0, "RRv2: empty cid");

            uint256 id = ++totalReceipts;
            emit ReceiptV2(
                id,
                msg.sender,
                consumers[i],
                marketIds[i],
                probabilities[i],
                confidences[i],
                traceHashes[i],
                merkleRoots[i],
                schemaVersions[i],
                traceCids[i],
                uint64(block.timestamp)
            );
        }
        lastId = totalReceipts;
    }

    /// @notice Verify a sorted-pair SHA-256 Merkle inclusion proof.
    /// @param  root  Known Merkle root (from a V2 receipt event).
    /// @param  leaf  SHA-256 of the canonical-bytes of the node being proven.
    /// @param  proof Bottom-up list of sibling hashes.
    /// @return Whether `leaf` is in the tree committed to by `root`.
    /// @dev    Mirrors agent/merkle.py's `verify_proof`. Sorted-pair convention
    ///         (`sha256(min(a,b) || max(a,b))`) means proofs are direction-free.
    ///         Odd-level: lonely node was promoted (OZ-canonical, NOT duplicated).
    function verifyInclusion(bytes32 root, bytes32 leaf, bytes32[] calldata proof)
        external
        pure
        returns (bool)
    {
        bytes32 h = leaf;
        uint256 len = proof.length;
        for (uint256 i = 0; i < len; ++i) {
            h = _hashPair(h, proof[i]);
        }
        return h == root;
    }

    /// @dev SHA-256 of the sorted-pair concatenation. Same as agent/merkle.py `_h`.
    function _hashPair(bytes32 a, bytes32 b) private pure returns (bytes32) {
        return a <= b ? sha256(abi.encodePacked(a, b)) : sha256(abi.encodePacked(b, a));
    }
}
