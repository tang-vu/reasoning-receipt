# Enforcement boundaries
The app guard limits writes to the configured chain, the registry contract and the
publishV2 selector. The app decodes every word of the sealed calldata and refuses to
stage it unless it publishes exactly the sealed trace hash, Merkle root, CID, market and
probabilities with no consumer. The host simulates after staging. Wallet approval is
the user's own; prompts are not enforcement.
Source checks are made by this app's own requests to public https hosts; your
judgments are recorded next to them and can be read by anyone who verifies the trace.
The oracle's own nodes keep their hashes, so earlier proofs still verify. An approved
audit says the record is honest. It does not say the forecast is right.
Confirmation checks the chain id, a successful finalized canonical receipt, and exactly
one ReceiptV2 event from the registry whose publisher is the auditor and whose fields
equal the seal. Each audit and each transaction hash is recorded at most once. The
registry itself accepts repeated publishes, so never publish again after an uncertain
broadcast: confirm the hash you have.
