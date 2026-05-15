"use client";

import { ConnectKitButton } from "connectkit";
import { useEffect, useState } from "react";
import { useAccount, useSignTypedData } from "wagmi";

const API_BASE =
  process.env.NEXT_PUBLIC_LIVE_API_BASE || "https://api.rrtrace.xyz";
const ARC_TX_URL = (h: string) =>
  `https://testnet.arcscan.app/tx/${h.startsWith("0x") ? h : `0x${h}`}`;

// Arc Testnet Gateway Wallet (also referenced server-side in server/x402.py).
const GATEWAY_VERIFYING_CONTRACT =
  "0x0077777d7EBA4688BDeF3E311b846F25870A19B9";
const ARC_CHAIN_ID = 5_042_002;

interface DemoMarket {
  market_id: string;
  market_question: string | null;
  market_source: string;
}

interface CachedPrice {
  market_id: string;
  market_question: string | null;
  probability: number;
  confidence: number;
  schema_version: string | null;
  merkle_root: string | null;
  trace_hash: string;
  trace_cid: string;
  arc_tx_hash: string | null;
  receipt_id: number;
  paid_by_caller: number;
}

interface ChallengeRequirement {
  amount: string;
  payTo: string;
  nonce: string;
  network: string;
}

/** Pull the 402 challenge body + signed token. Server returns 402 on the
 * first unauthenticated GET; we parse those out so the client knows which
 * fields to sign and which token to echo back on the paid retry. */
async function fetchChallenge(marketId: string): Promise<{
  challengeToken: string;
  requirements: ChallengeRequirement;
}> {
  const r = await fetch(`${API_BASE}/mcp/v1/get_price/${marketId}`, {
    method: "GET",
  });
  if (r.status !== 402) {
    throw new Error(`expected 402 challenge, got ${r.status}`);
  }
  const challengeToken = r.headers.get("X-Payment-Challenge") || "";
  if (!challengeToken) throw new Error("no X-Payment-Challenge header on 402");
  const body = await r.json();
  const accept = body.accepts?.[0];
  if (!accept) throw new Error("malformed 402 body — no accepts[0]");
  return {
    challengeToken,
    requirements: {
      amount: String(accept.amount),
      payTo: accept.payTo,
      nonce: accept.nonce,
      network: accept.network,
    },
  };
}

function randomBytes32Hex(): `0x${string}` {
  const buf = new Uint8Array(32);
  crypto.getRandomValues(buf);
  return `0x${Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("")}` as `0x${string}`;
}

function microUsdcToDecimal(amount: string): string {
  return (Number(amount) / 1_000_000).toFixed(4);
}

