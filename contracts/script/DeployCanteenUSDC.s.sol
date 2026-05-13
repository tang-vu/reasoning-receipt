// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Script, console2} from "forge-std/Script.sol";
import {CanteenUSDC} from "../src/CanteenUSDC.sol";

/// @notice Deploys CanteenUSDC bound to the Arc Testnet USDC at
///         0x3600000000000000000000000000000000000000.
///
///         forge script script/DeployCanteenUSDC.s.sol \
///           --rpc-url $RPC --broadcast --private-key $DEPLOYER_PRIVATE_KEY
contract DeployCanteenUSDC is Script {
    address constant ARC_TESTNET_USDC = 0x3600000000000000000000000000000000000000;

    function run() external returns (CanteenUSDC cusdc) {
        uint256 pk = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address underlying = vm.envOr("CUSDC_UNDERLYING", ARC_TESTNET_USDC);
        vm.startBroadcast(pk);
        cusdc = new CanteenUSDC(underlying);
        vm.stopBroadcast();
        console2.log("CanteenUSDC deployed at", address(cusdc));
        console2.log("underlying USDC", underlying);
    }
}
