import { api } from "@/lib/api";
import { LiveReceiptsFeed } from "@/components/live-receipts-feed";
import { StatCard } from "@/components/stat-card";
import { VolumeChart } from "@/components/volume-chart";

function Pill({ label }: { label: string }) {
  return (
    <span className="rounded-full border border-border bg-panel px-2 py-0.5 text-muted">
      {label}
    </span>
  );
}

function microUsdcToString(micro: number): string {
  return (micro / 1_000_000).toFixed(4);
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

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Total receipts"
          value={stats ? stats.total_receipts.toLocaleString() : "—"}
          hint="On Arc + indexed locally"
        />
        <StatCard
          label="USDC settled"
          value={stats ? `$${microUsdcToString(stats.total_paid_micro_usdc)}` : "—"}
          hint="Sum across paid queries"
        />
        <StatCard
          label="Markets priced"
          value={stats ? stats.distinct_markets.toLocaleString() : "—"}
          hint="Distinct prediction markets"
        />
        <StatCard
          label="Consumers"
          value={stats ? stats.distinct_consumers.toLocaleString() : "—"}
          hint="Distinct payer addresses"
        />
      </section>

      <section>
        <VolumeChart rows={recent} />
      </section>

      <LiveReceiptsFeed initial={recent} />
    </div>
  );
}
