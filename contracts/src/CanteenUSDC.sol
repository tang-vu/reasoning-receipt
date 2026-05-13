// SPDX-License-Identifier: MIT
pragma solidity ^0.8.26;

/// @title CanteenUSDC (cUSDC)
/// @notice A minimal 1:1 ERC-20 wrapper around USDC on Arc Testnet.
///         `wrap(amount)` pulls `amount` USDC from the caller and mints the
///         caller `amount` cUSDC. `unwrap(amount)` burns the caller's cUSDC
///         and returns `amount` USDC.
/// @dev    No fees, no admin, no upgrades. Pure ERC-20 with two extension
///         functions and two extra events. Decimals match the underlying
///         (USDC = 6).
contract CanteenUSDC {
    // ----- ERC-20 standard ---------------------------------------------

    string public constant name = "Canteen USDC";
    string public constant symbol = "cUSDC";
    uint8 public constant decimals = 6;
    uint256 public totalSupply;
    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) public allowance;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    // ----- Wrapper additions -------------------------------------------

    /// @notice The underlying USDC contract this wrapper is bound to.
    address public immutable underlying;

    /// @notice Emitted when USDC is wrapped into cUSDC.
    event Wrap(address indexed account, uint256 amount);

    /// @notice Emitted when cUSDC is unwrapped back into USDC.
    event Unwrap(address indexed account, uint256 amount);

    constructor(address underlying_) {
        require(underlying_ != address(0), "cUSDC: zero underlying");
        underlying = underlying_;
    }

    // ----- ERC-20 transfers --------------------------------------------

    function transfer(address to, uint256 value) external returns (bool) {
        _transfer(msg.sender, to, value);
        return true;
    }

    function approve(address spender, uint256 value) external returns (bool) {
        allowance[msg.sender][spender] = value;
        emit Approval(msg.sender, spender, value);
        return true;
    }

    function transferFrom(address from, address to, uint256 value) external returns (bool) {
        uint256 current = allowance[from][msg.sender];
        if (current != type(uint256).max) {
            require(current >= value, "cUSDC: allowance");
            unchecked {
                allowance[from][msg.sender] = current - value;
            }
        }
        _transfer(from, to, value);
        return true;
    }

    function _transfer(address from, address to, uint256 value) internal {
        require(to != address(0), "cUSDC: to zero");
        uint256 bal = balanceOf[from];
        require(bal >= value, "cUSDC: balance");
        unchecked {
            balanceOf[from] = bal - value;
            balanceOf[to] += value;
        }
        emit Transfer(from, to, value);
    }

    // ----- Wrap / Unwrap -----------------------------------------------

    /// @notice Pull `amount` of the underlying USDC from `msg.sender` and mint
    ///         `amount` cUSDC. Caller must have approved this contract for at
    ///         least `amount` of USDC beforehand.
    function wrap(uint256 amount) external returns (bool) {
        require(amount > 0, "cUSDC: zero amount");
        // ERC-20 transferFrom on the underlying. We don't trust the return
        // value alone — some legacy tokens don't return a bool — so we also
        // check via balance delta is overkill; here we assume well-behaved
        // USDC (which is the case on Arc / Sepolia / mainnet).
        bool ok = _safeTransferFrom(underlying, msg.sender, address(this), amount);
        require(ok, "cUSDC: pull failed");

        totalSupply += amount;
        unchecked {
            balanceOf[msg.sender] += amount;
        }
        emit Transfer(address(0), msg.sender, amount);
        emit Wrap(msg.sender, amount);
        return true;
    }

    /// @notice Burn `amount` of caller's cUSDC and return `amount` of the
    ///         underlying USDC to the caller.
    function unwrap(uint256 amount) external returns (bool) {
        require(amount > 0, "cUSDC: zero amount");
        uint256 bal = balanceOf[msg.sender];
        require(bal >= amount, "cUSDC: balance");
        unchecked {
            balanceOf[msg.sender] = bal - amount;
            totalSupply -= amount;
        }
        emit Transfer(msg.sender, address(0), amount);
        emit Unwrap(msg.sender, amount);

        bool ok = _safeTransfer(underlying, msg.sender, amount);
        require(ok, "cUSDC: return failed");
        return true;
    }

    // ----- internal ERC-20 helpers (avoid SafeERC20 dep) ----------------

    function _safeTransfer(address token, address to, uint256 value) internal returns (bool) {
        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(0xa9059cbb, to, value) // transfer(address,uint256)
        );
        return success && (data.length == 0 || abi.decode(data, (bool)));
    }

    function _safeTransferFrom(address token, address from, address to, uint256 value)
        internal
        returns (bool)
    {
        (bool success, bytes memory data) = token.call(
            abi.encodeWithSelector(0x23b872dd, from, to, value) // transferFrom(address,address,uint256)
        );
        return success && (data.length == 0 || abi.decode(data, (bool)));
    }
}
