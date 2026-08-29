"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, type StatsResponse, type TraceRow } from "@/lib/api";
import { LandingReceiptPanel } from "@/components/landing-receipt-panel";

export function LandingHero({ initialStats, initialReceipt }: { initialStats: StatsResponse | null; initialReceipt: TraceRow | null }) {
  const [stats, setStats] = useState(initialStats);

  useEffect(() => {
    let cancelled = false;
    api.stats().then((fresh) => !cancelled && setStats(fresh)).catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return (
    <section className="relative isolate min-h-[calc(100vh-64px)] overflow-hidden border-x border-ink-3">
      <div className="instrument-grid instrument-grid-fade pointer-events-none absolute inset-0 -z-10 opacity-60" />
      <div className="grid min-h-[calc(100vh-64px)] min-w-0 grid-cols-[minmax(0,1fr)] lg:grid-cols-[minmax(0,1.06fr)_minmax(0,0.94fr)]">
        <div className="flex min-w-0 flex-col border-b border-ink-3 p-5 sm:p-8 lg:border-b-0 lg:border-r lg:p-12 xl:p-16">
          <div className="mb-12 flex flex-wrap items-center justify-between gap-4 sm:mb-16">
            <div className="flex items-center gap-2 font-mono text-[9px] uppercase tracking-[0.18em] text-lime">
              <span className="h-1.5 w-1.5 bg-lime" /> Proof layer / reasoning-receipt 1
            </div>
            <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-bone-faint">Model agnostic · Verify offline</div>
          </div>

          <h1 className="max-w-[820px] text-balance font-display text-[clamp(58px,8.3vw,126px)] leading-[0.84] tracking-[-0.035em]">
            The evidence<br />outlives the <span className="italic text-lime">answer.</span>
          </h1>

          <div className="mt-10 grid gap-8 xl:mt-14 xl:grid-cols-[1fr_auto] xl:items-end">
            <p className="max-w-[610px] text-[15px] leading-7 text-bone-dim sm:text-[17px]">
              Give every AI decision a portable record of <strong className="font-medium text-bone">what it saw, which rules applied, what it did, and who approved it.</strong> Every node is hashed. Every claim can be checked. No vendor trust required.
            </p>
            <div className="flex gap-3 xl:flex-col">
              <Link href="/build#lab" className="group inline-flex items-center justify-between gap-5 bg-lime px-5 py-3.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-ink-1 transition-transform hover:-translate-y-0.5">
                Create proof <span className="transition-transform group-hover:translate-x-1">→</span>
              </Link>
              <Link href="/inclusion" className="group inline-flex items-center justify-between gap-5 border border-bone/70 px-5 py-3.5 font-mono text-[10px] uppercase tracking-[0.12em] text-bone transition-colors hover:border-lime hover:text-lime">
                Verify one <span>↗</span>
              </Link>
            </div>
          </div>

          <div className="mt-14 grid grid-cols-2 border-t border-ink-3 pt-7 sm:grid-cols-4 lg:mt-auto">
            <Meta label="receipts indexed" value={stats?.total_receipts.toLocaleString() ?? "—"} />
            <Meta label="typed nodes" value="128" suffix="max" />
            <Meta label="hash" value="SHA-256" />
            <Meta label="verify" value="$0" suffix="offline" />
          </div>
        </div>

        <div className="relative grid min-h-[660px] min-w-0 place-items-center overflow-hidden bg-ink-2/30 p-5 sm:p-10 lg:min-h-0 xl:p-14">
          <div className="pointer-events-none absolute inset-x-8 top-7 flex justify-between font-mono text-[8px] uppercase tracking-[0.16em] text-bone-faint">
            <span>capture surface / 01</span><span>x: 847.21 y: 392.04</span>
          </div>
          <LandingReceiptPanel initial={initialReceipt} />
          <div className="pointer-events-none absolute inset-x-8 bottom-7 hash-noise font-mono text-[8px] uppercase tracking-[0.2em] text-bone-faint">
            <span>canonical-json · 9b36f04b7e9ef1379d · merkle-root · 91c03e882a · canonical-json · 9b36f04b7e9ef1379d · merkle-root · 91c03e882a · </span>
          </div>
        </div>
      </div>
    </section>
  );
}

function Meta({ label, value, suffix }: { label: string; value: string; suffix?: string }) {
  return (
    <div className="border-l border-ink-3 px-3 first:border-l-0 first:pl-0 sm:px-5">
      <div className="font-mono text-[8px] uppercase tracking-[0.16em] text-bone-faint">{label}</div>
      <div className="mt-2 font-display text-3xl italic leading-none text-bone sm:text-4xl">{value}</div>
      {suffix && <div className="mt-1 font-mono text-[8px] uppercase tracking-[0.14em] text-lime">{suffix}</div>}
    </div>
  );
}
