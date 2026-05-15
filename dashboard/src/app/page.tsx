import { api } from "@/lib/api";
import { LandingBento } from "@/components/landing-bento";
import { LandingHero } from "@/components/landing-hero";
import { LiveReceiptsFeed } from "@/components/live-receipts-feed";
import { LiveStatsGrid } from "@/components/live-stats-grid";
import { VolumeChart } from "@/components/volume-chart";

export default async function Home() {
  const [stats, recent] = await Promise.all([
    api.stats().catch(() => null),
    api.receipts(100).catch(() => []),
  ]);

  return (
    <div className="space-y-12">
      <LandingHero initial={stats} />

      <LandingBento />

      <LiveStatsGrid initial={stats} />

      <section>
        <VolumeChart rows={recent} />
      </section>

      <LiveReceiptsFeed initial={recent} />
    </div>
  );
}
