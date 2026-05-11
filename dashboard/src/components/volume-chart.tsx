"use client";

import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TraceRow } from "@/lib/api";

interface Bin {
  label: string;
  count: number;
}

function bucketize(rows: TraceRow[], bucketCount = 24): Bin[] {
  if (rows.length === 0) return [];
  const ts = rows
    .map((r) => +new Date(r.created_at))
    .filter((n) => Number.isFinite(n));
  if (ts.length === 0) return [];
  const min = Math.min(...ts);
  const max = Math.max(...ts);
  const span = Math.max(1, max - min);
  const width = span / bucketCount;
  const buckets: Bin[] = Array.from({ length: bucketCount }, (_, i) => {
    const start = new Date(min + i * width);
    return {
      label: start.toISOString().slice(11, 16),
      count: 0,
    };
  });
  for (const t of ts) {
    const idx = Math.min(bucketCount - 1, Math.floor((t - min) / width));
    buckets[idx].count += 1;
  }
  return buckets;
}

export function VolumeChart({ rows }: { rows: TraceRow[] }) {
  const data = useMemo(() => bucketize(rows), [rows]);

  return (
    <div className="rounded-xl border border-border bg-panel p-4">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm text-muted">Receipts over the visible window</div>
        <div className="text-xs text-muted">{rows.length} receipts</div>
      </div>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 0 }}>
            <defs>
              <linearGradient id="gradVol" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#5eead4" stopOpacity={0.45} />
                <stop offset="100%" stopColor="#5eead4" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#23232a" />
            <XAxis dataKey="label" stroke="#8a8a93" tick={{ fontSize: 11 }} />
            <YAxis stroke="#8a8a93" tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip
              contentStyle={{ background: "#111114", border: "1px solid #23232a" }}
              labelStyle={{ color: "#e7e7ea" }}
            />
            <Area
              type="monotone"
              dataKey="count"
              stroke="#5eead4"
              fill="url(#gradVol)"
              strokeWidth={2}
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
