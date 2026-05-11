import { api, type TraceRow } from "@/lib/api";
import { StatCard } from "@/components/stat-card";
import { VolumeChart } from "@/components/volume-chart";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function microUsdc(micro: number): string {
  return (micro / 1_000_000).toFixed(4);
}

function avg(rows: TraceRow[], pick: (r: TraceRow) => number): number {
  if (rows.length === 0) return 0;
  return rows.reduce((s, r) => s + pick(r), 0) / rows.length;
}

function spanHours(rows: TraceRow[]): number {
  if (rows.length < 2) return 0;
  const ts = rows
    .map((r) => +new Date(r.created_at))
    .filter((n) => Number.isFinite(n))
    .sort((a, b) => a - b);
  return (ts[ts.length - 1] - ts[0]) / 3_600_000;
}

export default async function StatsPage() {
  const [stats, rows] = await Promise.all([
    api.stats().catch(() => null),
    api.receipts(500).catch(() => []),
  ]);

  const hrs = spanHours(rows);
  const perHour = hrs > 0 ? rows.length / hrs : 0;
  const avgProb = avg(rows, (r) => r.probability);
  const avgConf = avg(rows, (r) => r.confidence);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Operational stats</h1>
        <p className="mt-1 text-sm text-muted">
          Computed over the latest 500 receipts. Server-side, no caching.
        </p>
      </header>

      <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Total receipts"
          value={stats ? stats.total_receipts.toLocaleString() : "—"}
        />
        <StatCard
          label="Queries / hour"
          value={perHour.toFixed(2)}
          hint={hrs > 0 ? `over ${hrs.toFixed(1)} hours` : "warming up"}
        />
        <StatCard
          label="Avg probability"
          value={`${(avgProb * 100).toFixed(1)}%`}
          hint="Across recent receipts"
        />
        <StatCard
          label="Avg confidence"
          value={`${(avgConf * 100).toFixed(1)}%`}
          hint="Across recent receipts"
        />
        <StatCard
          label="USDC settled"
          value={stats ? `$${microUsdc(stats.total_paid_micro_usdc)}` : "—"}
          hint="x402 paywall"
        />
        <StatCard
          label="Distinct markets"
          value={stats ? stats.distinct_markets.toLocaleString() : "—"}
        />
        <StatCard
          label="Distinct consumers"
          value={stats ? stats.distinct_consumers.toLocaleString() : "—"}
        />
        <StatCard
          label="Latest receipt"
          value={
            stats?.latest_receipt_at
              ? new Date(stats.latest_receipt_at).toISOString().replace("T", " ").slice(0, 19)
              : "—"
          }
        />
      </section>

      <section>
        <VolumeChart rows={rows} />
      </section>
    </div>
  );
}
