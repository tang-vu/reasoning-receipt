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
      {/* Top ticker sits flush against the nav — break out of the layout padding. */}
      <div className="-mx-8 -mt-10 mb-10">
        <LandingTicker initial={recent} />
      </div>

      <LandingHero initialStats={stats} initialReceipt={latestReceipt} />

      <section className="py-24" style={{ borderTop: "1px solid var(--ink-3)" }}>
        <LandingDebate />
      </section>

      <section className="py-24" style={{ borderTop: "1px solid var(--ink-3)" }}>
        <LiveStatsGrid initial={stats} />
      </section>

      <section className="py-16" style={{ borderTop: "1px solid var(--ink-3)" }}>
        <VolumeChart rows={recent} />
      </section>

      <section className="py-16" style={{ borderTop: "1px solid var(--ink-3)" }}>
        <LiveReceiptsFeed initial={recent} />
      </section>
    </>
  );
}
