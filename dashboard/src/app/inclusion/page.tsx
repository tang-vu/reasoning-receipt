"use client";

import Link from "next/link";
import { useState } from "react";

interface InclusionResponse {
  receipt_id: number;
  node_id: string;
  leaf: string;
  proof: string[];
  root_from_trace: string;
  root_recomputed: string;
  root_matches: boolean;
  verified_offchain: boolean;
  verified_onchain: boolean | null;
  onchain_error: string | null;
  node: Record<string, unknown> & { _note?: string };
}

const LIVE_API_BASE =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_LIVE_API_BASE) ||
  "https://api.rrtrace.xyz";

const ARC_V2_URL =
  "https://testnet.arcscan.app/address/0x27d93c52fea923f956345af27f61d7bf47f0c4c1";

const COMMON_NODE_IDS = [
  { id: "c0", label: "c0 — claim" },
  { id: "s_bull", label: "s_bull — bull stance" },
  { id: "s_bear", label: "s_bear — bear stance" },
  { id: "s_edge", label: "s_edge — edge stance" },
  { id: "fc1", label: "fc1 — falsifiable claim #1" },
  { id: "cd_falsifiability", label: "cd_falsifiability — critic dim" },
  { id: "cd_coherence", label: "cd_coherence — critic dim" },
];

