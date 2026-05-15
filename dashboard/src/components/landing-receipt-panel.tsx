"use client";

import { useEffect, useState } from "react";

import { api, type TraceRow } from "@/lib/api";

/**
 * Cream paper "receipt" rendered to the right of the hero. Reads the latest
 * v3 receipt off the live API and styles it like a thermal-printer slip —
 * dashed dividers, italic display question, BIG italic probability, hash
 * stamp at the foot. Slight rotation gives it physicality.
 */
function shortHex(h: string | null): string {
  if (!h) return "—";
  if (h.length <= 18) return h;
  return `${h.slice(0, 12)}…${h.slice(-6)}`;
}

export function LandingReceiptPanel({ initial }: { initial: TraceRow | null }) {
  const [row, setRow] = useState<TraceRow | null>(initial);

  useEffect(() => {
    let cancelled = false;
    api
      .receipts(1)
      .then((rs) => {
        if (!cancelled && rs.length) setRow(rs[0]);
      })
      .catch(() => {});
  }, []);

  if (!row) return null;

  const verdict =
    row.schema_version === "rr-trace/3"
      ? "VERIFIED · v3"
      : "VERIFIED · v2";
  const isYes = row.probability >= 0.5;
  const tsFmt = row.created_at
    ? new Date(row.created_at).toISOString().replace("T", " · ").slice(0, 19)
    : "—";

  return (
    <aside
      className="mx-auto w-full max-w-[440px] font-mono lg:ml-auto lg:mr-0 lg:[transform:rotate(0.6deg)]"
      style={{
        background: "var(--bone)",
        color: "var(--ink)",
        boxShadow: "0 30px 60px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)",
      }}
    >
      <div className="px-5 pb-3 pt-5 sm:px-7 sm:pb-3.5 sm:pt-7">
        {/* Header */}
        <div
          className="pb-4 text-center"
          style={{ borderBottom: "1px dashed oklch(0.45 0.005 80)" }}
        >
          <div
            className="text-[28px] italic leading-none text-[color:var(--ink)]"
            style={{ fontFamily: "var(--f-display)" }}
          >
            ReasoningReceipt
          </div>
          <div
            className="mt-1 text-[9.5px] uppercase tracking-[0.22em]"
            style={{ color: "oklch(0.35 0.005 80)" }}
          >
            x402-paywalled oracle · arc testnet
          </div>
          <div
            className="mt-2 text-[10px]"
            style={{ color: "oklch(0.45 0.005 80)" }}
          >
            receipt #{row.id}
          </div>
        </div>

        {/* Question */}
        <div
          className="mb-3 mt-3 break-words text-[15px] italic leading-snug text-[color:var(--ink)] sm:mb-3.5 sm:mt-3.5 sm:text-[18px]"
          style={{ fontFamily: "var(--f-display)" }}
        >
          {row.market_question || row.market_id}
        </div>

        {/* Probability block */}
        <div
          className="my-2.5 flex flex-wrap items-baseline gap-2 py-2.5 sm:gap-2.5"
          style={{
            borderTop: "1px dashed oklch(0.55 0.005 80)",
            borderBottom: "1px dashed oklch(0.55 0.005 80)",
          }}
        >
          <span
            className="text-[44px] italic leading-[0.9] text-[color:var(--ink)] sm:text-[56px]"
            style={{ fontFamily: "var(--f-display)" }}
          >
            {(row.probability * 100).toFixed(0)}
            <span className="text-[22px] sm:text-[28px]">%</span>
          </span>
          <span
            className="text-[11px]"
            style={{ color: "oklch(0.35 0.005 80)" }}
          >
            probability
          </span>
          <span
            className="ml-auto inline-flex items-center gap-1.5 bg-[color:var(--ink)] px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-bone"
            style={{
              background: "var(--ink)",
              color: "var(--bone)",
              transform: "rotate(-3deg)",
            }}
          >
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ background: isYes ? "var(--lime)" : "var(--terra)" }}
              aria-hidden
            />
            {isYes ? "YES" : "NO"}
          </span>
        </div>

        {/* Meta rows */}
        <div className="space-y-1.5 text-[11.5px]" style={{ color: "oklch(0.30 0.005 80)" }}>
          <div className="flex items-baseline justify-between">
            <span>confidence</span>
            <span className="font-medium text-[color:var(--ink)]">{(row.confidence * 100).toFixed(0)}%</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span>source</span>
            <span className="font-medium text-[color:var(--ink)]">{row.market_source}</span>
          </div>
          {row.disagreement_pp != null && (
            <div className="flex items-baseline justify-between">
              <span>disagreement</span>
              <span className="font-medium text-[color:var(--ink)]">{row.disagreement_pp.toFixed(1)} pp</span>
            </div>
          )}
          <div className="flex items-baseline justify-between">
            <span>gas</span>
            <span className="font-medium text-[color:var(--ink)]">$0.000683 usdc</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span>paid</span>
            <span className="font-medium text-[color:var(--ink)]">$0.01 usdc</span>
          </div>
          <div className="flex items-baseline justify-between">
            <span>settled</span>
            <span className="font-medium text-[color:var(--ink)]">{tsFmt}</span>
          </div>
        </div>

        {/* Hash + stamp */}
        <div
          className="mt-3 pt-3 text-[10px]"
          style={{
            borderTop: "1px dashed oklch(0.55 0.005 80)",
            color: "oklch(0.40 0.005 80)",
          }}
        >
          <div className="uppercase tracking-[0.2em]">trace_hash</div>
          <div className="mt-1 break-all text-[9.5px] leading-snug text-[color:var(--ink)]">{shortHex(row.trace_hash)}</div>
          {row.merkle_root && (
            <>
              <div className="mt-2 uppercase tracking-[0.2em]">merkle_root</div>
              <div className="mt-1 break-all text-[9.5px] leading-snug text-[color:var(--ink)]">
                {shortHex(row.merkle_root)}
              </div>
            </>
          )}
          <div
            className="mt-3 inline-flex items-center gap-2 text-[10px]"
            style={{ color: "oklch(0.30 0.005 80)" }}
          >
            <span
              className="inline-grid h-8 w-8 place-items-center rounded-full text-[18px] italic"
              style={{
                border: "1.4px solid var(--ink)",
                color: "var(--ink)",
                fontFamily: "var(--f-display)",
                transform: "rotate(-7deg)",
              }}
              aria-hidden
            >
              R
            </span>
            {verdict}
          </div>
        </div>
      </div>

      {/* Perforated bottom */}
      <div
        aria-hidden
        style={{
          height: 7,
          background:
            "radial-gradient(circle at 7px 0, var(--ink) 7px, transparent 7.6px) 0 0 / 17.5px 100% repeat-x",
        }}
      />
    </aside>
  );
}
