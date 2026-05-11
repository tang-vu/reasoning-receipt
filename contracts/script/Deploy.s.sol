// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {ReceiptRegistry} from "../src/ReceiptRegistry.sol";

/// @notice Deploys ReceiptRegistry to Arc testnet. Run with:
///         forge script script/Deploy.s.sol \
///           --rpc-url $RPC --broadcast --private-key $DEPLOYER_PRIVATE_KEY
contract Deploy is Script {
    function run() external returns (ReceiptRegistry registry) {
        uint256 pk = vm.envUint("DEPLOYER_PRIVATE_KEY");
        vm.startBroadcast(pk);
        registry = new ReceiptRegistry();
        vm.stopBroadcast();
        console2.log("ReceiptRegistry deployed at", address(registry));
        console2.log("Total receipts at deploy", registry.totalReceipts());
    }
}
