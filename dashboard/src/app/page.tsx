import { api } from "@/lib/api";
import { LandingDebate } from "@/components/landing-debate";
import { LandingHero } from "@/components/landing-hero";
import { LandingTicker } from "@/components/landing-ticker";
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
      {/* Top ticker sits flush against the nav — break out of the layout padding
       *  (which is responsive: px-4 / sm:px-6 / lg:px-8). */}
      <div className="-mx-4 -mt-8 mb-8 sm:-mx-6 sm:-mt-10 sm:mb-10 lg:-mx-8">
        <LandingTicker initial={recent} />
      </div>

      <LandingHero initialStats={stats} initialReceipt={latestReceipt} />

      <section className="py-14 sm:py-20 lg:py-24" style={{ borderTop: "1px solid var(--ink-3)" }}>
        <LandingDebate />
      </section>

      <section className="py-14 sm:py-20 lg:py-24" style={{ borderTop: "1px solid var(--ink-3)" }}>
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
