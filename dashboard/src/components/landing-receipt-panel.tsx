import type { TraceRow } from "@/lib/api";

function shortHex(hash: string | null | undefined): string {
  if (!hash) return "9b36f04b7e9e…91c03e";
  return hash.length > 20 ? `${hash.slice(0, 14)}…${hash.slice(-7)}` : hash;
}

const nodes = [
  ["01", "REQUEST", "refund_usd: 49", "5c1a"],
  ["02", "EVIDENCE", "delivery_delay: 8d", "a290"],
  ["03", "POLICY", "limit_usd: 100", "7f14"],
  ["04", "OUTCOME", "approved: true", "ee42"],
];

export function LandingReceiptPanel({ initial }: { initial: TraceRow | null }) {
  const root = shortHex(initial?.merkle_root ?? initial?.trace_hash);

  return (
    <aside className="proof-card relative min-w-0 w-full max-w-[500px] border border-ink-3 bg-ink-1/80 p-4 sm:p-7">
      <div className="absolute left-2 top-2 font-mono text-[8px] text-lime">REC_01</div>
      <div className="absolute right-2 top-2 font-mono text-[8px] text-bone-faint">LIVE SPECIMEN</div>

      <div className="receipt-shadow relative mx-auto mt-6 w-[92%] overflow-hidden bg-bone text-ink-1 [transform:rotate(-0.7deg)]">
        <div className="scan-beam pointer-events-none absolute inset-x-0 top-0 z-10 h-px bg-lime shadow-[0_0_18px_2px_rgba(152,232,69,0.5)]" />
        <div className="px-5 pb-5 pt-7 sm:px-8 sm:pb-7 sm:pt-9">
          <div className="flex items-start justify-between border-b border-dashed border-neutral-500 pb-5">
            <div><div className="font-display text-[29px] italic leading-none">ReasoningReceipt</div><div className="mt-2 font-mono text-[8px] uppercase tracking-[0.22em] text-neutral-500">portable proof artifact</div></div>
            <div className="border border-neutral-400 px-2 py-1 font-mono text-[8px] uppercase tracking-[0.12em]">RR / 001</div>
          </div>

          <div className="grid grid-cols-[1fr_auto] gap-4 border-b border-dashed border-neutral-500 py-5">
            <div><div className="font-mono text-[8px] uppercase tracking-[0.18em] text-neutral-500">subject</div><div className="mt-1 font-display text-[22px] italic leading-none">support:refund-approval</div></div>
            <div className="text-right font-mono text-[8px] text-neutral-500"><div>2026.08.29</div><div className="mt-1">14:07:35Z</div></div>
          </div>

          <div className="py-2">
            {nodes.map(([id, kind, value, hash], index) => (
              <div key={id} className="relative grid min-w-0 grid-cols-[22px_64px_minmax(0,1fr)] items-center gap-2 border-b border-dotted border-neutral-300 py-2.5 font-mono text-[8px] last:border-b-0 sm:grid-cols-[24px_78px_minmax(0,1fr)_auto] sm:text-[9px]">
                {index < nodes.length - 1 && <span className="absolute left-[9px] top-7 h-5 border-l border-dotted border-neutral-400" />}
                <span className="grid h-[19px] w-[19px] place-items-center rounded-full border border-neutral-400 text-[7px]">{id}</span>
                <span className="font-semibold">{kind}</span><span className="truncate text-neutral-600">{value}</span><span className="hidden text-neutral-400 sm:inline">#{hash}</span>
              </div>
            ))}
          </div>

          <div className="border-y border-dashed border-neutral-500 py-4">
            <div className="flex items-end justify-between gap-4">
              <div className="min-w-0"><div className="font-mono text-[8px] uppercase tracking-[0.18em] text-neutral-500">merkle_root</div><div className="mt-1 truncate font-mono text-[10px]">{root}</div></div>
              <div className="flex-none border-2 border-ink-1 px-3 py-1.5 font-mono text-[9px] font-bold uppercase tracking-[0.16em] [transform:rotate(-2deg)]">verified ✓</div>
            </div>
          </div>

          <div className="mt-4 flex justify-between font-mono text-[8px] uppercase tracking-[0.14em] text-neutral-500"><span>4 nodes / 4 valid</span><span>sha-256 · offline</span></div>
        </div>
        <div aria-hidden className="h-[7px]" style={{ background: "radial-gradient(circle at 7px 0, var(--ink) 7px, transparent 7.6px) 0 0 / 17.5px 100% repeat-x" }} />
      </div>

      <div className="mt-5 grid grid-cols-3 border-t border-ink-3 pt-4 font-mono text-[8px] uppercase tracking-[0.13em] text-bone-faint">
        <span>canonical ✓</span><span className="text-center">portable ✓</span><span className="text-right text-lime">integrity 100%</span>
      </div>
    </aside>
  );
}
