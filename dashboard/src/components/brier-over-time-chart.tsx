"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  Legend,
} from "recharts";

import type { BrierPoint } from "@/lib/api";

/**
 * Brier-over-time chart — does the agent get sharper as it resolves more markets?
 *
 * X axis: resolution order (1..N resolved receipts). Y axis: Brier score, lower
 * is better. Two lines:
 *   - rolling (trailing window) — sensitive to recent form
 *   - cumulative (all history) — the lifetime score, smoother
 *
 * The dashed reference at 0.25 is the score of a trivial "50% on everything"
 * forecaster: anything below it means the agent's probabilities carry signal.
 */
export function BrierOverTimeChart({ points }: { points: BrierPoint[] }) {
  if (!points || points.length < 2) {
    return (
      <div className="rounded-xl border border-border bg-panel p-6 text-sm text-muted">
        <div className="font-semibold text-ink">Brier over time</div>
        <p className="mt-2 max-w-2xl">
          Needs at least two resolved receipts to plot a trend. As more markets close and the
          resolver back-fills outcomes, this line shows whether the agent&apos;s calls are getting
          sharper over its lifetime.
        </p>
      </div>
    );
  }

  const window = points[points.length - 1]?.n ?? 50;
  const data = points.map((p) => ({
    index: p.index,
    rolling: Number(p.brier_rolling.toFixed(4)),
    cumulative: Number(p.brier_cumulative.toFixed(4)),
    t: p.t,
  }));

  return (
    <div className="rounded-xl border border-border bg-panel p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <div className="text-sm font-semibold text-ink">Brier over time — is the agent learning?</div>
        <div className="text-xs text-muted">lower = sharper · dashed 0.25 = coin-flip baseline</div>
      </div>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#23232a" />
            <XAxis
              dataKey="index"
              stroke="#8a8a93"
              tick={{ fontSize: 11 }}
              label={{
                value: "resolved receipts →",
                position: "insideBottom",
                offset: -2,
                fill: "#8a8a93",
              }}
            />
            <YAxis
              domain={[0, "auto"]}
              tickCount={6}
              stroke="#8a8a93"
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => (typeof v === "number" ? v.toFixed(2) : String(v))}
              label={{ value: "Brier", angle: -90, position: "insideLeft", fill: "#8a8a93" }}
            />
            <Tooltip
              cursor={{ stroke: "#5eead4", strokeOpacity: 0.4 }}
              contentStyle={{ background: "#111114", border: "1px solid #23232a" }}
              labelStyle={{ color: "#e7e7ea" }}
              labelFormatter={(v) => `resolved #${v}`}
              formatter={(value: unknown, name: string) => {
                const num = typeof value === "number" ? value : NaN;
                return [num.toFixed(4), name];
              }}
            />
            <Legend wrapperStyle={{ paddingTop: 8 }} />
            <ReferenceLine y={0.25} stroke="#444" strokeDasharray="4 4" />
            <Line
              type="monotone"
              dataKey="rolling"
              stroke="#5eead4"
              strokeWidth={2}
              dot={false}
              name={`rolling (${window})`}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="cumulative"
              stroke="#a78bfa"
              strokeWidth={1.5}
              strokeDasharray="2 2"
              dot={false}
              name="cumulative"
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
