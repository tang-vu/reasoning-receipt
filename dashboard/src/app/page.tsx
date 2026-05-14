import { api } from "@/lib/api";
import { LiveReceiptsFeed } from "@/components/live-receipts-feed";
import { StatCard } from "@/components/stat-card";
import { VolumeChart } from "@/components/volume-chart";

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
      <section>
        <h1 className="text-3xl font-semibold tracking-tight">
          The trace <span className="text-accent">is</span> the product.
        </h1>
        <p className="mt-2 max-w-2xl text-muted">
          Every price comes with a full hashed reasoning trace. Pay a few cents over x402, get a
          number plus a receipt — pointer to the chain-of-thought, settled on Arc in under a
          second.
        </p>
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
