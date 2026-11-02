# Enforcement boundaries
The app guard limits writes to the configured chain, the USDC contract and the transfer
selector. It does not check transfer arguments. The app decodes the prepared calldata and
refuses to stage it unless recipient and amount equal the deployment. The API refuses to
prepare a transfer whose simulation fails, and the host simulates again after staging.
Wallet approval is the user's own; prompts are not enforcement.
The API, not the model, enforces the audit gate: it prepares nothing unless the audit is
published, so a failed or inconclusive audit blocks payment. The audited trace is never edited. Verification checks the chain id, a successful
finalized canonical receipt, and exactly one matching Transfer event from the prepared
wallet. Each audited trace and each transaction hash can settle at most once. A plain ERC-20
transfer cannot itself refuse a second payment, so never resubmit after an uncertain
broadcast: verify the hash you have.
