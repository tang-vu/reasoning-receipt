import Link from "next/link";

/**
 * Apple-style Bento Grid Showcase per landing.csv pattern #28.
 * Asymmetric 6-col grid, each card carries a distinct visual hook
 * (animated SVG, massive stat, code panel, gradient orb) so the page
 * reads as a story, not a feature list.
 */
export function LandingBento() {
  return (
    <section className="space-y-4">
      <header className="flex items-baseline justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">What's in the box</h2>
        <span className="text-xs uppercase tracking-wider text-muted">six pillars · rubric-mapped</span>
      </header>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-6 md:auto-rows-[180px]">
        {/* Card 1 — 5-agent ensemble (HERO, col-span-4 row-span-2) */}
        <article className="glass-card group relative overflow-hidden rounded-3xl p-6 md:col-span-4 md:row-span-2">
          <div className="pointer-events-none absolute -right-20 -top-20 h-64 w-64 rounded-full bg-accent/15 blur-3xl" />
          <div className="relative flex h-full flex-col justify-between gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-accent">Agentic sophistication</div>
              <h3 className="mt-1 text-2xl font-semibold tracking-tight">
                Five agents debate. The supervisor merges. The critic decides.
              </h3>
              <p className="mt-3 max-w-md text-sm leading-relaxed text-muted">
                Bull, Bear, Edge run in parallel with isolated context. Supervisor merges
                weighted-Bayesian with a calibration prior. Critic audits across six dims —
                rejected receipts never reach the chain.
              </p>
            </div>

            {/* Stylised pipeline diagram */}
            <div className="flex items-center gap-3 text-[11px] font-mono text-muted">
              <PipelineNode tone="teal" label="Bull" />
              <PipelineLine />
              <div className="flex flex-col gap-1.5">
                <PipelineNode tone="amber" label="Bear" />
                <PipelineNode tone="amber" label="Edge" />
              </div>
              <PipelineLine />
              <PipelineNode tone="ink" label="Supervisor" big />
              <PipelineLine />
              <PipelineNode tone="ink" label="Critic" big />
            </div>

            <div className="flex items-center justify-between text-xs text-muted">
              <span>~21% receipts rejected by the audit gate before chain emit.</span>
              <Link href="/agents" className="font-mono text-accent group-hover:underline">
                /agents →
              </Link>
            </div>
          </div>
        </article>

        {/* Card 2 — Massive cost number (col-span-2, row-span-1) */}
        <article className="glass-card relative overflow-hidden rounded-3xl p-6 ring-1 ring-accent2/20 md:col-span-2">
          <div className="pointer-events-none absolute inset-0 bg-gradient-to-br from-accent2/8 to-transparent" />
          <div className="relative flex h-full flex-col justify-between">
            <div className="text-[10px] uppercase tracking-[0.18em] text-accent2">Per-action economics</div>
            <div>
              <div className="font-mono text-[clamp(2rem,4.5vw,3rem)] font-semibold leading-none text-ink">
                $0.000683
              </div>
              <div className="mt-1 text-xs text-muted">
                gas per Receipt event, measured across <span className="text-ink">3,000+</span> emissions
              </div>
            </div>
            <div className="text-xs text-muted">15× cheaper than the answer it commits to.</div>
          </div>
        </article>

        {/* Card 3 — Merkle DAG (col-span-2, row-span-1) */}
        <article className="glass-card relative overflow-hidden rounded-3xl p-6 md:col-span-2">
          <div className="pointer-events-none absolute -right-10 -bottom-10 h-40 w-40 rounded-full bg-accent/15 blur-2xl" />
          <div className="relative flex h-full flex-col justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-accent">Innovation</div>
              <h3 className="mt-1 text-lg font-semibold tracking-tight">Merkle DAG on Arc</h3>
            </div>
            {/* Mini merkle tree */}
            <svg viewBox="0 0 120 40" className="my-2 h-12 w-full" aria-hidden>
              <g stroke="rgba(94,234,212,0.45)" strokeWidth="1" fill="none">
                <line x1="60" y1="6" x2="30" y2="20" />
                <line x1="60" y1="6" x2="90" y2="20" />
                <line x1="30" y1="20" x2="15" y2="34" />
                <line x1="30" y1="20" x2="45" y2="34" />
                <line x1="90" y1="20" x2="75" y2="34" />
                <line x1="90" y1="20" x2="105" y2="34" />
              </g>
              <g fill="#5eead4">
                <circle cx="60" cy="6" r="3.5" />
              </g>
              <g fill="rgba(231,231,234,0.7)">
                <circle cx="30" cy="20" r="2.5" />
                <circle cx="90" cy="20" r="2.5" />
              </g>
              <g fill="rgba(231,231,234,0.4)">
                <circle cx="15" cy="34" r="2" />
                <circle cx="45" cy="34" r="2" />
                <circle cx="75" cy="34" r="2" />
                <circle cx="105" cy="34" r="2" />
              </g>
            </svg>
            <div className="flex items-center justify-between text-xs text-muted">
              <span>~200-byte proofs</span>
              <Link href="/inclusion" className="font-mono text-accent hover:underline">
                /inclusion →
              </Link>
            </div>
          </div>
        </article>

        {/* Card 4 — Code / x402 (col-span-3 row-span-1) */}
        <article className="glass-card relative overflow-hidden rounded-3xl p-6 md:col-span-3">
          <div className="flex h-full flex-col justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-accent">Agent-to-agent commerce</div>
              <h3 className="mt-1 text-lg font-semibold tracking-tight">x402 v2 paywall</h3>
            </div>
            <pre className="my-3 overflow-x-auto rounded-lg bg-bg/70 p-3 font-mono text-[11px] leading-relaxed text-muted ring-1 ring-border">
{`HTTP/1.1 402 Payment Required
PAYMENT-REQUIRED: { ... }     # x402-v2 challenge
                              ↓ sign EIP-3009
HTTP/1.1 200 OK               # /v1/settle via Gateway`}
            </pre>
            <div className="text-xs">
              <Link href="/try" className="font-mono text-accent hover:underline">
                /try — live wallet round-trip →
              </Link>
            </div>
          </div>
        </article>

        {/* Card 5 — Six Circle products (col-span-3 row-span-1) */}
        <article className="glass-card relative overflow-hidden rounded-3xl p-6 ring-1 ring-accent2/15 md:col-span-3">
          <div className="flex h-full flex-col justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-accent2">Circle Tools</div>
              <h3 className="mt-1 text-lg font-semibold tracking-tight">Six products in production</h3>
            </div>
            <div className="grid grid-cols-3 gap-2 text-xs">
              {[
                "Arc Testnet",
                "USDC",
                "Wallets",
                "Gateway / x402",
                "CCTP V2",
                "App Kit · Unified Balance",
              ].map((p) => (
                <div key={p} className="rounded-md bg-bg/50 px-2.5 py-1.5 text-muted ring-1 ring-border">
                  <span className="text-ink">{p}</span>
                </div>
              ))}
            </div>
            <div className="text-[11px] text-muted">App Kit is Circle&apos;s 2026 release — integrated in <code className="font-mono text-ink">services/app-kit/</code>.</div>
          </div>
        </article>

        {/* Card 6 — Two venues (col-span-2 row-span-1) */}
        <article className="glass-card relative overflow-hidden rounded-3xl p-6 md:col-span-2">
          <div className="flex h-full flex-col justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-accent">Traction</div>
              <h3 className="mt-1 text-lg font-semibold tracking-tight">Two venues, one scanner</h3>
            </div>
            <div className="my-3 flex items-baseline gap-2">
              <span className="rounded-md bg-accent/15 px-2 py-1 text-xs font-mono text-accent">Polymarket</span>
              <span className="text-muted">+</span>
              <span className="rounded-md bg-accent2/15 px-2 py-1 text-xs font-mono text-accent2">Kalshi</span>
            </div>
            <p className="text-xs text-muted">
              Round-robin interleave. RFB 03 plural — in the daemon, not the roadmap.
            </p>
          </div>
        </article>

        {/* Card 7 — MCP-native (col-span-2 row-span-1) */}
        <article className="glass-card relative overflow-hidden rounded-3xl p-6 md:col-span-2">
          <div className="flex h-full flex-col justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-accent">Integrations</div>
              <h3 className="mt-1 text-lg font-semibold tracking-tight">MCP-native</h3>
            </div>
            <p className="my-2 text-xs text-muted">
              stdio for Claude Desktop / Cursor / Cline. Paywalled HTTP variant at{" "}
              <code className="font-mono text-ink">/mcp/v1/</code> — agents pay $0.01 USDC per call.
            </p>
            <div className="flex gap-1.5 text-[10px] font-mono">
              <span className="rounded bg-bg/50 px-1.5 py-0.5 ring-1 ring-border">get_price</span>
              <span className="rounded bg-bg/50 px-1.5 py-0.5 ring-1 ring-border">verify_receipt</span>
              <span className="rounded bg-bg/50 px-1.5 py-0.5 ring-1 ring-border">audit</span>
            </div>
          </div>
        </article>

        {/* Card 8 — CCTP V2 demo (col-span-2 row-span-1) */}
        <article className="glass-card relative overflow-hidden rounded-3xl p-6 md:col-span-2">
          <div className="flex h-full flex-col justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-accent2">Cross-chain</div>
              <h3 className="mt-1 text-lg font-semibold tracking-tight">CCTP V2 demo</h3>
            </div>
            <div className="my-2 flex items-center gap-2 font-mono text-xs">
              <span className="rounded bg-bg/50 px-2 py-1 text-muted ring-1 ring-border">Sepolia</span>
              <span className="text-accent2">→</span>
              <span className="rounded bg-bg/50 px-2 py-1 text-ink ring-1 ring-border">Arc Testnet</span>
            </div>
            <div className="text-[11px] text-muted">
              1.0 USDC moved end-to-end in <span className="text-ink">~60 s</span>. Tx hashes in
              docs/SUBMISSION.md.
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}

/* ---------- helpers for the pipeline diagram ---------- */

function PipelineNode({
  label,
  tone,
  big = false,
}: {
  label: string;
  tone: "teal" | "amber" | "ink";
  big?: boolean;
}) {
  const bg =
    tone === "teal"
      ? "bg-accent/12 ring-accent/40 text-accent"
      : tone === "amber"
        ? "bg-accent2/12 ring-accent2/40 text-accent2"
        : "bg-panel/80 ring-border text-ink";
  return (
    <span
      className={`rounded-md ${big ? "px-3 py-1.5" : "px-2.5 py-1"} ring-1 ${bg} whitespace-nowrap`}
    >
      {label}
    </span>
  );
}

function PipelineLine() {
  return <span aria-hidden className="h-px w-5 bg-border" />;
}
