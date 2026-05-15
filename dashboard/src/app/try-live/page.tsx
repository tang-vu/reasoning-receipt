"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ConnectKitButton } from "connectkit";
import { useAccount, useSignMessage } from "wagmi";

interface DemoMarket {
  market_id: string;
  market_source: string;
  market_question: string | null;
  category: string | null;
}

interface DemoResponse {
  receipt_id: number;
  market_id: string;
  market_question: string | null;
  probability: number;
  confidence: number;
  trace_hash: string;
  trace_cid: string;
  merkle_root: string | null;
  arc_tx_hash: string | null;
  schema_version: string;
  consumer_address: string;
  note: string;
}

const API_BASE =
  process.env.NEXT_PUBLIC_LIVE_API_BASE || "https://api.rrtrace.xyz";
const ARC_TX_URL = (h: string) =>
  `https://testnet.arcscan.app/tx/${h.startsWith("0x") ? h : `0x${h}`}`;

/** Build the EXACT plaintext the server reconstructs in server/demo.py
 * `_build_demo_message`. Any drift in whitespace/wording breaks ecrecover. */
function buildDemoMessage(opts: {
  marketId: string;
  consumer: string;
  nonce: string;
  timestamp: string;
}): string {
  return (
    "ReasoningReceipt - demo authorization\n" +
    `market: ${opts.marketId}\n` +
    `consumer: ${opts.consumer}\n` +
    `nonce: ${opts.nonce}\n` +
    `timestamp: ${opts.timestamp}\n` +
    "\n" +
    "By signing, I authorize the oracle to emit a demo receipt attributed to my " +
    "wallet on Arc Testnet. No payment required."
  );
}

function randomNonce(): string {
  // 16 random hex chars — only collision protection is the 60s rate limit,
  // so we don't need full 32-byte entropy.
  const buf = new Uint8Array(8);
  crypto.getRandomValues(buf);
  return Array.from(buf, (b) => b.toString(16).padStart(2, "0")).join("");
}

