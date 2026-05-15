import Link from "next/link";

/**
 * Bento-grid showcase of the project's six rubric-relevant pillars. Pure
 * server component — no client state, ships as static HTML. Asymmetric
 * span layout collapses to single-column on mobile via Tailwind responsive
 * utilities.
 */
type BentoTone = "teal" | "amber" | "neutral";

interface Cell {
  span: string; // tailwind col/row spans (md+)
  tone?: BentoTone;
  title: string;
  body: React.ReactNode;
  footer?: React.ReactNode;
}

const TONE_RING: Record<BentoTone, string> = {
  teal: "ring-1 ring-accent/15",
  amber: "ring-1 ring-accent2/15",
  neutral: "",
};

export function LandingBento() {
  const cells: Cell[] = [
    {
      span: "md:col-span-4 md:row-span-2",
      tone: "teal",
      title: "5-agent ensemble per query",
      body: (
        <>
          <p className="text-sm text-muted">
            <span className="text-ink">Bull</span>, <span className="text-ink">Bear</span>, and{" "}
            <span className="text-ink">Edge</span> debate in parallel with isolated context. A{" "}
            <span className="text-ink">Supervisor</span> merges weighted-Bayesian with a
            calibration prior from past Brier scores. A <span className="text-ink">Critic</span>{" "}
            audits across six rigor dimensions; rejected receipts never reach the chain.
          </p>
          <pre className="mt-4 overflow-x-auto rounded-lg bg-bg/60 p-3 font-mono text-[11px] leading-relaxed text-muted">
{`scanner ──┬─→ [Bull   · Flash]
          ├─→ [Bear   · Flash]   ─→ [Supervisor · Pro] ─→ [Critic · Flash]
          └─→ [Edge   · Flash]              │                  │
                                            ▼                  ▼
                                   disagreement_pp     verdict ∈ {pass, revise, reject}`}
          </pre>
        </>
      ),
      footer: (
        <Link href="/agents" className="text-xs font-mono text-accent hover:underline">
          /agents →
        </Link>
      ),
    },
    {
      span: "md:col-span-2 md:row-span-1",
      tone: "amber",
      title: "Merkle DAG on Arc",
      body: (
        <p className="text-sm text-muted">
          Every claim, evidence URL, counter-argument and critic dimension gets its own SHA-256.
          The root commits via <span className="text-ink">ReceiptRegistryV2</span> — challenge
          any node with a <span className="text-ink">~200-byte proof</span>.
        </p>
      ),
      footer: (
        <Link href="/inclusion" className="text-xs font-mono text-accent2 hover:underline">
          /inclusion →
        </Link>
      ),
    },
    {
      span: "md:col-span-2 md:row-span-1",
      title: "x402 v2 paywall",
      body: (
        <p className="text-sm text-muted">
          PAYMENT-REQUIRED + EIP-3009 typed-data + Circle Gateway settle. Same envelope on{" "}
          <code className="font-mono text-xs text-ink">/price</code> and the paywalled{" "}
          <code className="font-mono text-xs text-ink">/mcp/v1</code> agent-to-agent path.
        </p>
      ),
      footer: (
        <Link href="/try" className="text-xs font-mono text-accent hover:underline">
          /try →
        </Link>
      ),
    },
    {
      span: "md:col-span-2 md:row-span-1",
      title: "Polymarket + Kalshi",
      body: (
        <p className="text-sm text-muted">
          Scanner pulls from both venues with round-robin interleave. RFB 03&apos;s{" "}
          <span className="text-ink">&quot;markets&quot;</span> is plural — and it&apos;s plural
          in the daemon, not the roadmap.
        </p>
      ),
    },
    {
      span: "md:col-span-2 md:row-span-1",
      tone: "amber",
      title: "Six Circle products in prod",
      body: (
        <ul className="space-y-1 text-sm text-muted">
          <li>· Arc Testnet · USDC</li>
          <li>· Wallets (developer-controlled)</li>
          <li>· Gateway / x402 v2 · CCTP V2</li>
          <li>· App Kit · Unified Balance (2026)</li>
        </ul>
      ),
    },
    {
      span: "md:col-span-2 md:row-span-1",
      tone: "teal",
      title: "Per-receipt economics",
      body: (
        <>
          <div className="font-mono text-3xl text-accent">$0.000683</div>
          <p className="mt-2 text-xs text-muted">
            Measured gas cost per Receipt event across 3,000+ on-chain emissions. A $0.01
            answer costs <span className="text-ink">15× less</span> than the gas to commit it
            on classical L1.
          </p>
        </>
      ),
    },
    {
      span: "md:col-span-2 md:row-span-1",
      title: "MCP-native",
      body: (
        <p className="text-sm text-muted">
          Drop the stdio server into <code className="font-mono text-xs text-ink">claude_desktop_config.json</code>{" "}
          and Claude calls the oracle as a first-class tool. Four tools:{" "}
          <code className="font-mono text-xs">get_price</code>,{" "}
          <code className="font-mono text-xs">verify_receipt</code>,{" "}
          <code className="font-mono text-xs">get_stats</code>,{" "}
          <code className="font-mono text-xs">get_calibration</code>.
        </p>
      ),
    },
  ];

  return (
    <section className="space-y-3">
      <header className="flex items-baseline justify-between">
        <h2 className="text-xl font-semibold tracking-tight">What&apos;s in the box</h2>
        <span className="text-xs text-muted">six pillars · rubric-mapped</span>
      </header>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-6 md:auto-rows-[160px]">
        {cells.map((c) => (
          <article
            key={c.title}
            className={`glass-card flex flex-col justify-between rounded-2xl p-5 ${c.span} ${
              c.tone ? TONE_RING[c.tone] : ""
            }`}
          >
            <div className="space-y-3">
              <h3 className="text-base font-semibold tracking-tight text-ink">{c.title}</h3>
              {c.body}
            </div>
            {c.footer && <div className="pt-3">{c.footer}</div>}
          </article>
        ))}
      </div>
    </section>
  );
}
