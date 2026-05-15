"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { api, type StatsResponse } from "@/lib/api";

/**
 * Hero section for the landing page. Pulls the live stats from
 * api.rrtrace.xyz on mount so the headline metric strip always reflects
 * current daemon state. Pure CSS visuals (drifting orbs + masked grid)
 * — no Framer Motion or three.js dep added.
 */
export function LandingHero({ initial }: { initial: StatsResponse | null }) {
  const [stats, setStats] = useState<StatsResponse | null>(initial);

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
    <section className="relative -mx-6 overflow-hidden px-6 pb-12 pt-8 sm:pt-12">
      {/* Ethereal-Glass background: two drifting blurred orbs + masked grid */}
      <div
        className="landing-orb"
        style={{
          top: "-120px",
          left: "-80px",
          width: "420px",
          height: "420px",
          background: "radial-gradient(circle at 30% 30%, rgba(94,234,212,0.55), transparent 70%)",
          animationDelay: "0s",
        }}
      />
      <div
        className="landing-orb"
        style={{
          top: "10%",
          right: "-100px",
          width: "380px",
          height: "380px",
          background: "radial-gradient(circle at 70% 30%, rgba(252,211,77,0.42), transparent 70%)",
          animationDelay: "-9s",
        }}
      />
      <div className="landing-grid pointer-events-none absolute inset-0" />

      <div className="relative">
        {/* Live status pill */}
        <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-border bg-panel/60 px-3 py-1.5 text-xs text-muted backdrop-blur">
          <span className="live-dot" aria-hidden />
          <span>
            Live on Arc Testnet ·{" "}
            <span className="text-ink">{stats ? stats.total_receipts.toLocaleString() : "—"}</span>{" "}
            receipts ·{" "}
            <span className="text-ink">{stats ? stats.distinct_markets : "—"}</span> markets ·{" "}
            <span className="text-ink">{stats ? stats.distinct_consumers : "—"}</span> consumers
          </span>
        </div>

        {/* Headline */}
        <h1 className="max-w-4xl text-[clamp(2.25rem,5.5vw,4.25rem)] font-semibold leading-[1.05] tracking-tight">
          <span className="hero-gradient-text">The trace</span> is the product.
        </h1>

        {/* Sub */}
        <p className="mt-5 max-w-2xl text-lg text-muted">
          Five agents debate, the supervisor merges, the critic audits across six dimensions.
          Every node of the reasoning DAG gets its own hash — and the Merkle root lands on Arc.
          Pay a few cents over <span className="text-ink">x402</span>, get a probability and a
          byte-verifiable receipt for how it was produced.
        </p>

        {/* CTAs */}
        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Link
            href="/try-live"
            className="group inline-flex items-center gap-2 rounded-lg bg-accent px-5 py-2.5 text-sm font-semibold text-bg shadow-[0_8px_24px_-12px_rgba(94,234,212,0.6)] transition-transform hover:-translate-y-0.5 hover:opacity-95"
          >
            Try live with your wallet
            <span className="flex h-6 w-6 items-center justify-center rounded-full bg-bg/15 text-xs transition-transform group-hover:translate-x-0.5">
              →
            </span>
          </Link>
          <Link
            href="/try"
            className="inline-flex items-center gap-2 rounded-lg border border-border bg-panel/60 px-5 py-2.5 text-sm font-medium text-ink backdrop-blur hover:border-accent/40"
          >
            See the x402 protocol
          </Link>
          <a
            href="https://github.com/tang-vu/reasoning-receipt"
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-lg px-3 py-2.5 text-sm text-muted hover:text-ink"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" aria-hidden>
              <path d="M8 .2a8 8 0 0 0-2.5 15.6c.4.1.5-.2.5-.4v-1.4c-2.2.5-2.7-1.1-2.7-1.1-.4-.9-.9-1.2-.9-1.2-.7-.5.1-.5.1-.5.8.1 1.2.8 1.2.8.7 1.2 1.9.9 2.3.7.1-.5.3-.9.5-1.1-1.8-.2-3.6-.9-3.6-3.9 0-.9.3-1.6.8-2.2-.1-.2-.4-1 .1-2.1 0 0 .7-.2 2.2.8a7.5 7.5 0 0 1 4 0c1.5-1 2.2-.8 2.2-.8.5 1.1.2 1.9.1 2.1.5.6.8 1.3.8 2.2 0 3.1-1.9 3.7-3.7 3.9.3.3.5.7.5 1.4v2.1c0 .2.1.5.6.4A8 8 0 0 0 8 .2Z" />
            </svg>
            GitHub
          </a>
        </div>

        {/* Capability pill row — what's in the box, scannable */}
        <div className="mt-8 flex flex-wrap gap-2 text-[10px] uppercase tracking-wider text-muted">
          {[
            "bull / bear / edge ensemble",
            "supervisor weighted-bayesian",
            "critic 6-dim audit",
            "merkle dag on arc",
            "x402 v2 paywall",
            "cctp v2 cross-chain",
            "mcp tool surface",
            "polymarket + kalshi",
          ].map((label) => (
            <span
              key={label}
              className="rounded-full border border-border bg-panel/40 px-2 py-1 backdrop-blur"
            >
              {label}
            </span>
          ))}
        </div>
      </div>
    </section>
  );
}
