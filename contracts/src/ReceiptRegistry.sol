// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title ReceiptRegistry
/// @notice Append-only registry of oracle receipts. Each receipt commits to a hashed
///         reasoning trace (off-chain, pinned to Irys/IPFS) and a probability for a
///         prediction-market event. The registry stores nothing but the event log —
///         clients reconstruct state from `Receipt` events.
/// @dev    Designed for Arc testnet. Per-receipt gas is minimal (one event emit, one
///         storage write for the counter). No admin, no upgrades, no pause switch.
contract ReceiptRegistry {
    /// @notice Emitted on every published receipt.
    /// @param  id         Monotonic receipt ID assigned by the contract.
    /// @param  publisher  Address that published the receipt (typically the oracle wallet).
    /// @param  consumer   Address that paid for the receipt via x402. Zero if unpaid (agent-internal).
    /// @param  marketId   Stable, market-specific event identifier (e.g. Polymarket token id).
    /// @param  probability Implied probability scaled to 1e6 (e.g. 612_345 = 0.612345).
    /// @param  confidence Calibrated confidence scaled to 1e6.
    /// @param  traceHash  SHA-256 of the canonical reasoning-trace JSON bytes.
    /// @param  traceCid   Content-addressed pointer (Irys/IPFS) to the trace blob.
    /// @param  publishedAt Block timestamp when the receipt was emitted.
    event Receipt(
        uint256 indexed id,
        address indexed publisher,
        address indexed consumer,
        bytes32 marketId,
        uint32 probability,
        uint32 confidence,
        bytes32 traceHash,
        string traceCid,
        uint64 publishedAt
    );

    /// @notice Total receipts emitted. Public so dashboards can poll a single uint.
    uint256 public totalReceipts;

    /// @notice Probability and confidence are expressed in basis-of-1e6.
    uint32 public constant PROBABILITY_SCALE = 1_000_000;

    /// @notice Publish a receipt. Anyone can call; intent is the oracle wallet does so
    ///         after settling x402 payment off-chain.
    /// @param  consumer    Address that paid; pass address(0) for agent-internal receipts.
    /// @param  marketId    Stable market/event identifier.
    /// @param  probability Implied probability in 1e6 units, must be ≤ PROBABILITY_SCALE.
    /// @param  confidence  Calibrated confidence in 1e6 units, must be ≤ PROBABILITY_SCALE.
    /// @param  traceHash   SHA-256 of the canonical trace JSON.
    /// @param  traceCid    Irys/IPFS CID for the trace blob.
    /// @return id          The newly assigned receipt ID.
    function publish(
        address consumer,
        bytes32 marketId,
        uint32 probability,
        uint32 confidence,
        bytes32 traceHash,
        string calldata traceCid
    ) external returns (uint256 id) {
        require(probability <= PROBABILITY_SCALE, "RR: prob OOB");
        require(confidence <= PROBABILITY_SCALE, "RR: conf OOB");
        require(traceHash != bytes32(0), "RR: empty hash");
        require(bytes(traceCid).length > 0, "RR: empty cid");

        id = ++totalReceipts;
        emit Receipt(
            id,
            msg.sender,
            consumer,
            marketId,
            probability,
            confidence,
            traceHash,
            traceCid,
            uint64(block.timestamp)
        );
    }

    /// @notice Batched variant — used by the agent loop to amortise per-receipt overhead.
    /// @dev    Arrays must be parallel and non-empty.
    function publishBatch(
        address[] calldata consumers,
        bytes32[] calldata marketIds,
        uint32[] calldata probabilities,
        uint32[] calldata confidences,
        bytes32[] calldata traceHashes,
        string[] calldata traceCids
    ) external returns (uint256 firstId, uint256 lastId) {
        uint256 len = consumers.length;
        require(len > 0, "RR: empty batch");
        require(
            len == marketIds.length &&
                len == probabilities.length &&
                len == confidences.length &&
                len == traceHashes.length &&
                len == traceCids.length,
            "RR: length mismatch"
        );

        firstId = totalReceipts + 1;
        for (uint256 i = 0; i < len; ++i) {
            require(probabilities[i] <= PROBABILITY_SCALE, "RR: prob OOB");
            require(confidences[i] <= PROBABILITY_SCALE, "RR: conf OOB");
            require(traceHashes[i] != bytes32(0), "RR: empty hash");
            require(bytes(traceCids[i]).length > 0, "RR: empty cid");

            uint256 id = ++totalReceipts;
            emit Receipt(
                id,
                msg.sender,
                consumers[i],
                marketIds[i],
                probabilities[i],
                confidences[i],
                traceHashes[i],
                traceCids[i],
                uint64(block.timestamp)
            );
        }
        lastId = totalReceipts;
    }
}
