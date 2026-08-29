import { api } from "@/lib/api";
import { LandingHero } from "@/components/landing-hero";
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

      <section className="py-14 sm:py-20 lg:py-24" style={{ borderTop: "1px solid var(--ink-3)" }}>
        <LandingUseCases />
      </section>

      <section className="py-14 sm:py-20 lg:py-24" style={{ borderTop: "1px solid var(--ink-3)" }}>
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

      <section className="py-12 sm:py-16" style={{ borderTop: "1px solid var(--ink-3)" }}>
        <VolumeChart rows={recent} />
      </section>

      <section className="py-12 sm:py-16" style={{ borderTop: "1px solid var(--ink-3)" }}>
        <LiveReceiptsFeed initial={recent} />
      </section>
    </>
  );
}
