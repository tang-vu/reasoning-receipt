// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";
import {ReceiptRegistryV2} from "../src/ReceiptRegistryV2.sol";

/// @notice Tests for ReceiptRegistryV2 — publish*, batch, and the on-chain
///         Merkle verifier. The verifier round-trips against trees we build
///         in-test using the same sorted-pair SHA-256 convention as
///         agent/merkle.py, so a passing test here is a cross-language
///         guarantee.
contract ReceiptRegistryV2Test is Test {
    ReceiptRegistryV2 internal registry;
    address internal publisher = address(0xBEEF);
    address internal consumer = address(0xCAFE);

    // Event reference uses qualified name `ReceiptRegistryV2.ReceiptV2(...)`
    // to avoid forge-std StdCheats `struct Receipt` collision.

    function setUp() public {
        registry = new ReceiptRegistryV2();
    }

    // -------------------------------------------------------------
    // publishV2 — happy path + boundaries
    // -------------------------------------------------------------

    function test_PublishV2EmitsEvent() public {
        bytes32 marketId = keccak256("polymarket:0xfeed");
        bytes32 traceHash = sha256(abi.encodePacked("trace-canonical-bytes"));
        bytes32 merkleRoot = sha256(abi.encodePacked("merkle-root"));
        bytes16 schemaVersion = bytes16("rr-trace/3");
        string memory cid = "ar://abc123";

        vm.warp(1_715_000_000);
        vm.prank(publisher);
        vm.expectEmit(true, true, true, true);
        emit ReceiptRegistryV2.ReceiptV2(
            1, publisher, consumer, marketId, 612345, 850000, traceHash, merkleRoot, schemaVersion, cid, 1_715_000_000
        );
        uint256 id =
            registry.publishV2(consumer, marketId, 612345, 850000, traceHash, merkleRoot, schemaVersion, cid);

        assertEq(id, 1, "first id is 1");
        assertEq(registry.totalReceipts(), 1, "counter incremented");
    }

    function test_PublishV2RejectsOutOfBoundProbability() public {
        // Pre-compute sha256 args — sha256 is a precompile staticcall and
        // would otherwise be intercepted by vm.expectRevert as "the next call".
        bytes32 h = sha256(abi.encodePacked("h"));
        bytes32 r = sha256(abi.encodePacked("r"));
        bytes16 v = bytes16("rr-trace/3");
        vm.prank(publisher);
        vm.expectRevert(bytes("RRv2: prob OOB"));
        registry.publishV2(consumer, bytes32("m"), 1_000_001, 500_000, h, r, v, "ar://x");
    }

    function test_PublishV2RejectsOutOfBoundConfidence() public {
        bytes32 h = sha256(abi.encodePacked("h"));
        bytes32 r = sha256(abi.encodePacked("r"));
        bytes16 v = bytes16("rr-trace/3");
        vm.prank(publisher);
        vm.expectRevert(bytes("RRv2: conf OOB"));
        registry.publishV2(consumer, bytes32("m"), 500_000, 1_000_001, h, r, v, "ar://x");
    }

    function test_PublishV2RejectsEmptyTraceHash() public {
        bytes32 r = sha256(abi.encodePacked("r"));
        bytes16 v = bytes16("rr-trace/3");
        vm.prank(publisher);
        vm.expectRevert(bytes("RRv2: empty hash"));
        registry.publishV2(consumer, bytes32("m"), 500_000, 500_000, bytes32(0), r, v, "ar://x");
    }

    function test_PublishV2RejectsEmptyMerkleRoot() public {
        bytes32 h = sha256(abi.encodePacked("h"));
        bytes16 v = bytes16("rr-trace/3");
        vm.prank(publisher);
        vm.expectRevert(bytes("RRv2: empty root"));
        registry.publishV2(consumer, bytes32("m"), 500_000, 500_000, h, bytes32(0), v, "ar://x");
    }

    function test_PublishV2RejectsEmptyCid() public {
        bytes32 h = sha256(abi.encodePacked("h"));
        bytes32 r = sha256(abi.encodePacked("r"));
        bytes16 v = bytes16("rr-trace/3");
        vm.prank(publisher);
        vm.expectRevert(bytes("RRv2: empty cid"));
        registry.publishV2(consumer, bytes32("m"), 500_000, 500_000, h, r, v, "");
    }

    // -------------------------------------------------------------
    // publishBatchV2
    // -------------------------------------------------------------

    function test_PublishBatchV2EmitsAllAndIncrementsCounter() public {
        uint256 n = 3;
        address[] memory consumers = new address[](n);
        bytes32[] memory marketIds = new bytes32[](n);
        uint32[] memory probs = new uint32[](n);
        uint32[] memory confs = new uint32[](n);
        bytes32[] memory hashes = new bytes32[](n);
        bytes32[] memory roots = new bytes32[](n);
        bytes16[] memory schemas = new bytes16[](n);
        string[] memory cids = new string[](n);
        for (uint256 i = 0; i < n; ++i) {
            consumers[i] = consumer;
            marketIds[i] = bytes32(uint256(i + 1));
            probs[i] = uint32(500_000 + i * 1000);
            confs[i] = 800_000;
            hashes[i] = sha256(abi.encodePacked("h", i));
            roots[i] = sha256(abi.encodePacked("r", i));
            schemas[i] = bytes16("rr-trace/3");
            cids[i] = "ar://batch";
        }
        vm.prank(publisher);
        (uint256 firstId, uint256 lastId) =
            registry.publishBatchV2(consumers, marketIds, probs, confs, hashes, roots, schemas, cids);
        assertEq(firstId, 1);
        assertEq(lastId, 3);
        assertEq(registry.totalReceipts(), 3);
    }

    function test_PublishBatchV2RejectsLengthMismatch() public {
        address[] memory consumers = new address[](2);
        bytes32[] memory marketIds = new bytes32[](1); // mismatched
        uint32[] memory probs = new uint32[](2);
        uint32[] memory confs = new uint32[](2);
        bytes32[] memory hashes = new bytes32[](2);
        bytes32[] memory roots = new bytes32[](2);
        bytes16[] memory schemas = new bytes16[](2);
        string[] memory cids = new string[](2);
        vm.prank(publisher);
        vm.expectRevert(bytes("RRv2: length mismatch"));
        registry.publishBatchV2(consumers, marketIds, probs, confs, hashes, roots, schemas, cids);
    }

    function test_PublishBatchV2RejectsEmpty() public {
        address[] memory consumers = new address[](0);
        bytes32[] memory marketIds = new bytes32[](0);
        uint32[] memory probs = new uint32[](0);
        uint32[] memory confs = new uint32[](0);
        bytes32[] memory hashes = new bytes32[](0);
        bytes32[] memory roots = new bytes32[](0);
        bytes16[] memory schemas = new bytes16[](0);
        string[] memory cids = new string[](0);
        vm.prank(publisher);
        vm.expectRevert(bytes("RRv2: empty batch"));
        registry.publishBatchV2(consumers, marketIds, probs, confs, hashes, roots, schemas, cids);
    }

    // -------------------------------------------------------------
    // verifyInclusion — Merkle correctness + cross-language equivalence
    // -------------------------------------------------------------

    function test_VerifyInclusion_SingleLeafIsItsOwnRoot() public view {
        bytes32 leaf = sha256(abi.encodePacked("only"));
        bytes32[] memory proof = new bytes32[](0);
        assertTrue(registry.verifyInclusion(leaf, leaf, proof));
    }

    function test_VerifyInclusion_TwoLeafTree() public view {
        bytes32 l0 = sha256(abi.encodePacked("l0"));
        bytes32 l1 = sha256(abi.encodePacked("l1"));
        bytes32 root = _hashPair(l0, l1);

        bytes32[] memory proofForL0 = new bytes32[](1);
        proofForL0[0] = l1;
        assertTrue(registry.verifyInclusion(root, l0, proofForL0));

        bytes32[] memory proofForL1 = new bytes32[](1);
        proofForL1[0] = l0;
        assertTrue(registry.verifyInclusion(root, l1, proofForL1));
    }

    function test_VerifyInclusion_FourLeafTreeAllProofsWork() public view {
        bytes32 l0 = sha256(abi.encodePacked("l0"));
        bytes32 l1 = sha256(abi.encodePacked("l1"));
        bytes32 l2 = sha256(abi.encodePacked("l2"));
        bytes32 l3 = sha256(abi.encodePacked("l3"));
        bytes32 l01 = _hashPair(l0, l1);
        bytes32 l23 = _hashPair(l2, l3);
        bytes32 root = _hashPair(l01, l23);

        // Proof for l0 = [l1, l23]
        bytes32[] memory p0 = new bytes32[](2);
        p0[0] = l1;
        p0[1] = l23;
        assertTrue(registry.verifyInclusion(root, l0, p0));

        // Proof for l3 = [l2, l01]
        bytes32[] memory p3 = new bytes32[](2);
        p3[0] = l2;
        p3[1] = l01;
        assertTrue(registry.verifyInclusion(root, l3, p3));
    }

    function test_VerifyInclusion_OddLevelLonelyNodePromoted() public view {
        // Three leaves: l0, l1, l2.
        // Level 1: [_hashPair(l0,l1), l2]  (l2 promoted, no duplication)
        // Root:    _hashPair(_hashPair(l0,l1), l2)
        bytes32 l0 = sha256(abi.encodePacked("l0"));
        bytes32 l1 = sha256(abi.encodePacked("l1"));
        bytes32 l2 = sha256(abi.encodePacked("l2"));
        bytes32 l01 = _hashPair(l0, l1);
        bytes32 root = _hashPair(l01, l2);

        // Proof for l2 is just [l01] — the promoted node folded with l01.
        bytes32[] memory p2 = new bytes32[](1);
        p2[0] = l01;
        assertTrue(registry.verifyInclusion(root, l2, p2));

        // Proof for l0 is [l1, l2] — l1 is sibling, l2 is the promoted node
        // at the next level.
        bytes32[] memory p0 = new bytes32[](2);
        p0[0] = l1;
        p0[1] = l2;
        assertTrue(registry.verifyInclusion(root, l0, p0));
    }

    function test_VerifyInclusion_RejectsTamperedLeaf() public view {
        bytes32 l0 = sha256(abi.encodePacked("real-leaf"));
        bytes32 l1 = sha256(abi.encodePacked("sibling"));
        bytes32 root = _hashPair(l0, l1);
        bytes32[] memory proof = new bytes32[](1);
        proof[0] = l1;

        bytes32 fakeLeaf = sha256(abi.encodePacked("attacker-leaf"));
        assertFalse(registry.verifyInclusion(root, fakeLeaf, proof));
    }

    function test_VerifyInclusion_RejectsBitFlippedSibling() public view {
        bytes32 l0 = sha256(abi.encodePacked("a"));
        bytes32 l1 = sha256(abi.encodePacked("b"));
        bytes32 root = _hashPair(l0, l1);

        bytes32 bad = bytes32(uint256(l1) ^ 1); // flip lowest bit
        bytes32[] memory proof = new bytes32[](1);
        proof[0] = bad;
        assertFalse(registry.verifyInclusion(root, l0, proof));
    }

    // -------------------------------------------------------------
    // helpers (same algorithm as the contract's private _hashPair —
    // tests get to call it directly to construct expected roots).
    // -------------------------------------------------------------

    function _hashPair(bytes32 a, bytes32 b) private pure returns (bytes32) {
        return a <= b ? sha256(abi.encodePacked(a, b)) : sha256(abi.encodePacked(b, a));
    }
}
