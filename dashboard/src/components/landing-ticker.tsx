"use client";

import { useEffect, useState } from "react";

import { api, type TraceRow } from "@/lib/api";

/**
 * Newsroom-style ticker that scrolls the latest on-chain receipts under the
 * nav. Mimics the design's "LIVE / ON-CHAIN" tag + animated mono row.
 * Re-fetches /receipts on mount and every 60s so the items track the daemon.
 */
function fmtItem(r: TraceRow): string {
  const src = (r.market_source || "").slice(0, 4).toUpperCase();
  const q = (r.market_question || r.market_id).slice(0, 40);
  const p = r.probability.toFixed(2);
  const gas = "0.00068";
  return `#${r.id} ${q} P=${p} · ${src} · gas $${gas}`;
}

export function LandingTicker({ initial }: { initial: TraceRow[] }) {
  const [rows, setRows] = useState<TraceRow[]>(initial.slice(0, 20));

  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      api
        .receipts(20)
        .then((fresh) => {
          if (!cancelled && fresh.length) setRows(fresh);
        })
        .catch(() => {});
    };
    tick();
    const id = window.setInterval(tick, 60_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const items = rows.length ? rows : [];
  // Duplicate the row so the looped scroll animation joins seamlessly.
  const doubled = [...items, ...items];

  return (
    <div
      className="relative flex h-9 items-center overflow-hidden border-b border-ink-3"
      style={{ background: "var(--ink)" }}
    >
      <span className="z-10 flex h-full flex-none items-center gap-2 bg-lime px-3.5 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-ink">
        <span
          className="inline-block h-1.5 w-1.5 rounded-full bg-ink"
          style={{ animation: "blink-step 1s steps(2) infinite" }}
          aria-hidden
        />
        Live / on-chain
      </span>
      <div
        className="flex-1 overflow-hidden"
        style={{
          maskImage:
            "linear-gradient(to right, transparent 0, black 40px, black calc(100% - 40px), transparent 100%)",
          WebkitMaskImage:
            "linear-gradient(to right, transparent 0, black 40px, black calc(100% - 40px), transparent 100%)",
        }}
      >
        <div
          className="inline-flex gap-9 whitespace-nowrap px-6 font-mono text-[12px] text-bone-dim"
          style={{ animation: "ticker-scroll 60s linear infinite" }}
        >
          {doubled.map((r, i) => (
            <span key={`${r.id}-${i}`} className="text-bone-dim">
              <span className="text-bone">{fmtItem(r).split(" P=")[0]}</span>
              {" P="}
              <span className={r.probability >= 0.5 ? "text-lime" : "text-terra"}>
                {r.probability.toFixed(2)}
              </span>
            </span>
          ))}
          {doubled.length === 0 && (
            <span className="text-bone-faint">waiting for receipts…</span>
          )}
        </div>
      </div>
    </div>
  );
}