export default function TryLivePage() {
  const { address, isConnected, chain } = useAccount();
  const { signMessageAsync } = useSignMessage();
  const [markets, setMarkets] = useState<DemoMarket[]>([]);
  const [selectedMarketId, setSelectedMarketId] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DemoResponse | null>(null);
  const [phase, setPhase] = useState<"idle" | "signing" | "submitting">("idle");

  useEffect(() => {
    fetch(`${API_BASE}/demo/markets?limit=20`)
      .then((r) => r.json())
      .then((d) => {
        const ms: DemoMarket[] = d.markets || [];
        setMarkets(ms);
        if (ms.length > 0) setSelectedMarketId(ms[0].market_id);
      })
      .catch(() => setError("Couldn't load market list — try refreshing."));
  }, []);

  async function getReasoning() {
    if (!address) return;
    if (!selectedMarketId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      // 1) Build the domain message + ask the wallet for a signature.
      //    This is the proof-of-intent gate — no synthetic tagging.
      const nonce = randomNonce();
      const timestamp = new Date().toISOString();
      const message = buildDemoMessage({
        marketId: selectedMarketId,
        consumer: address,
        nonce,
        timestamp,
      });
      setPhase("signing");
      const signature = await signMessageAsync({ message });

      // 2) POST to server with sig + nonce + timestamp. Server recovers the
      //    signer and asserts it matches `consumer_address`.
      setPhase("submitting");
      const r = await fetch(`${API_BASE}/demo/price/${selectedMarketId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          consumer_address: address,
          signature,
          nonce,
          timestamp,
        }),
      });
      if (!r.ok) {
        const body = await r.json().catch(() => ({}));
        throw new Error(body.detail || `HTTP ${r.status}`);
      }
      setResult(await r.json());
    } catch (e) {
      // wagmi throws { shortMessage, message } — prefer the short one.
      const msg =
        e && typeof e === "object" && "shortMessage" in e
          ? String((e as { shortMessage: unknown }).shortMessage)
          : e instanceof Error
            ? e.message
            : "request failed";
      setError(msg);
    } finally {
      setLoading(false);
      setPhase("idle");
    }
  }

  const onArc = chain?.id === 5_042_002;

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          Try it live — your wallet, a real on-chain receipt
        </h1>
        <p className="max-w-3xl text-muted">
          Connect any EVM wallet, pick a market, and <strong className="text-ink">sign a one-line authorization message</strong>.
          The oracle verifies your signature off-chain (no gas to you), then re-emits the latest
          cached trace for that market with <strong className="text-ink">your address as the consumer</strong> on
          Arc Testnet. The operator covers gas (~$0.0007 USDC). Each address gets{" "}
          <strong className="text-ink">5 free demos per day, 1 per minute</strong>.
        </p>
        <p className="text-xs text-muted">
          The signature is your proof of intent — without it the receipt would be a synthetic
          tag-the-wallet, which doesn&apos;t count as &quot;real user activity&quot;. For the full
          paywalled flow (real $0.01 USDC payment via x402 v2), see{" "}
          <Link href="/try" className="text-accent hover:underline">/try</Link>.
        </p>
      </header>

      {/* Step 1: Connect */}
      <section className="space-y-3 rounded-xl border border-border bg-panel p-5">
        <div className="flex items-center gap-3">
          <StepDot index={1} active={!isConnected} done={isConnected} />
          <h2 className="text-lg font-semibold">Connect a wallet</h2>
        </div>
        <ConnectKitButton />
        {isConnected && (
          <div className="space-y-1 text-xs text-muted">
            <div>
              Connected as <code className="font-mono text-ink">{address}</code>
            </div>
            <div>
              Network:{" "}
              <span className={onArc ? "text-accent" : "text-danger"}>
                {chain?.name ?? "unknown"} {onArc ? "✓" : "(switch to Arc Testnet)"}
              </span>
            </div>
          </div>
        )}
      </section>

      {/* Step 2: Pick + query */}
      <section className="space-y-4 rounded-xl border border-border bg-panel p-5">
        <div className="flex items-center gap-3">
          <StepDot index={2} active={isConnected && !result} done={result !== null} />
          <h2 className="text-lg font-semibold">Pick a market &amp; get reasoning</h2>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <select
            value={selectedMarketId}
            onChange={(e) => setSelectedMarketId(e.target.value)}
            className="min-w-[320px] rounded-lg border border-border bg-bg px-3 py-2 text-sm text-ink"
            disabled={!isConnected || loading}
          >
            {markets.length === 0 && <option value="">Loading markets…</option>}
            {markets.map((m) => (
              <option key={m.market_id} value={m.market_id}>
                [{m.market_source}] {(m.market_question ?? m.market_id).slice(0, 80)}
              </option>
            ))}
          </select>

          <button
            onClick={getReasoning}
            disabled={!isConnected || !selectedMarketId || loading}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {phase === "signing"
              ? "Confirm in wallet…"
              : phase === "submitting"
                ? "Emitting on Arc…"
                : "Sign &amp; get reasoning"}
          </button>
        </div>

        {error && (
          <div className="rounded-lg border border-danger/40 bg-danger/5 p-3 text-sm text-danger">
            {error}
          </div>
        )}

        {result && (
          <div className="space-y-3 rounded-lg border border-accent/40 bg-accent/5 p-4 text-sm">
            <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1">
              <span className="text-xs uppercase tracking-wider text-muted">
                Receipt
              </span>
              <Link
                href={`/traces/${result.receipt_id}`}
                className="font-mono text-accent hover:underline"
              >
                #{result.receipt_id}
              </Link>
              <span className="text-xs text-muted">{result.schema_version}</span>
            </div>

            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <div className="rounded border border-border bg-bg p-3">
                <div className="text-xs uppercase tracking-wider text-muted">
                  Probability (YES)
                </div>
                <div className="mt-1 font-mono text-2xl text-accent">
                  {(result.probability * 100).toFixed(1)}%
                </div>
              </div>
              <div className="rounded border border-border bg-bg p-3">
                <div className="text-xs uppercase tracking-wider text-muted">
                  Confidence
                </div>
                <div className="mt-1 font-mono text-2xl text-accent2">
                  {(result.confidence * 100).toFixed(1)}%
                </div>
              </div>
            </div>

            <div className="space-y-1 font-mono text-xs text-muted">
              <div>
                trace_hash:{" "}
                <span className="text-ink">{shortHex(result.trace_hash)}</span>
              </div>
              {result.merkle_root && (
                <div>
                  merkle_root:{" "}
                  <span className="text-ink">{shortHex(result.merkle_root)}</span>
                </div>
              )}
              <div>
                trace_cid: <span className="text-ink">{result.trace_cid}</span>
              </div>
              {result.arc_tx_hash && (
                <div>
                  arc_tx:{" "}
                  <a
                    href={ARC_TX_URL(result.arc_tx_hash)}
                    target="_blank"
                    rel="noreferrer"
                    className="text-accent hover:underline"
                  >
                    {shortHex(result.arc_tx_hash)} ↗
                  </a>
                </div>
              )}
            </div>

            <p className="text-xs text-muted">{result.note}</p>

            <div className="flex flex-wrap gap-3 text-xs">
              <Link
                href={`/traces/${result.receipt_id}`}
                className="rounded bg-accent px-3 py-1.5 font-semibold text-bg hover:opacity-90"
              >
                See full trace →
              </Link>
              <Link
                href="/stats"
                className="rounded border border-border px-3 py-1.5 text-muted hover:text-ink"
              >
                Watch /stats — your wallet is now a distinct consumer
              </Link>
            </div>
          </div>
        )}
      </section>

      <section className="rounded-xl border border-border bg-panel p-5 text-xs text-muted">
        <strong className="text-ink">How this works under the hood:</strong>{" "}
        the daemon emits ~50 v3 receipts per day across markets it discovers
        from Polymarket Gamma + Kalshi Trade API. Each one carries a
        Merkle-rooted reasoning DAG produced by the 5-agent ensemble
        (Bull/Bear/Edge + Supervisor + Critic). Your demo call re-emits the
        latest such receipt on Arc with your wallet attached as
        <code className="ml-1 font-mono text-ink">consumer_address</code> — no
        new Gemini run, no payment from you, just a real{" "}
        <code className="font-mono text-ink">ReceiptV2</code> event with{" "}
        <code className="font-mono text-ink">YOUR</code> address. Verifiable on{" "}
        <Link href="/stats" className="text-accent hover:underline">
          /stats
        </Link>{" "}
        and on the Arc explorer.
      </section>
    </div>
  );
}

function shortHex(h: string | null): string {
  if (!h) return "—";
  if (h.length <= 18) return h;
  return `${h.slice(0, 10)}…${h.slice(-6)}`;
}

function StepDot({ index, active, done }: { index: number; active?: boolean; done?: boolean }) {
  const cls = done
    ? "bg-accent text-bg"
    : active
      ? "bg-accent2 text-bg"
      : "bg-panel2 text-muted";
  return (
    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-bold ${cls}`}>
      {done ? "✓" : index}
    </span>
  );
}
