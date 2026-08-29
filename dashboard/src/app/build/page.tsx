import type { Metadata } from "next";
import Link from "next/link";

import { ReceiptLab } from "@/components/receipt-lab";

export const metadata: Metadata = {
  title: "Build a receipt",
  description: "Create and verify a portable ReasoningReceipt for any AI decision or action.",
};

const endpoints = [
  ["01", "CREATE", "POST /v1/receipts", "Canonicalise typed nodes and return their hashes plus one Merkle root."],
  ["02", "VERIFY", "POST /v1/verify", "Recompute the complete commitment without trusting our server or a chain."],
  ["03", "PROVE", "POST /v1/proofs", "Generate a selective inclusion proof for one node in the decision trace."],
];

export default function BuildPage() {
  return (
    <div className="border-x border-ink-3">
      <section className="relative overflow-hidden border-b border-ink-3 px-5 py-16 sm:px-8 sm:py-24 lg:px-12 xl:px-16">
        <div className="instrument-grid instrument-grid-fade pointer-events-none absolute inset-0 opacity-60" />
        <div className="relative grid gap-10 lg:grid-cols-[1fr_0.65fr] lg:items-end">
          <div>
            <div className="micro text-lime">Builder / live protocol surface</div>
            <h1 className="mt-7 max-w-5xl text-balance font-display text-[clamp(64px,10vw,138px)] leading-[0.82] tracking-[-0.04em]">Turn an action into <span className="italic text-lime">evidence.</span></h1>
          </div>
          <div className="border-l border-ink-3 pl-6 lg:mb-2">
            <p className="max-w-xl text-base leading-7 text-bone-dim">Compose a real receipt below. The lab sends your typed nodes to the production API, gets a canonical Merkle artifact back, then verifies every byte immediately.</p>
            <div className="mt-5 flex gap-5 font-mono text-[9px] uppercase tracking-[0.14em]"><span className="text-lime">Free core API</span><span className="text-bone-faint">No account</span><span className="text-bone-faint">No wallet</span></div>
          </div>
        </div>
      </section>

      <ReceiptLab />

      <section className="border-t border-ink-3 py-16 sm:py-24">
        <div className="px-5 sm:px-8 lg:px-12 xl:px-16">
          <div className="micro text-lime">Three primitives / one stable contract</div>
          <div className="mt-8 grid border-l border-t border-ink-3 lg:grid-cols-3">
            {endpoints.map(([id, action, endpoint, copy]) => (
              <article key={id} className="group min-h-64 border-b border-r border-ink-3 p-6 transition-colors hover:bg-ink-2/70 sm:p-8">
                <div className="flex justify-between font-mono text-[9px] uppercase tracking-[0.15em]"><span className="text-lime">{id} / {action}</span><span className="text-bone-faint">HTTP</span></div>
                <h2 className="mt-10 font-mono text-sm text-bone">{endpoint}</h2>
                <p className="mt-4 max-w-sm text-sm leading-6 text-bone-dim">{copy}</p>
                <div className="mt-8 h-px w-full bg-gradient-to-r from-lime/60 to-transparent" />
              </article>
            ))}
          </div>

          <div className="mt-10 flex flex-col justify-between gap-6 border border-ink-3 p-6 sm:flex-row sm:items-center sm:p-8">
            <div><h2 className="font-display text-4xl italic">Prefer code?</h2><p className="mt-2 text-sm text-bone-dim">MIT licensed. Read the schema, run it locally, or lift the protocol into your stack.</p></div>
            <Link href="https://github.com/tang-vu/reasoning-receipt" className="inline-flex items-center justify-between gap-8 border border-bone px-5 py-3 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors hover:border-lime hover:text-lime">Open source <span>↗</span></Link>
          </div>
        </div>
      </section>
    </div>
  );
}
