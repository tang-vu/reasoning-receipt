"use client";

import { useEffect, useState } from "react";

import { api, type StatsResponse, type TraceRow } from "@/lib/api";
import { StatCard } from "@/components/stat-card";
import { VolumeChart } from "@/components/volume-chart";

/**
 * Client-side wrapper for the /stats page. Takes server-rendered seeds for
 * the stats object + the 500-receipt window, then refreshes both from the
 * live API on mount so the page never shows hour-old build-time numbers
 * on GH Pages.
 */
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

interface Props {
  initialStats: StatsResponse | null;
  initialRows: TraceRow[];
}

export function LiveStatsPanel({ initialStats, initialRows }: Props) {
  const [stats, setStats] = useState<StatsResponse | null>(initialStats);
  const [rows, setRows] = useState<TraceRow[]>(initialRows);

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.stats(), api.receipts(500)])
      .then(([s, r]) => {
        if (cancelled) return;
        setStats(s);
        if (r.length > 0) setRows(r);
      })
      .catch(() => {
        // Stay on SSR seeds when the live API is unreachable.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const hrs = spanHours(rows);
  const perHour = hrs > 0 ? rows.length / hrs : 0;
  const avgProb = avg(rows, (r) => r.probability);
  const avgConf = avg(rows, (r) => r.confidence);

  return (
    <>
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
    </>
  );
}