export default function InclusionPlayground() {
  const [receiptId, setReceiptId] = useState("2712");
  const [nodeId, setNodeId] = useState("c0");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<InclusionResponse | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const r = await fetch(
        `${LIVE_API_BASE}/verify/${receiptId}/node/${encodeURIComponent(nodeId)}`,
        { cache: "no-store" },
      );
      const data = (await r.json()) as InclusionResponse | { detail: string };
      if (!r.ok) {
        setError(("detail" in data && data.detail) || `HTTP ${r.status}`);
      } else {
        setResult(data as InclusionResponse);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          Merkle inclusion playground
        </h1>
        <p className="max-w-3xl text-muted">
          Every node of an rr-trace/3 reasoning DAG — claim, each stance, each piece of
          evidence, each counter-argument, each sensitivity factor, each critic dimension —
          has its own SHA-256 hash. A Merkle root over all the node hashes is committed on
          Arc inside <a href={ARC_V2_URL} target="_blank" rel="noreferrer" className="text-accent hover:underline">ReceiptRegistryV2</a>.
          Pick any receipt and any node id; the server pulls the trace from Irys, builds the
          inclusion proof, verifies it locally, and then calls
          <code className="mx-1 rounded bg-panel px-1.5 py-0.5 font-mono text-xs">verifyInclusion(root, leaf, proof)</code>
          on Arc via <code className="mx-1 rounded bg-panel px-1.5 py-0.5 font-mono text-xs">eth_call</code>.
          You get a yes/no from the contract itself — no full-trace download required.
        </p>
      </header>

      <section className="rounded-xl border border-border bg-panel p-5">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-muted">Receipt id</label>
            <input
              value={receiptId}
              onChange={(e) => setReceiptId(e.target.value.replace(/[^0-9]/g, ""))}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 font-mono text-sm text-ink"
              placeholder="2712"
            />
            <p className="text-xs text-muted">Any rr-trace/3 receipt id. Try 2712 (recent).</p>
          </div>
          <div className="space-y-2">
            <label className="text-xs uppercase tracking-wider text-muted">Node id</label>
            <input
              value={nodeId}
              onChange={(e) => setNodeId(e.target.value.trim())}
              className="w-full rounded-lg border border-border bg-bg px-3 py-2 font-mono text-sm text-ink"
              placeholder="c0"
            />
            <div className="flex flex-wrap gap-1.5">
              {COMMON_NODE_IDS.map((n) => (
                <button
                  key={n.id}
                  type="button"
                  onClick={() => setNodeId(n.id)}
                  className="rounded-full border border-border bg-bg px-2 py-0.5 text-[10px] font-mono uppercase tracking-wider text-muted hover:text-accent"
                  title={n.label}
                >
                  {n.id}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-end">
            <button
              onClick={run}
              disabled={loading || !receiptId || !nodeId}
              className="w-full rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Verifying…" : "Verify inclusion"}
            </button>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-xl border border-danger/40 bg-danger/5 p-5 text-sm text-danger">
          <div className="font-semibold">Error</div>
          <div className="mt-1 font-mono text-xs">{error}</div>
        </div>
      )}

      {result && (
        <div className="space-y-4">
          <section className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <VerdictCard
              label="Off-chain fold"
              ok={result.verified_offchain}
              note="sorted-pair SHA-256 fold matches the trace's stored root"
            />
            <VerdictCard
              label="On-chain verifyInclusion()"
              ok={result.verified_onchain}
              note={
                result.onchain_error
                  ? `RPC error — ${result.onchain_error}`
                  : "ReceiptRegistryV2.verifyInclusion via eth_call"
              }
            />
            <VerdictCard
              label="Root match"
              ok={result.root_matches}
              note="trace-embedded root equals locally recomputed root"
            />
          </section>

          <section className="rounded-xl border border-border bg-panel p-5">
            <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-2">
              <KV k="Receipt" v={`#${result.receipt_id}`} mono />
              <KV k="Node id" v={result.node_id} mono />
              <KV k="Leaf hash" v={result.leaf} mono break />
              <KV k="Merkle root" v={result.root_from_trace} mono break />
            </div>
            <details className="mt-4 rounded-lg border border-border bg-bg p-3 text-sm">
              <summary className="cursor-pointer text-xs uppercase tracking-wider text-muted">
                Inclusion proof ({result.proof.length} sibling{result.proof.length === 1 ? "" : "s"})
              </summary>
              <ul className="mt-2 space-y-1 font-mono text-xs">
                {result.proof.map((p, i) => (
                  <li key={i} className="break-all">
                    [{i}] {p}
                  </li>
                ))}
              </ul>
            </details>
            <details className="mt-2 rounded-lg border border-border bg-bg p-3 text-sm">
              <summary className="cursor-pointer text-xs uppercase tracking-wider text-muted">
                What got hashed (canonical bytes of this node)
              </summary>
              <pre className="mt-2 overflow-x-auto text-xs leading-relaxed">
{JSON.stringify(result.node, null, 2)}
              </pre>
            </details>
          </section>

          <section className="rounded-xl border border-accent/40 bg-accent/5 p-5 text-sm">
            <div className="font-semibold text-accent">What just happened</div>
            <ol className="mt-2 list-decimal space-y-1 pl-5 text-ink">
              <li>The server pulled receipt <code className="font-mono">#{result.receipt_id}</code> from the DB to find its trace CID.</li>
              <li>It downloaded the canonical trace JSON from Irys.</li>
              <li>It computed the sha256 of node <code className="font-mono">{result.node_id}</code>&apos;s canonical bytes (= the leaf above).</li>
              <li>It built the Merkle proof (sorted-pair sha256, OZ-style, promote-on-odd).</li>
              <li>It folded the leaf + proof locally → matched the trace&apos;s embedded root.</li>
              <li>It called <code className="font-mono">verifyInclusion(root, leaf, proof)</code> on ReceiptRegistryV2 via <code className="font-mono">eth_call</code> → got <strong>{String(result.verified_onchain)}</strong> back from the contract.</li>
            </ol>
            <p className="mt-3 text-muted">
              The whole roundtrip was <strong>~200 bytes of proof</strong>. No full-trace download.
              Anyone with the receipt id can do the same — see <Link href="/try" className="text-accent hover:underline">/try</Link> for the curl version.
            </p>
          </section>
        </div>
      )}
    </div>
  );
}

function VerdictCard({ label, ok, note }: { label: string; ok: boolean | null; note: string }) {
  const tone =
    ok === true
      ? "border-accent/40 bg-accent/5 text-accent"
      : ok === false
        ? "border-danger/40 bg-danger/5 text-danger"
        : "border-border bg-panel text-muted";
  const status = ok === true ? "VERIFIED ✓" : ok === false ? "FAILED ✗" : "—";
  return (
    <div className={`rounded-xl border p-4 ${tone}`}>
      <div className="text-xs uppercase tracking-wider opacity-80">{label}</div>
      <div className="mt-1 font-mono text-lg font-semibold">{status}</div>
      <div className="mt-1 text-xs text-muted">{note}</div>
    </div>
  );
}

function KV({ k, v, mono, break: br }: { k: string; v: string; mono?: boolean; break?: boolean }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-muted">{k}</div>
      <div className={`${mono ? "font-mono" : ""} ${br ? "break-all" : ""} text-sm text-ink`}>{v}</div>
    </div>
  );
}
