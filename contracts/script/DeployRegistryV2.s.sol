// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {ReceiptRegistryV2} from "../src/ReceiptRegistryV2.sol";

/// @notice Deploys ReceiptRegistryV2 to Arc testnet. Additive to V1 — does NOT
///         touch the existing ReceiptRegistry address. Run with:
///
///           forge script script/DeployRegistryV2.s.sol \
///             --rpc-url $RPC --broadcast --private-key $DEPLOYER_PRIVATE_KEY
///
///         After deploy, write the printed address to .env as
///         RECEIPT_REGISTRY_V2_ADDRESS so the agent loop can dual-emit on V1 + V2.
contract DeployRegistryV2 is Script {
    function run() external returns (ReceiptRegistryV2 registry) {
        uint256 pk = vm.envUint("DEPLOYER_PRIVATE_KEY");
        vm.startBroadcast(pk);
        registry = new ReceiptRegistryV2();
        vm.stopBroadcast();
        console2.log("ReceiptRegistryV2 deployed at", address(registry));
        console2.log("Total receipts at deploy", registry.totalReceipts());
    }
}
