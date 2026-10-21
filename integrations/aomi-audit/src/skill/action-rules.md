# Contract usage
The only allowed write is publishV2 on the configured ReceiptRegistryV2, native value 0,
sent from the configured auditor wallet. The registry records that wallet as publisher,
which is how readers tell audited receipts apart. Do not reconstruct calldata, trace
hashes, Merkle roots or traces yourself, and do not edit a fetched result.
