import type { Metadata } from "next";
import Link from "next/link";

import { api } from "@/lib/api";
import { ReliabilityChart } from "@/components/reliability-chart";
import { BrierOverTimeChart } from "@/components/brier-over-time-chart";
import { StatCard } from "@/components/stat-card";

export const metadata: Metadata = {
  title: "Calibration — Brier + reliability",
  description:
    "How well does ReasoningReceipt's probability map to reality? Brier score on resolved markets, 10-bucket reliability curve, confidence-tier breakdown.",
  alternates: { canonical: "/calibration/" },
};

function fmtBrier(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  return x.toFixed(4);
}

function fmtPct(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  return `${(x * 100).toFixed(1)}%`;
}

export default async function CalibrationPage() {
  const cal = await api.calibration().catch(() => null);

  return (
    <div className="space-y-8">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">
          Calibration — the agent <span className="text-accent">measures itself</span>
        </h1>
        <p className="mt-2 max-w-3xl text-muted">
          Once a market on Polymarket or Kalshi resolves, the resolver back-fills the outcome
          onto every receipt the agent emitted for it. That gives us ground truth for every
          prediction. We then compute a <span className="font-mono text-ink">Brier score</span>{" "}
          (mean squared error between predicted probability and actual outcome — lower is
          better, perfect forecaster scores 0) plus a 10-bucket reliability curve.
        </p>
        <p className="mt-2 max-w-3xl text-sm text-muted">
          A trivial &ldquo;50% on everything&rdquo; forecaster scores ~0.25. A good
          prediction-market analyst typically lands between 0.10 and 0.18.
        </p>
      </header>

      {!cal || cal.total_resolved === 0 ? (
        <div className="rounded-xl border border-border bg-panel p-6 text-sm text-muted">
          <div className="font-semibold text-ink">No resolved receipts yet.</div>
          <p className="mt-2 max-w-2xl">
            The agent started emitting receipts on May 12, 2026. Most markets have horizons of
            7–30 days, so the first wave of resolutions is expected from May 19 onward. The
            resolver polls Polymarket Gamma every ~10 minutes and back-fills outcomes as markets
            close — this page will populate automatically.
          </p>
          <p className="mt-3 max-w-2xl">
            View receipts piling up at{" "}
            <Link href="/traces/" className="text-accent underline">
              /traces
            </Link>{" "}
            or check the on-chain log directly:
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-panel2 p-3 font-mono text-xs">
            cast call 0x59022EFd46a697bbf2fAd36CcfA8F2099f0bd1Bf
            &nbsp;&nbsp;&quot;totalReceipts()(uint256)&quot; --rpc-url $RPC
          </pre>
        </div>
      ) : (
        <>
          <section className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <StatCard
              label="Brier score"
              value={fmtBrier(cal.brier_score)}
              hint={`across ${cal.total_resolved} resolved receipts`}
            />
            <StatCard
              label="High-conf Brier"
              value={fmtBrier(cal.brier_high_conf)}
              hint="confidence ≥ 0.7"
            />
            <StatCard
              label="Low-conf Brier"
              value={fmtBrier(cal.brier_low_conf)}
              hint="confidence < 0.7"
            />
            <StatCard
              label="Resolved markets"
              value={cal.distinct_resolved_markets.toLocaleString()}
              hint={`out of ${cal.total_resolved} receipts`}
            />
          </section>

          <ReliabilityChart buckets={cal.buckets} />

          <BrierOverTimeChart points={cal.brier_over_time} />

          <section className="rounded-xl border border-border bg-panel p-5">
            <div className="mb-3 text-sm font-semibold text-ink">Bucket breakdown</div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-panel2 text-xs uppercase tracking-wider text-muted">
                  <tr>
                    <th className="px-3 py-2">Bucket</th>
                    <th className="px-3 py-2">n</th>
                    <th className="px-3 py-2">mean predicted</th>
                    <th className="px-3 py-2">mean actual</th>
                    <th className="px-3 py-2">drift</th>
                  </tr>
                </thead>
                <tbody>
                  {cal.buckets.map((b) => {
                    const drift = b.mean_actual - b.mean_predicted;
                    return (
                      <tr key={b.label} className="border-t border-border">
                        <td className="px-3 py-2 font-mono text-xs text-muted">{b.label}</td>
                        <td className="px-3 py-2 font-mono">{b.n}</td>
                        <td className="px-3 py-2 font-mono">{fmtPct(b.mean_predicted)}</td>
                        <td className="px-3 py-2 font-mono">{fmtPct(b.mean_actual)}</td>
                        <td
                          className={`px-3 py-2 font-mono ${
                            Math.abs(drift) < 0.05
                              ? "text-accent"
                              : Math.abs(drift) < 0.15
                                ? "text-accent2"
                                : "text-danger"
                          }`}
                        >
                          {drift >= 0 ? "+" : ""}
                          {(drift * 100).toFixed(1)} pp
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <p className="text-xs text-muted">
            Note: a market is treated as resolved YES iff Polymarket Gamma reports{" "}
            <code className="font-mono">closed=true</code> and the YES close price is within 5%
            of 1.0; resolved NO iff the YES close price is within 5% of 0.0. Ambiguous markets
            (close price near 0.5) are not counted.
          </p>
        </>
      )}
    </div>
  );
}
