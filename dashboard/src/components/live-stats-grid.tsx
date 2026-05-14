"use client";

import { useEffect, useState } from "react";

import { api, type StatsResponse } from "@/lib/api";
import { StatCard } from "@/components/stat-card";

/**
 * Live-refreshing version of the homepage stats grid. Takes server-rendered
 * stats as an initial seed (so the static export still has correct numbers
 * at first paint) and overrides them with a fresh /stats fetch on client
 * mount. Without this, GH Pages serves the build-time snapshot count until
 * the next dashboard redeploy.
 */
function microUsdcToString(micro: number): string {
  return (micro / 1_000_000).toFixed(4);
}

export function LiveStatsGrid({ initial }: { initial: StatsResponse | null }) {
  const [stats, setStats] = useState<StatsResponse | null>(initial);

  useEffect(() => {
    let cancelled = false;
    api
      .stats()
      .then((fresh) => {
        if (!cancelled) setStats(fresh);
      })
      .catch(() => {
        // Keep the SSR seed — degrade silently if the live API is unreachable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
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
  );
}
