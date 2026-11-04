# Vercel serverless deployment

ReasoningReceipt uses two Vercel projects so the web and API can deploy and scale independently.

| Project | Root directory | Domain | Runtime |
|---|---|---|---|
| `dashboard` | `dashboard/` | `rrtrace.xyz` | Next.js |
| `reasoning-receipt-api` | repository root | `api.rrtrace.xyz` | FastAPI + Node Irys function |

Production does not require PM2, Cloudflare Tunnel, SQLite, Windows Scheduled Tasks, or an
always-on machine.

## Runtime changes

- FastAPI runs through `api/index.py` and disables the process-local SSE broker.
- The dashboard polls `/receipts` every 30 seconds; the committed snapshot remains a fallback.
- Vercel Cron calls `GET /cron/agent-batch` once daily. Each invocation processes a bounded batch.
- Python sends canonical trace bytes to `api/irys-upload.js`, authenticated with
  `IRYS_UPLOAD_SECRET`; the Irys private key exists only in that serverless function's environment.
- `DATABASE_URL` must be a pooled Postgres connection string. Provider-style `postgres://` and
  `postgresql://` URLs are normalized to psycopg 3 automatically.

## Required API environment variables

Copy the applicable secrets from the local `.env` into the API project's Production environment.
At minimum:

```text
DATABASE_URL
CRON_SECRET
IRYS_PRIVATE_KEY
IRYS_UPLOAD_SECRET
GOOGLE_API_KEY
RPC
DEPLOYER_PRIVATE_KEY
RECEIPT_REGISTRY_ADDRESS
RECEIPT_REGISTRY_V2_ADDRESS
CORS_ORIGINS=https://rrtrace.xyz,https://www.rrtrace.xyz
RR_CRON_AGENT_ENABLED=1
RR_CRON_PER_TICK=1
RR_CRON_TRADER=0
```

Add Circle/x402 and market credentials only for the adapters that are enabled.

## Database migration

Create a Neon database from the Vercel Marketplace, obtain its pooled connection string, then run:

```powershell
$env:TARGET_DATABASE_URL = "<pooled-postgres-url>"
.\.venv\Scripts\python.exe scripts\migrate-sqlite-to-postgres.py
```

The migration refuses to write into non-empty target tables. It never changes the SQLite source.

## Frontend environment

```text
NEXT_PUBLIC_LIVE_API_BASE=https://api.rrtrace.xyz
```

`npm run build:vercel` explicitly disables the old static-export mode.

## Optional Aomi audit and settlement

The serverless API reads deployment objects from `RR_AUDIT_CONFIG_JSON` and
`RR_SETTLEMENT_CONFIG_JSON`; local development may instead use the existing
`RR_AUDIT_CONFIG` and `RR_SETTLEMENT_CONFIG` file paths. Inline JSON takes
precedence, and invalid configuration fails closed. Build each Aomi artifact
with the same deployment values.

For each enabled integration, configure its separate `RR_AUDIT_API_TOKEN` or
`RR_SETTLEMENT_API_TOKEN` and its `*_RPC_URL`. Keep API tokens in secret stores;
deployment JSON contains public addresses and fixed transfer parameters only.

Set `RR_AUDIT_MODE=aomi` only after the auditor app is deployed and can process
the queue. The dashboard's `NEXT_PUBLIC_AOMI_APPLICATION_ID` is the deployed
Settlement app's numeric ID and requires a dashboard rebuild.

## Verification

```text
GET  https://api.rrtrace.xyz/healthz
POST https://api.rrtrace.xyz/v1/receipts
GET  https://rrtrace.xyz/build
```