export function X402LivePaywall() {
  const { address, isConnected, chain } = useAccount();
  const { signTypedDataAsync } = useSignTypedData();

  const [markets, setMarkets] = useState<DemoMarket[]>([]);
  const [selectedMarketId, setSelectedMarketId] = useState<string>("");
  const [phase, setPhase] = useState<
    "idle" | "challenge" | "signing" | "settling" | "done"
  >("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CachedPrice | null>(null);
  const [challengeView, setChallengeView] = useState<ChallengeRequirement | null>(null);

  useEffect(() => {
    fetch(`${API_BASE}/demo/markets?limit=20`)
      .then((r) => r.json())
      .then((d) => {
        const ms: DemoMarket[] = d.markets || [];
        setMarkets(ms);
        if (ms.length > 0) setSelectedMarketId(ms[0].market_id);
      })
      .catch(() => {});
  }, []);

  async function payAndQuery() {
    if (!address || !selectedMarketId) return;
    setError(null);
    setResult(null);
    setChallengeView(null);

    try {
      // 1) Hit the endpoint cold — server returns 402 + challenge.
      setPhase("challenge");
      const { challengeToken, requirements } = await fetchChallenge(selectedMarketId);
      setChallengeView(requirements);

      // 2) Build the EIP-3009 TransferWithAuthorization typed-data the
      //    Circle Gateway facilitator expects.
      const validAfter = 0n;
      const validBefore = BigInt(Math.floor(Date.now() / 1000) + 600);
      const authNonce = randomBytes32Hex();

      setPhase("signing");
      const signature = await signTypedDataAsync({
        domain: {
          name: "GatewayWalletBatched",
          version: "1",
          chainId: ARC_CHAIN_ID,
          verifyingContract: GATEWAY_VERIFYING_CONTRACT as `0x${string}`,
        },
        types: {
          TransferWithAuthorization: [
            { name: "from", type: "address" },
            { name: "to", type: "address" },
            { name: "value", type: "uint256" },
            { name: "validAfter", type: "uint256" },
            { name: "validBefore", type: "uint256" },
            { name: "nonce", type: "bytes32" },
          ],
        },
        primaryType: "TransferWithAuthorization",
        message: {
          from: address as `0x${string}`,
          to: requirements.payTo as `0x${string}`,
          value: BigInt(requirements.amount),
          validAfter,
          validBefore,
          nonce: authNonce,
        },
      });

      // 3) Construct the x402 v2 payload the server's verify() understands.
      //    Mock-mode server checks payer + amount + challenge token; real
      //    mode forwards this verbatim to Circle's /v1/settle.
      const xPayment = {
        x402Version: 2,
        scheme: "exact",
        network: requirements.network,
        payer: address,
        amount: requirements.amount,
        nonce: requirements.nonce,
        payload: {
          signature,
          authorization: {
            from: address,
            to: requirements.payTo,
            value: requirements.amount,
            validAfter: validAfter.toString(),
            validBefore: validBefore.toString(),
            nonce: authNonce,
          },
        },
      };
      const xPaymentHeader = btoa(JSON.stringify(xPayment));

      // 4) Retry with the signed payload — server settles and returns the cached trace.
      setPhase("settling");
      const r2 = await fetch(`${API_BASE}/mcp/v1/get_price/${selectedMarketId}`, {
        method: "GET",
        headers: {
          "X-Payment": xPaymentHeader,
          "X-Payment-Challenge": challengeToken,
        },
      });
      if (!r2.ok) {
        const body = await r2.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r2.status}`);
      }
      setResult(await r2.json());
      setPhase("done");
    } catch (e) {
      const msg =
        e && typeof e === "object" && "shortMessage" in e
          ? String((e as { shortMessage: unknown }).shortMessage)
          : e instanceof Error
            ? e.message
            : "request failed";
      setError(msg);
      setPhase("idle");
    }
  }

  const onArc = chain?.id === ARC_CHAIN_ID;
  const busy = phase !== "idle" && phase !== "done";
  const phaseLabel: Record<typeof phase, string> = {
    idle: "Pay $0.01 USDC & query",
    challenge: "Fetching 402 challenge…",
    signing: "Confirm EIP-3009 in wallet…",
    settling: "Settling via Gateway…",
    done: "Done — query again",
  };

  return (
    <section className="space-y-4 rounded-xl border border-accent/40 bg-accent/5 p-5">
      <header className="space-y-2">
        <h2 className="text-lg font-semibold">
          Try it for real — sign an EIP-3009 payment authorization
        </h2>
        <p className="text-sm text-muted">
          This is the full x402 v2 paywall, end-to-end. Connect a wallet, sign a{" "}
          <code className="font-mono text-xs text-ink">TransferWithAuthorization</code>{" "}
          authorizing 0.01 USDC to the Arc Testnet Gateway Wallet, server
          settles via Circle&apos;s facilitator (mock in this environment so no
          testnet USDC is consumed — the signature is real EIP-712 typed-data
          either way). You get back the latest <em>cached</em>{" "}
          rr-trace/3 trace for the market — no fresh ensemble run, just the
          paid agent-to-agent revenue path.
        </p>
      </header>

      {/* Step 1: connect */}
      <div className="flex flex-wrap items-center gap-3">
        <ConnectKitButton />
        {isConnected && (
          <span className="text-xs text-muted">
            {address?.slice(0, 8)}…{address?.slice(-4)} ·{" "}
            <span className={onArc ? "text-accent" : "text-danger"}>
              {onArc ? "Arc Testnet ✓" : "switch to Arc Testnet"}
            </span>
          </span>
        )}
      </div>

      {/* Step 2: market + pay */}
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={selectedMarketId}
          onChange={(e) => setSelectedMarketId(e.target.value)}
          className="min-w-[280px] rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink"
          disabled={!isConnected || busy}
        >
          {markets.length === 0 && <option value="">Loading markets…</option>}
          {markets.map((m) => (
            <option key={m.market_id} value={m.market_id}>
              [{m.market_source}] {(m.market_question ?? m.market_id).slice(0, 70)}
            </option>
          ))}
        </select>
        <button
          onClick={payAndQuery}
          disabled={!isConnected || !selectedMarketId || busy}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {phaseLabel[phase]}
        </button>
      </div>

      {/* Live trace of the protocol exchange */}
      {challengeView && (
        <pre className="overflow-x-auto rounded-lg bg-bg p-3 font-mono text-xs leading-relaxed text-muted">
{`HTTP/1.1 402 Payment Required
PAYMENT-REQUIRED: <base64 body>
X-Payment-Challenge: <hmac-signed token>

{
  "x402Version": 2,
  "accepts": [{
    "scheme":  "exact",
    "network": "${challengeView.network}",
    "amount":  "${challengeView.amount}",      // ${microUsdcToDecimal(challengeView.amount)} USDC
    "payTo":   "${challengeView.payTo}",
    "nonce":   "${challengeView.nonce.slice(0, 22)}…",
    "extra":   { "verifyingContract": "${GATEWAY_VERIFYING_CONTRACT.slice(0, 12)}…" }
  }]
}`}
        </pre>
      )}

      {error && (
        <div className="rounded-lg border border-danger/40 bg-danger/5 p-3 text-sm text-danger">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-3 rounded-lg border border-accent/40 bg-bg p-4 text-sm">
          <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
            <span className="text-xs uppercase tracking-wider text-muted">Settled</span>
            <a
              href={`/traces/${result.receipt_id}`}
              className="font-mono text-accent hover:underline"
            >
              receipt #{result.receipt_id}
            </a>
            <span className="text-xs text-muted">{result.schema_version}</span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            <div className="rounded border border-border bg-panel p-3">
              <div className="text-xs uppercase tracking-wider text-muted">Probability (YES)</div>
              <div className="mt-1 font-mono text-2xl text-accent">
                {(result.probability * 100).toFixed(1)}%
              </div>
            </div>
            <div className="rounded border border-border bg-panel p-3">
              <div className="text-xs uppercase tracking-wider text-muted">Confidence</div>
              <div className="mt-1 font-mono text-2xl text-accent2">
                {(result.confidence * 100).toFixed(1)}%
              </div>
            </div>
          </div>
          <div className="space-y-1 font-mono text-xs text-muted">
            <div>
              paid: <span className="text-ink">{result.paid_by_caller.toFixed(4)} USDC</span>{" "}
              <span className="text-[10px]">(mock-settled in this env; signature was real)</span>
            </div>
            <div>
              trace_hash: <span className="text-ink">{result.trace_hash.slice(0, 14)}…</span>
            </div>
            {result.merkle_root && (
              <div>
                merkle_root: <span className="text-ink">{result.merkle_root.slice(0, 14)}…</span>
              </div>
            )}
            {result.arc_tx_hash && (
              <div>
                arc_tx:{" "}
                <a
                  href={ARC_TX_URL(result.arc_tx_hash)}
                  target="_blank"
                  rel="noreferrer"
                  className="text-accent hover:underline"
                >
                  {result.arc_tx_hash.slice(0, 14)}… ↗
                </a>
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
