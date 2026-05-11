// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";
import {ReceiptRegistry} from "../src/ReceiptRegistry.sol";

contract ReceiptRegistryTest is Test {
    ReceiptRegistry internal registry;
    address internal publisher = address(0xBEEF);
    address internal consumer = address(0xCAFE);

    // Receipt event is referenced via `emit ReceiptRegistry.Receipt(...)` below.
    // Not re-declared in this contract to avoid colliding with forge-std's
    // `struct Receipt` in StdCheats.

    function setUp() public {
        registry = new ReceiptRegistry();
    }

    function test_PublishEmitsEvent() public {
        bytes32 marketId = keccak256("polymarket:0xfeed");
        bytes32 traceHash = keccak256("trace");
        string memory cid = "ar://abc123";

        vm.warp(1_715_000_000);
        vm.prank(publisher);
        vm.expectEmit(true, true, true, true);
        emit ReceiptRegistry.Receipt(
            1, publisher, consumer, marketId, 612345, 850000, traceHash, cid, 1_715_000_000
        );
        uint256 id = registry.publish(consumer, marketId, 612345, 850000, traceHash, cid);

        assertEq(id, 1, "first id is 1");
        assertEq(registry.totalReceipts(), 1, "counter incremented");
    }

    function test_PublishRejectsOutOfBoundProbability() public {
        vm.prank(publisher);
        vm.expectRevert(bytes("RR: prob OOB"));
        registry.publish(consumer, bytes32("m"), 1_000_001, 500_000, keccak256("h"), "ar://x");
    }

    function test_PublishRejectsOutOfBoundConfidence() public {
        vm.prank(publisher);
        vm.expectRevert(bytes("RR: conf OOB"));
        registry.publish(consumer, bytes32("m"), 500_000, 1_000_001, keccak256("h"), "ar://x");
    }

    function test_PublishRejectsEmptyHash() public {
        vm.prank(publisher);
        vm.expectRevert(bytes("RR: empty hash"));
        registry.publish(consumer, bytes32("m"), 500_000, 500_000, bytes32(0), "ar://x");
    }

    function test_PublishRejectsEmptyCid() public {
        vm.prank(publisher);
        vm.expectRevert(bytes("RR: empty cid"));
        registry.publish(consumer, bytes32("m"), 500_000, 500_000, keccak256("h"), "");
    }

    function test_BatchPublishMonotonic() public {
        uint256 n = 4;
        address[] memory consumers = new address[](n);
        bytes32[] memory marketIds = new bytes32[](n);
        uint32[] memory probs = new uint32[](n);
        uint32[] memory confs = new uint32[](n);
        bytes32[] memory hashes = new bytes32[](n);
        string[] memory cids = new string[](n);
        for (uint256 i = 0; i < n; ++i) {
            consumers[i] = consumer;
            marketIds[i] = keccak256(abi.encode("market", i));
            probs[i] = uint32(100_000 + i * 100_000);
            confs[i] = 700_000;
            hashes[i] = keccak256(abi.encode("trace", i));
            cids[i] = "ar://test";
        }
        vm.prank(publisher);
        (uint256 firstId, uint256 lastId) = registry.publishBatch(
            consumers,
            marketIds,
            probs,
            confs,
            hashes,
            cids
        );
        assertEq(firstId, 1);
        assertEq(lastId, n);
        assertEq(registry.totalReceipts(), n);
    }

    function test_BatchRejectsLengthMismatch() public {
        address[] memory consumers = new address[](2);
        bytes32[] memory marketIds = new bytes32[](1);
        uint32[] memory probs = new uint32[](2);
        uint32[] memory confs = new uint32[](2);
        bytes32[] memory hashes = new bytes32[](2);
        string[] memory cids = new string[](2);
        vm.prank(publisher);
        vm.expectRevert(bytes("RR: length mismatch"));
        registry.publishBatch(consumers, marketIds, probs, confs, hashes, cids);
    }

    function testFuzz_PublishAccepts(uint32 prob, uint32 conf) public {
        vm.assume(prob <= 1_000_000 && conf <= 1_000_000);
        vm.prank(publisher);
        uint256 id = registry.publish(
            consumer,
            keccak256("fuzz"),
            prob,
            conf,
            keccak256("h"),
            "ar://fuzz"
        );
        assertEq(id, 1);
    }
}
