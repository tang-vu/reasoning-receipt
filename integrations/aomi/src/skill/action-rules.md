# Contract usage
The only allowed write is transfer(address,uint256) on the configured USDC contract,
native value 0. Amounts are integer strings in the token's base units; on Arc testnet
USDC has 6 decimals, so 10000 = 0.01 USDC. Arc's native gas balance uses 18 decimals;
do not confuse the two. No approve, no transferFrom, no other recipient, no split or
partial amounts. Do not reconstruct calldata, trace hashes or receipts yourself.
