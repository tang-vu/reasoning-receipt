"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
  Legend,
  ComposedChart,
  Cell,
} from "recharts";

import type { CalibrationBucket } from "@/lib/api";

/**
 * Reliability chart for a calibration report.
 *
 * X axis: mean predicted probability inside each bucket.
 * Y axis: actual fraction of receipts in that bucket whose market resolved YES.
 *
 * A perfectly calibrated forecaster has all dots on the y=x identity line.
 * Dots below the line = overconfident (predicted too high). Dots above the line
 * = underconfident. Dot size encodes the number of receipts in that bucket.
 */
export function ReliabilityChart({ buckets }: { buckets: CalibrationBucket[] }) {
  const points = buckets
    .filter((b) => b.n > 0)
    .map((b) => ({
      x: b.mean_predicted,
      y: b.mean_actual,
      n: b.n,
      label: b.label,
    }));

  const identity = Array.from({ length: 11 }, (_, i) => ({ x: i / 10, y: i / 10 }));

  if (points.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-panel p-6 text-sm text-muted">
        No resolved receipts yet. Reliability chart will populate as markets close and the
        resolver back-fills outcomes (most markets have 7–30 day horizons).
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-panel p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <div className="text-sm font-semibold text-ink">Reliability — predicted vs actual</div>
        <div className="text-xs text-muted">
          dots near y=x = well calibrated · dot size = receipts in bucket
        </div>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#23232a" />
            <XAxis
              type="number"
              dataKey="x"
              domain={[0, 1]}
              tickCount={6}
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              stroke="#8a8a93"
              tick={{ fontSize: 11 }}
              name="predicted"
              label={{ value: "predicted", position: "insideBottom", offset: -2, fill: "#8a8a93" }}
            />
            <YAxis
              type="number"
              dataKey="y"
              domain={[0, 1]}
              tickCount={6}
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              stroke="#8a8a93"
              tick={{ fontSize: 11 }}
              name="actual"
              label={{ value: "actual", angle: -90, position: "insideLeft", fill: "#8a8a93" }}
            />
            <ZAxis type="number" dataKey="n" range={[60, 320]} />
            <Tooltip
              cursor={{ stroke: "#5eead4", strokeOpacity: 0.4 }}
              contentStyle={{ background: "#111114", border: "1px solid #23232a" }}
              labelStyle={{ color: "#e7e7ea" }}
              formatter={(value: unknown, name: string) => {
                const num = typeof value === "number" ? value : NaN;
                if (name === "predicted" || name === "actual") {
                  return [`${(num * 100).toFixed(1)}%`, name];
                }
                return [String(value), name];
              }}
            />
            <Legend wrapperStyle={{ paddingTop: 8 }} />
            <Line
              type="linear"
              data={identity}
              dataKey="y"
              stroke="#444"
              strokeDasharray="4 4"
              dot={false}
              name="perfect calibration"
              isAnimationActive={false}
            />
            <Scatter data={points} name="bucket">
              {points.map((_, i) => (
                <Cell key={i} fill="#5eead4" />
              ))}
            </Scatter>
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

// Re-export to avoid unused-import warnings — Recharts requires Line/LineChart
// in scope when ComposedChart is used.
const _exports = { LineChart };
export default _exports;
