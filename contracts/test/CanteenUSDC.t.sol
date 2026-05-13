// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";
import {CanteenUSDC} from "../src/CanteenUSDC.sol";

/// @notice Minimal mock that implements only the bits of USDC the wrapper exercises.
contract MockUSDC {
    string public constant name = "USD Coin";
    string public constant symbol = "USDC";
    uint8 public constant decimals = 6;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function mint(address to, uint256 amount) external {
        totalSupply += amount;
        balanceOf[to] += amount;
        emit Transfer(address(0), to, amount);
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transfer(address to, uint256 value) external returns (bool) {
        require(balanceOf[msg.sender] >= value, "mock: balance");
        balanceOf[msg.sender] -= value;
        balanceOf[to] += value;
        emit Transfer(msg.sender, to, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        require(allowance[from][msg.sender] >= value, "mock: allowance");
        require(balanceOf[from] >= value, "mock: balance");
        allowance[from][msg.sender] -= value;
        balanceOf[from] -= value;
        balanceOf[to] += value;
        emit Transfer(from, to, value);
        return true;
    }
}

contract CanteenUSDCTest is Test {
    MockUSDC internal usdc;
    CanteenUSDC internal cusdc;
    address internal alice = address(0xA11CE);
    address internal bob = address(0xB0B);

    function setUp() public {
        usdc = new MockUSDC();
        cusdc = new CanteenUSDC(address(usdc));
        usdc.mint(alice, 1_000 * 1e6);
        usdc.mint(bob, 100 * 1e6);
    }

    function test_Metadata() public view {
        assertEq(cusdc.name(), "Canteen USDC");
        assertEq(cusdc.symbol(), "cUSDC");
        assertEq(uint256(cusdc.decimals()), 6);
        assertEq(cusdc.underlying(), address(usdc));
        assertEq(cusdc.totalSupply(), 0);
    }

    function test_WrapMintsOneToOne() public {
        vm.startPrank(alice);
        usdc.approve(address(cusdc), 100 * 1e6);
        bool ok = cusdc.wrap(100 * 1e6);
        vm.stopPrank();

        assertTrue(ok);
        assertEq(cusdc.balanceOf(alice), 100 * 1e6, "alice cUSDC");
        assertEq(cusdc.totalSupply(), 100 * 1e6, "total");
        assertEq(usdc.balanceOf(address(cusdc)), 100 * 1e6, "wrapper holds USDC");
        assertEq(usdc.balanceOf(alice), 900 * 1e6, "alice USDC -100");
    }

    function test_UnwrapBurnsAndReturns() public {
        vm.startPrank(alice);
        usdc.approve(address(cusdc), 100 * 1e6);
        cusdc.wrap(100 * 1e6);
        cusdc.unwrap(40 * 1e6);
        vm.stopPrank();

        assertEq(cusdc.balanceOf(alice), 60 * 1e6);
        assertEq(cusdc.totalSupply(), 60 * 1e6);
        assertEq(usdc.balanceOf(alice), 940 * 1e6, "alice USDC +40 back");
        assertEq(usdc.balanceOf(address(cusdc)), 60 * 1e6, "wrapper still holds 60");
    }

    function test_WrapRejectsZero() public {
        vm.prank(alice);
        vm.expectRevert(bytes("cUSDC: zero amount"));
        cusdc.wrap(0);
    }

    function test_WrapFailsWithoutAllowance() public {
        vm.prank(alice);
        vm.expectRevert(); // mock USDC reverts on insufficient allowance
        cusdc.wrap(50 * 1e6);
    }

    function test_UnwrapRejectsOverBalance() public {
        vm.startPrank(alice);
        usdc.approve(address(cusdc), 10 * 1e6);
        cusdc.wrap(10 * 1e6);
        vm.expectRevert(bytes("cUSDC: balance"));
        cusdc.unwrap(20 * 1e6);
        vm.stopPrank();
    }

    function test_TransferAndTransferFrom() public {
        vm.startPrank(alice);
        usdc.approve(address(cusdc), 100 * 1e6);
        cusdc.wrap(100 * 1e6);
        cusdc.transfer(bob, 30 * 1e6);
        vm.stopPrank();

        assertEq(cusdc.balanceOf(alice), 70 * 1e6);
        assertEq(cusdc.balanceOf(bob), 30 * 1e6);

        vm.prank(bob);
        cusdc.approve(alice, 10 * 1e6);

        vm.prank(alice);
        cusdc.transferFrom(bob, alice, 10 * 1e6);

        assertEq(cusdc.balanceOf(bob), 20 * 1e6);
        assertEq(cusdc.balanceOf(alice), 80 * 1e6);
        assertEq(cusdc.allowance(bob, alice), 0);
    }

    function test_InfiniteAllowanceIsNotDecremented() public {
        vm.startPrank(alice);
        usdc.approve(address(cusdc), 100 * 1e6);
        cusdc.wrap(100 * 1e6);
        cusdc.approve(bob, type(uint256).max);
        vm.stopPrank();

        vm.prank(bob);
        cusdc.transferFrom(alice, bob, 25 * 1e6);

        assertEq(cusdc.allowance(alice, bob), type(uint256).max, "max allowance untouched");
        assertEq(cusdc.balanceOf(bob), 25 * 1e6);
    }

    function test_ConstructorRejectsZero() public {
        vm.expectRevert(bytes("cUSDC: zero underlying"));
        new CanteenUSDC(address(0));
    }

    function testFuzz_WrapRoundTrip(uint96 amount) public {
        vm.assume(amount > 0 && amount <= 500 * 1e6);
        vm.startPrank(alice);
        usdc.approve(address(cusdc), amount);
        cusdc.wrap(amount);
        cusdc.unwrap(amount);
        vm.stopPrank();
        assertEq(cusdc.balanceOf(alice), 0);
        assertEq(cusdc.totalSupply(), 0);
        assertEq(usdc.balanceOf(alice), 1_000 * 1e6, "fully unwrapped");
    }
}
