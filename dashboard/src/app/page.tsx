import Link from "next/link";

import { api } from "@/lib/api";
import { LandingHero } from "@/components/landing-hero";
import { LandingProofFlow } from "@/components/landing-proof-flow";
import { LandingUseCases } from "@/components/landing-use-cases";
import { LiveReceiptsFeed } from "@/components/live-receipts-feed";
import { LiveStatsGrid } from "@/components/live-stats-grid";
import { VolumeChart } from "@/components/volume-chart";

export default async function Home() {
  const [stats, recent] = await Promise.all([
    api.stats().catch(() => null),
    api.receipts(100).catch(() => []),
  ]);
  const latestReceipt = recent[0] ?? null;

  return (
    <>
      <LandingHero initialStats={stats} initialReceipt={latestReceipt} />

      <LandingProofFlow />

      <section className="border-x border-t border-ink-3 px-5 py-16 sm:px-8 sm:py-24 lg:px-12 xl:px-16">
        <LandingUseCases />
      </section>

      <section className="border-x border-t border-ink-3 px-5 py-16 sm:px-8 sm:py-24 lg:px-12 xl:px-16">
        <div className="mb-8 max-w-3xl">
          <div className="micro mb-3 text-lime">reference adapter · forecasting</div>
          <h2 className="font-display text-4xl italic sm:text-5xl">Battle-tested in prediction markets.</h2>
          <p className="mt-4 text-sm leading-relaxed text-bone-dim">
            The original oracle remains as a production reference: thousands of receipts,
            on-chain commitments, paid consumers, and outcome calibration.
          </p>
        </div>
        <LiveStatsGrid initial={stats} />
      </section>

      <section className="border-x border-t border-ink-3 px-5 py-12 sm:px-8 sm:py-16 lg:px-12 xl:px-16">
        <VolumeChart rows={recent} />
      </section>

      <section className="border-x border-y border-ink-3 px-5 py-12 sm:px-8 sm:py-16 lg:px-12 xl:px-16">
        <LiveReceiptsFeed initial={recent} />
      </section>

      <section className="relative overflow-hidden border-x border-b border-ink-3 px-5 py-20 sm:px-8 sm:py-28 lg:px-12 xl:px-16">
        <div className="instrument-grid pointer-events-none absolute inset-0 opacity-30" />
        <div className="relative grid gap-10 lg:grid-cols-[1fr_auto] lg:items-end">
          <div>
            <div className="micro text-lime">The next action is yours</div>
            <h2 className="mt-6 max-w-5xl text-balance font-display text-5xl leading-[0.9] sm:text-7xl lg:text-8xl">Your agent leaves logs.<br />Make it leave <span className="italic text-lime">evidence.</span></h2>
          </div>
          <Link href="/build#lab" className="group inline-flex min-w-56 items-center justify-between bg-lime px-6 py-4 font-mono text-[10px] font-semibold uppercase tracking-[0.14em] text-ink-1 transition-transform hover:-translate-y-1">Open receipt lab <span className="transition-transform group-hover:translate-x-1">→</span></Link>
        </div>
      </section>
    </>
  );
}
