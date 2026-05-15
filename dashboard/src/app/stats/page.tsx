import type { Metadata } from "next";

import { api } from "@/lib/api";
import { LiveStatsPanel } from "@/components/live-stats-panel";

export const metadata: Metadata = {
  title: "Stats — traction at a glance",
  description:
    "Live traction for the ReasoningReceipt oracle: total receipts on Arc, USDC settled, distinct markets, distinct consumers, hourly volume chart.",
  alternates: { canonical: "/stats/" },
};

export default async function StatsPage() {
  const [stats, rows] = await Promise.all([
    api.stats().catch(() => null),
    api.receipts(500).catch(() => []),
  ]);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Operational stats</h1>
        <p className="mt-1 text-sm text-muted">
          Computed over the latest 500 receipts. Refreshes from the live API on every page load.
        </p>
      </header>
      <LiveStatsPanel initialStats={stats} initialRows={rows} />
    </div>
  );
}
