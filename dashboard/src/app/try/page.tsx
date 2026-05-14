import type { Metadata } from "next";
import Link from "next/link";

import { api } from "@/lib/api";

export const metadata: Metadata = {
  title: "Try it — how the paywall works",
  description:
    "Step-by-step walkthrough of the x402 v2 paywall: 402 challenge → EIP-3009 sign → settle on Arc → byte-verifiable receipt. No wallet required to read along.",
  alternates: { canonical: "/try/" },
};

const ARC_USDC_GAS = "0.000683";
const CIRCLE_GATEWAY = "0x0077777d7EBA4688BDeF3E311b846F25870A19B9";
const CHAIN_ID = "eip155:5042002";

export default async function TryPage() {
  // Pull one real receipt as the "what the response looks like" example.
  const sample = await api.receipts(1).then((rs) => rs[0] ?? null).catch(() => null);

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">Try it — how the paywall works</h1>
        <p className="max-w-3xl text-muted">
          ReasoningReceipt is built for <strong className="text-ink">agents</strong>, not browsers.
          The intended consumer is another piece of software that pays $0.01 over x402, gets back
          a probability + a verifiable trace, and uses the answer to size a position. Here&apos;s the
          exact HTTP dance the consumer goes through. No wallet required to read along —
          everything you need to verify a receipt is on this page.
        </p>
      </header>

      {/* Step 1 */}
      <Step
        index={1}
        title="Consumer fetches /price/{market_id} — server returns 402"
        caption="The first call has no X-Payment header. Server replies 402 with the EIP-3009 challenge."
      >
        <pre className="overflow-x-auto rounded-lg bg-bg p-3 text-xs leading-relaxed text-muted">
{`HTTP/1.1 402 Payment Required
Content-Type: application/json
Accept-Payment: x402-v2

{
  "scheme": "x402",
  "version": "2.0",
  "network": "${CHAIN_ID}",
  "asset": "USDC",
  "amount": "10000",          // 0.01 USDC in micro-USDC
  "extra": {
    "verifyingContract": "${CIRCLE_GATEWAY}",
    "facilitatorUrl": "https://gateway-api-testnet.circle.com/v1/settle"
  }
}`}
        </pre>
      </Step>

      {/* Step 2 */}
      <Step
        index={2}
        title="Consumer signs EIP-3009 TransferWithAuthorization"
        caption="A typed-data signature delegates a one-shot USDC transfer to the Circle Gateway. No gas spent by the consumer."
      >
        <pre className="overflow-x-auto rounded-lg bg-bg p-3 text-xs leading-relaxed text-muted">
{`{
  "from":         "<consumer-address>",
  "to":           "<oracle-receiver-address>",
  "value":        "10000",
  "validAfter":   "0",
  "validBefore":  "<now + 5 min>",
  "nonce":        "<random 32 bytes>"
}
// signed with consumer's private key → r, s, v`}
        </pre>
      </Step>

      {/* Step 3 */}
      <Step
        index={3}
        title="Consumer retries /price with X-Payment — server settles + returns trace"
        caption="Server posts the signed payload to /v1/settle, settles via Circle Gateway, emits a ReceiptV2 on Arc with the Merkle root of the reasoning DAG, and returns the price."
      >
          {sample ? (
            <pre className="overflow-x-auto rounded-lg bg-bg p-3 text-xs leading-relaxed text-muted">
{`HTTP/1.1 200 OK
Content-Type: application/json

{
  "market_id":     "${sample.market_id}",
  "probability":   ${sample.probability.toFixed(6)},
  "confidence":    ${sample.confidence.toFixed(6)},
  "claim":         "${(sample.market_question ?? "").slice(0, 80)}…",
  "trace_hash":    "${sample.trace_hash}",
  "trace_cid":     "${sample.trace_cid}",
  "merkle_root":   "${sample.merkle_root ?? "(only on rr-trace/3 rows)"}",
  "arc_tx_hash":   "${sample.arc_tx_hash ?? "(pending)"}",
  "schema":        "${sample.schema_version ?? "rr-trace/2"}",
  "paid_usdc":     "0.01",
  "gas_usdc":      "${ARC_USDC_GAS}"
}`}
            </pre>
          ) : (
            <pre className="rounded-lg bg-bg p-3 text-xs text-muted">No live receipt to show — backend may be sleeping.</pre>
          )}
      </Step>

      {/* Step 4 */}
      <Step
        index={4}
        title="Anyone can verify the trace byte-for-byte"
        caption="Pull the trace JSON from Irys → re-canonicalise (sorted keys, 6-dp floats, UTC) → SHA-256 → compare to the on-chain hash."
      >
        <pre className="overflow-x-auto rounded-lg bg-bg p-3 text-xs leading-relaxed text-muted">
{`uv run python -m scripts.verify-receipt ${sample?.id ?? "<id>"}
  verdict           : VERIFIED [OK]
  stored hash       : ${sample?.trace_hash ?? "<0x…>"}
  recomputed hash   : <same>
  irys gateway      : https://gateway.irys.xyz/${(sample?.trace_cid ?? "").replace("ar://", "") || "<cid>"}`}
        </pre>
        {sample && (
          <Link
            href={`/traces/${sample.id}`}
            className="inline-block rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:opacity-90"
          >
            Open this trace in the dashboard →
          </Link>
        )}
      </Step>

      {/* MCP — stdio (dev tools) */}
      <section className="space-y-3 rounded-xl border border-border bg-panel p-5">
        <h2 className="text-lg font-semibold">Or skip HTTP — call it as an MCP tool</h2>
        <p className="text-sm text-muted">
          ReasoningReceipt ships as a stdio MCP server. Drop this snippet into your{" "}
          <code className="rounded bg-bg px-1 py-0.5 font-mono text-xs">claude_desktop_config.json</code>
          {" "}and Claude calls the oracle directly. Four tools: <code className="font-mono text-xs">get_price</code>,
          {" "}<code className="font-mono text-xs">verify_receipt</code>,
          {" "}<code className="font-mono text-xs">get_stats</code>,
          {" "}<code className="font-mono text-xs">get_calibration</code>.
        </p>
        <pre className="overflow-x-auto rounded-lg bg-bg p-3 text-xs leading-relaxed text-muted">
{`{
  "mcpServers": {
    "reasoning-receipt": {
      "command": "node",
      "args": ["<path-to-repo>/services/mcp/server.js"],
      "env": { "RR_API_BASE": "https://api.rrtrace.xyz" }
    }
  }
}`}
        </pre>
      </section>

      {/* MCP — paywalled HTTP (agent-to-agent commerce) */}
      <section className="space-y-3 rounded-xl border border-accent/40 bg-accent/5 p-5">
        <h2 className="text-lg font-semibold">
          Agent-to-agent commerce — paywalled MCP over x402
        </h2>
        <p className="text-sm text-muted">
          For agents <strong className="text-ink">in production</strong> (no local stdio access),
          the same four MCP tools are exposed as Circle x402 v2 paywalled HTTP endpoints. Pay
          $0.01 USDC per call, get the cached probability + trace pointer + Merkle root back.
          Any agent that already speaks x402 to <code className="font-mono text-xs">/price</code>{" "}
          speaks this with zero extra code.
        </p>
        <pre className="overflow-x-auto rounded-lg bg-bg p-3 text-xs leading-relaxed text-muted">
{`# First call — server replies 402
curl -i https://api.rrtrace.xyz/mcp/v1/get_price/<market_id>

HTTP/1.1 402 Payment Required
{
  "scheme":  "x402",
  "version": "2.0",
  "network": "${CHAIN_ID}",
  "asset":   "USDC",
  "amount":  "10000",
  "extra":   { "verifyingContract": "${CIRCLE_GATEWAY}" }
}

# Sign EIP-3009 TransferWithAuthorization, retry
curl -H "X-Payment: <base64-signed-payload>" \\
     https://api.rrtrace.xyz/mcp/v1/get_price/<market_id>
→ 200 { probability, trace_hash, trace_cid, merkle_root, arc_tx_hash, ... }

# Same envelope for the audit endpoint
curl https://api.rrtrace.xyz/mcp/v1/audit/<receipt_id>`}
        </pre>
      </section>
    </div>
  );
}

function Step({
  index,
  title,
  caption,
  children,
}: {
  index: number;
  title: string;
  caption: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent text-xs font-bold text-bg">
          {index}
        </span>
        <h2 className="text-lg font-semibold">{title}</h2>
      </div>
      <p className="ml-10 max-w-3xl text-sm text-muted">{caption}</p>
      <div className="ml-10 space-y-3">{children}</div>
    </section>
  );
}
