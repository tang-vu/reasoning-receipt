"""cusdc-cli.py — wrap / unwrap USDC into CanteenUSDC on Arc Testnet.

Implements the Part 1 tutorial flow against the deployed CanteenUSDC wrapper
at 0x7473d0db92F77aA89F19A2D74174D14D14CBD3E1 (or wherever `CUSDC_ADDRESS`
points). The wrapper is bound 1:1 to the Arc Testnet USDC at
0x3600000000000000000000000000000000000000.

Subcommands:
    wrap   <amount>   approve USDC then wrap into cUSDC
    unwrap <amount>   burn cUSDC and return USDC
    balance           print USDC + cUSDC for the deployer wallet

`<amount>` is a decimal USDC value (e.g. 1.5). The script converts to
micro-units (6 decimals) before sending the call.

Reads DEPLOYER_PRIVATE_KEY + RPC from .env.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from eth_account import Account
from web3 import HTTPProvider, Web3
from web3.middleware import SignAndSendRawMiddlewareBuilder

logger = logging.getLogger("rr.cusdc")

ARC_USDC = "0x3600000000000000000000000000000000000000"
DEFAULT_CUSDC = os.getenv("CUSDC_ADDRESS", "0x7473d0db92F77aA89F19A2D74174D14D14CBD3E1")

_ABI_ERC20 = [
    {
        "type": "function", "name": "approve", "stateMutability": "nonpayable",
        "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function", "name": "balanceOf", "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function", "name": "allowance", "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}, {"name": "spender", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]

_ABI_WRAPPER = _ABI_ERC20 + [
    {
        "type": "function", "name": "wrap", "stateMutability": "nonpayable",
        "inputs": [{"name": "amount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function", "name": "unwrap", "stateMutability": "nonpayable",
        "inputs": [{"name": "amount", "type": "uint256"}],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "type": "function", "name": "underlying", "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "address"}],
    },
    {
        "type": "function", "name": "totalSupply", "stateMutability": "view",
        "inputs": [],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def _connect():
    load_dotenv()
    pk = os.getenv("DEPLOYER_PRIVATE_KEY")
    rpc = os.getenv("RPC")
    if not pk or not rpc:
        raise SystemExit("DEPLOYER_PRIVATE_KEY + RPC must be set in .env")
    acct = Account.from_key(pk)
    w3 = Web3(HTTPProvider(rpc, request_kwargs={"timeout": 20}))
    w3.middleware_onion.inject(SignAndSendRawMiddlewareBuilder.build(acct), layer=0)
    w3.eth.default_account = acct.address
    return w3, acct


def cmd_balance(args) -> int:
    w3, acct = _connect()
    addr = args.address or acct.address
    usdc = w3.eth.contract(address=Web3.to_checksum_address(ARC_USDC), abi=_ABI_ERC20)
    cusdc = w3.eth.contract(address=Web3.to_checksum_address(args.cusdc), abi=_ABI_WRAPPER)
    usdc_bal = usdc.functions.balanceOf(addr).call()
    cusdc_bal = cusdc.functions.balanceOf(addr).call()
    total = cusdc.functions.totalSupply().call()
    print(f"address     : {addr}")
    print(f"USDC        : {usdc_bal / 1e6:>12.6f}  ({usdc_bal} micro)")
    print(f"cUSDC       : {cusdc_bal / 1e6:>12.6f}  ({cusdc_bal} micro)")
    print(f"cUSDC supply: {total / 1e6:>12.6f}  ({total} micro)")
    return 0


def cmd_wrap(args) -> int:
    w3, acct = _connect()
    amount = int(round(args.amount * 1_000_000))
    cusdc_addr = Web3.to_checksum_address(args.cusdc)
    usdc = w3.eth.contract(address=Web3.to_checksum_address(ARC_USDC), abi=_ABI_ERC20)
    cusdc = w3.eth.contract(address=cusdc_addr, abi=_ABI_WRAPPER)

    usdc_bal = usdc.functions.balanceOf(acct.address).call()
    if usdc_bal < amount:
        print(f"insufficient USDC: have {usdc_bal / 1e6}, need {args.amount}", file=sys.stderr)
        return 2

    cur_allowance = usdc.functions.allowance(acct.address, cusdc_addr).call()
    if cur_allowance < amount:
        print(f"1/2 approve {args.amount} USDC -> CanteenUSDC ...")
        tx_h = usdc.functions.approve(cusdc_addr, amount).transact({"from": acct.address})
        w3.eth.wait_for_transaction_receipt(tx_h, timeout=120)
        print(f"  approve tx: 0x{tx_h.hex() if isinstance(tx_h, bytes) else tx_h}")
    else:
        print("approve: skipping (allowance already sufficient)")

    print(f"2/2 wrap {args.amount} USDC ...")
    tx_h = cusdc.functions.wrap(amount).transact({"from": acct.address})
    rcpt = w3.eth.wait_for_transaction_receipt(tx_h, timeout=120)
    h = tx_h.hex() if isinstance(tx_h, bytes) else tx_h
    print(f"  wrap tx: 0x{h}")
    print(f"  block:   {rcpt['blockNumber']}")
    print(f"  explorer: https://testnet.arcscan.app/tx/0x{h}")
    return 0


def cmd_unwrap(args) -> int:
    w3, acct = _connect()
    amount = int(round(args.amount * 1_000_000))
    cusdc = w3.eth.contract(address=Web3.to_checksum_address(args.cusdc), abi=_ABI_WRAPPER)

    bal = cusdc.functions.balanceOf(acct.address).call()
    if bal < amount:
        print(f"insufficient cUSDC: have {bal / 1e6}, need {args.amount}", file=sys.stderr)
        return 2

    print(f"unwrap {args.amount} cUSDC ...")
    tx_h = cusdc.functions.unwrap(amount).transact({"from": acct.address})
    rcpt = w3.eth.wait_for_transaction_receipt(tx_h, timeout=120)
    h = tx_h.hex() if isinstance(tx_h, bytes) else tx_h
    print(f"  unwrap tx: 0x{h}")
    print(f"  block:     {rcpt['blockNumber']}")
    print(f"  explorer:  https://testnet.arcscan.app/tx/0x{h}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CanteenUSDC wrap / unwrap CLI on Arc Testnet.")
    parser.add_argument(
        "--cusdc",
        default=DEFAULT_CUSDC,
        help="CanteenUSDC contract address (default: env CUSDC_ADDRESS or deployed instance)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_bal = sub.add_parser("balance", help="print USDC + cUSDC for a wallet")
    p_bal.add_argument("--address", help="defaults to DEPLOYER_PRIVATE_KEY's address")
    p_bal.set_defaults(func=cmd_balance)

    p_wrap = sub.add_parser("wrap", help="approve + wrap USDC into cUSDC")
    p_wrap.add_argument("amount", type=float, help="USDC amount (e.g. 1.5)")
    p_wrap.set_defaults(func=cmd_wrap)

    p_unw = sub.add_parser("unwrap", help="burn cUSDC + return USDC")
    p_unw.add_argument("amount", type=float, help="cUSDC amount (e.g. 1.5)")
    p_unw.set_defaults(func=cmd_unwrap)

    args = parser.parse_args(argv)
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper(), format="%(asctime)s %(levelname)-7s %(message)s")
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
