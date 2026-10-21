# ReasoningReceipt on Aomi: settlement

This Aomi App settles an **audited** reasoning receipt with one USDC transfer that the
user approves in their own wallet. Only a trace the independent auditor
([integrations/aomi-audit](../aomi-audit/README.md)) approved and published on chain can be
paid for: a pending, sealed or rejected audit blocks settlement. Once the transfer is
independently verified on chain, the API issues a **separate outcome receipt** that links
back to the audited trace, which is never edited.

**Transfers are disabled by default.** An ordinary build has no EVM namespace, and the
API refuses every settlement route until a deployment with a recipient is configured.

```mermaid
sequenceDiagram
    actor User
    participant Aomi
    participant API as ReasoningReceipt API
    participant Wallet
    participant Arc as Arc testnet
    User->>Aomi: Settle audit N
    Aomi->>API: POST /v1/settlements/prepare (audit id, connected wallet, chain)
    API->>API: Audit must be published (approved + confirmed on chain), else refuse
    API->>Arc: eth_call transfer(recipient, amount) from the wallet
    API-->>Aomi: Unsigned transfer, or refusal if simulation fails
    Aomi->>Aomi: Decode calldata, must equal deployment recipient and amount
    Aomi->>Arc: stage_tx, then enforced simulate_batch (stop on failure)
    Aomi-->>User: Preview: audit id, trace hash, chain, token, recipient, amount
    User->>Wallet: Explicit approval (commit_txs)
    Wallet->>Arc: Broadcast
    Aomi->>API: POST /v1/settlements/verify (audit id, tx hash)
    API->>Arc: Receipt status, finality, canonical block, Transfer log
    API-->>Aomi: settled + outcome receipt, or pending / pending_finality / reverted
```

## Defaults

| | |
|---|---|
| Chain | Arc testnet, `5042002` |
| Token | USDC ERC-20 interface, `0x3600000000000000000000000000000000000000` (6 decimals) |
| Amount | `10000` base units = 0.01 test USDC |
| Recipient | one address from the deployment JSON; placeholder until configured |
| Approval | the user's own wallet; no server-held keys, no unattended signing |

All of these live in one deployment JSON. The app is built from it, and the API reads
the same file, so the model, the trace and the chat cannot change any of them.

## How each requirement is met

| Requirement | Where it is enforced |
|---|---|
| Failed or inconclusive audits block settlement | `/prepare` loads the audit by id and refuses (409) unless its status is `published`, which `/v1/audits/{id}/published` sets only after the auditor approved the trace and its `ReceiptV2` was confirmed final on chain. Pending, sealed and rejected audits prepare nothing, and `/verify` refuses them too. |
| Audited trace stays unchanged and verifiable | Settlement only reads the audit row. The outcome receipt is a new `reasoning-receipt/1` envelope whose `source` node carries the audit id, `trace_hash`, `merkle_root`, `trace_cid`, auditor and publishing transaction. |
| Preview and transaction match chain, recipient, amount | API builds calldata only from the deployment. The app decodes the returned calldata and refuses to stage it unless chain, token, recipient, amount, payer and value all match its build-time deployment. The skill guard limits writes to the configured chain, the USDC contract and `transfer(address,uint256)`. |
| Failed simulation blocks submission | `/prepare` runs `eth_call` from the connected wallet and returns no calldata if it fails. After staging, the route's enforcement runs `simulate_batch` with `on_failure: stop`. Commit happens only after explicit approval. |
| Rejection, pending or reverted never become success | `/verify` returns `pending`, `pending_finality` or `reverted` and records nothing. Success requires status `0x1`, a block at or below `finalized`, a canonical block hash, and exactly one matching `Transfer` log from the prepared wallet. A rejected wallet prompt produces no hash, so there is nothing to verify. |
| Repeated processing cannot duplicate success | `settlements.source_receipt_hash` (the audited `trace_hash`) and `settlements.transaction_hash` are unique, and the success write is conditional on `status = 'prepared'`. Re-verifying returns the stored outcome; a second transaction or a reused hash is refused. Tests run six concurrent verifications. |

One boundary is worth stating plainly: a plain ERC-20 transfer cannot refuse a second
payment on chain. If a user broadcasts twice before verifying, the second transfer
moves funds but can never become a second success record. The skill tells the agent to
verify the hash it has rather than resubmit.

## Configure for live testing

1. Copy `settlement-deployment.example.json` to `settlement-deployment.json` (ignored by
   git), set the recipient, and set `enabled` to `true`. Keep `api_url` an HTTPS origin.
2. On the API, set `RR_SETTLEMENT_CONFIG` to that file, `RR_SETTLEMENT_RPC_URL` to an Arc
   testnet RPC that supports the `finalized` block tag, and `RR_SETTLEMENT_API_TOKEN` to
   a random token.
3. Build the app with `RR_SETTLEMENT_CONFIG` pointing at the same file. An invalid
   enabled deployment fails the build. Give only `RR_SETTLEMENT_API_TOKEN` to the app's
   environment in Aomi.
4. Publish an audit first (see integrations/aomi-audit), then run one settlement for its
   audit id on Arc testnet through Aomi with a funded test wallet. Keep the outcome
   receipt and check it with `POST /v1/verify`.

The default artifact (no `RR_SETTLEMENT_CONFIG`) is the one to keep deployed until then.

## Deploy

The layout follows Aomi's community-app conventions: `.aomi/config.json` at the repo root
points here, the repo-root `Cargo.toml` carries the SDK pin Aomi's deploy gate reads, and
this folder is its own Cargo workspace with `Cargo.lock` beside it. `aomi.toml` sets
`public = false` until the live run passes. Deploy from build.aomi.dev on `main`.

## Develop

```bash
cargo test --locked                                             # disabled build
RR_SETTLEMENT_CONFIG=/abs/path/settlement.json cargo test --locked  # configured build
uv run --extra dev pytest tests/test_settlement.py              # API, from the repo root
```
