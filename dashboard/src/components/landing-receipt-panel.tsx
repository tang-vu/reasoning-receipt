import type { TraceRow } from "@/lib/api";

function shortHex(hash: string | null | undefined): string {
  if (!hash) return "7d12a4f9…91c03e";
  return hash.length > 18 ? `${hash.slice(0, 12)}…${hash.slice(-6)}` : hash;
}

export function LandingReceiptPanel({ initial }: { initial: TraceRow | null }) {
  const root = shortHex(initial?.merkle_root ?? initial?.trace_hash);

  return (
    <aside
      className="mx-auto w-full max-w-[440px] font-mono lg:ml-auto lg:mr-0 lg:[transform:rotate(0.6deg)]"
      style={{
        background: "var(--bone)",
        color: "var(--ink)",
        boxShadow: "0 30px 60px -20px rgba(0,0,0,0.6), 0 0 0 1px rgba(255,255,255,0.04)",
      }}
    >
      <div className="px-5 pb-4 pt-5 sm:px-7 sm:pb-5 sm:pt-7">
        <div className="border-b border-dashed border-neutral-500 pb-4 text-center">
          <div className="font-display text-[28px] italic leading-none">ReasoningReceipt</div>
          <div className="mt-1 text-[9.5px] uppercase tracking-[0.2em] text-neutral-600">
            portable evidence protocol
          </div>
          <div className="mt-2 text-[10px] text-neutral-500">reasoning-receipt/1</div>
        </div>

        <div className="my-4">
          <div className="text-[9px] uppercase tracking-[0.18em] text-neutral-500">subject</div>
          <div className="mt-1 font-display text-[21px] italic leading-snug">support:refund-approval</div>
        </div>

        <div className="border-y border-dashed border-neutral-500 py-3">
          {[
            ["01", "request", "customer asked for $49 refund"],
            ["02", "evidence", "order arrived 8 days late"],
            ["03", "policy", "auto-approve below $100"],
            ["04", "outcome", "refund approved"],
          ].map(([id, kind, copy]) => (
            <div key={id} className="grid grid-cols-[24px_70px_1fr] gap-2 border-b border-dotted border-neutral-300 py-2 text-[10px] last:border-b-0">
              <span className="text-neutral-400">{id}</span>
              <span className="font-semibold uppercase">{kind}</span>
              <span className="text-neutral-600">{copy}</span>
            </div>
          ))}
        </div>

        <div className="mt-4 grid grid-cols-[1fr_auto] items-end gap-4">
          <div>
            <div className="text-[9px] uppercase tracking-[0.18em] text-neutral-500">merkle_root</div>
            <div className="mt-1 break-all text-[10px]">{root}</div>
          </div>
          <div className="border-2 border-[color:var(--ink)] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] [transform:rotate(-3deg)]">
            verified
          </div>
        </div>

        <div className="mt-5 flex justify-between border-t border-dashed border-neutral-500 pt-3 text-[9px] uppercase tracking-[0.12em] text-neutral-500">
          <span>4 typed nodes</span>
          <span>sha-256 · offline</span>
        </div>
      </div>

      <div
        aria-hidden
        className="h-[7px]"
        style={{
          background: "radial-gradient(circle at 7px 0, var(--ink) 7px, transparent 7.6px) 0 0 / 17.5px 100% repeat-x",
        }}
      />
    </aside>
  );
}
