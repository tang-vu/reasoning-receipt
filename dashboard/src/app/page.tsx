import { api } from "@/lib/api";
import { LiveReceiptsFeed } from "@/components/live-receipts-feed";
import { LiveStatsGrid } from "@/components/live-stats-grid";
import { VolumeChart } from "@/components/volume-chart";

function Pill({ label }: { label: string }) {
  return (
    <span className="rounded-full border border-border bg-panel px-2 py-0.5 text-muted">
      {label}
    </span>
  );
}

export default async function Home() {
  const [stats, recent] = await Promise.all([
    api.stats().catch(() => null),
    api.receipts(100).catch(() => []),
  ]);

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">
          The trace <span className="text-accent">is</span> the product.
        </h1>
        <p className="max-w-2xl text-muted">
          Five agents debate. The supervisor merges. The critic audits across six dimensions.
          Every node of the resulting reasoning DAG gets its own hash; the Merkle root lands on
          Arc. Pay a few cents over x402, get a probability — and a byte-verifiable receipt for
          how it was produced.
        </p>
        <div className="flex flex-wrap gap-2 pt-1 text-[10px] font-mono uppercase tracking-wider">
          <Pill label="bull / bear / edge" />
          <Pill label="supervisor weighted-bayesian" />
          <Pill label="critic 6-dim audit" />
          <Pill label="merkle dag on arc" />
          <Pill label="x402 v2 paywall" />
          <Pill label="cctp v2 sepolia → arc" />
          <Pill label="mcp tool" />
        </div>
      </section>

      <LiveStatsGrid initial={stats} />

      <section>
        <VolumeChart rows={recent} />
      </section>

      <LiveReceiptsFeed initial={recent} />
    </div>
  );
}
