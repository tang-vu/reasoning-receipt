"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, type StatsResponse, type TraceRow } from "@/lib/api";
import { LandingReceiptPanel } from "@/components/landing-receipt-panel";

/**
 * Hero ported from design-landing/index.html:
 *   eyebrow chip → MASSIVE Instrument-Serif h1 with italic+lime "is" →
 *   lede paragraph → two CTAs → 4-col meta strip (italic serif numbers) →
 *   receipt panel on the right.
 */
export function LandingHero({
  initialStats,
  initialReceipt,
}: {
  initialStats: StatsResponse | null;
  initialReceipt: TraceRow | null;
}) {
  const [stats, setStats] = useState<StatsResponse | null>(initialStats);

  useEffect(() => {
    let cancelled = false;
    api
      .stats()
      .then((s) => {
        if (!cancelled) setStats(s);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section className="relative grid items-start gap-20 py-12 lg:grid-cols-[1.15fr_1fr] lg:gap-20">
      {/* LEFT column */}
      <div>
        {/* Eyebrow */}
        <div
          className="mb-9 inline-flex items-center gap-2.5 border border-ink-3 px-3 py-1.5 text-[11px] uppercase tracking-[0.14em]"
          style={{ fontFamily: "var(--f-mono)", color: "var(--bone-dim)" }}
        >
          <span
            className="inline-block h-1.5 w-1.5 rounded-full"
            style={{ background: "var(--lime)" }}
            aria-hidden
          />
          An x402-paywalled AI oracle · Arc Testnet · ~$0.0007 / receipt
        </div>

        {/* Headline */}
        <h1
          className="mb-12 text-balance leading-[0.96] tracking-[-0.02em]"
          style={{
            fontFamily: "var(--f-display)",
            fontWeight: 400,
            fontSize: "clamp(46px, 8.5vw, 134px)",
          }}
        >
          The trace{" "}
          <span
            className="italic"
            style={{ color: "var(--lime)" }}
          >
            is
          </span>{" "}
          the product.
        </h1>

        {/* Lede */}
        <p className="mb-10 max-w-[560px] text-[18px] leading-relaxed text-bone-dim">
          ReasoningReceipt is a paid oracle for{" "}
          <b className="font-medium text-bone">Polymarket</b> and{" "}
          <b className="font-medium text-bone">Kalshi</b>. Pay a few cents of USDC over x402,
          get a probability — <b className="font-medium text-bone">plus a byte-verifiable,
          Merkle-rooted reasoning DAG</b> committed to Arc. Not a hash of an opaque blob. The
          whole chain-of-thought. Auditable, leaf by leaf.
        </p>

        {/* CTAs */}
        <div className="flex flex-wrap items-center gap-3.5">
          <Link
            href="/try-live"
            className="group inline-flex items-center gap-2.5 border px-5 py-3.5 text-[13px] tracking-[0.04em] transition-all hover:-translate-y-0.5"
            style={{
              fontFamily: "var(--f-mono)",
              background: "var(--lime)",
              borderColor: "var(--lime)",
              color: "var(--ink)",
              fontWeight: 600,
            }}
          >
            Pay $0.01 · query live
            <span className="inline-block transition-transform group-hover:translate-x-1">→</span>
          </Link>
          <Link
            href="/try"
            className="group inline-flex items-center gap-2.5 border border-bone px-5 py-3.5 text-[13px] tracking-[0.04em] text-bone transition-all hover:border-lime hover:text-lime"
            style={{ fontFamily: "var(--f-mono)" }}
          >
            See the x402 protocol
            <span className="inline-block transition-transform group-hover:translate-x-1">→</span>
          </Link>
        </div>

        {/* Meta strip — 4 cols italic serif numbers */}
        <div
          className="mt-14 grid grid-cols-2 md:grid-cols-4"
          style={{
            borderTop: "1px solid var(--ink-3)",
            borderBottom: "1px solid var(--ink-3)",
          }}
        >
          <MetaCell label="receipts on chain" value={stats?.total_receipts.toLocaleString() ?? "—"} />
          <MetaCell label="distinct markets" value={stats?.distinct_markets.toLocaleString() ?? "—"} />
          <MetaCell label="distinct consumers" value={stats?.distinct_consumers.toString() ?? "—"} />
          <MetaCell label="per-receipt gas" value="0.0007" suffix=" usdc" last />
        </div>
      </div>

      {/* RIGHT column — receipt */}
      <LandingReceiptPanel initial={initialReceipt} />
    </section>
  );
}

function MetaCell({
  label,
  value,
  suffix,
  last = false,
}: {
  label: string;
  value: string;
  suffix?: string;
  last?: boolean;
}) {
  return (
    <div
      className="py-5 pr-4.5"
      style={{ borderRight: last ? "0" : "1px solid var(--ink-3)" }}
    >
      <div
        className="mb-2 text-[10.5px] uppercase tracking-[0.14em]"
        style={{ fontFamily: "var(--f-mono)", color: "var(--bone-faint)" }}
      >
        {label}
      </div>
      <div
        className="italic leading-none text-bone"
        style={{ fontFamily: "var(--f-display)", fontSize: 38 }}
      >
        {value}
        {suffix && (
          <small
            className="ml-1 align-top text-[12px] text-bone-dim"
            style={{ fontFamily: "var(--f-mono)", fontStyle: "normal", position: "relative", top: 4 }}
          >
            {suffix}
          </small>
        )}
      </div>
    </div>
  );
}
