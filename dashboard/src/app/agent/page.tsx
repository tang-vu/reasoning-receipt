import type { Metadata } from "next";
import Link from "next/link";

import { AomiAgent } from "@/components/aomi-agent";

export const metadata: Metadata = {
  title: "Settle with Aomi",
  description: "Settle an audited ReasoningReceipt with one wallet-approved USDC transfer through an Aomi agent.",
};

// Inlined at build time, so the static export works too. Unset or invalid keeps the chat off.
const APPLICATION_ID = Number(process.env.NEXT_PUBLIC_AOMI_APPLICATION_ID) || 0;

const steps = [
  ["01", "AUDIT", "An independent Aomi auditor checks every cited source and publishes the sealed trace to ReceiptRegistryV2."],
  ["02", "PREPARE", "Ask the agent to settle an audit. Failed or inconclusive audits are refused before anything is prepared."],
  ["03", "APPROVE", "The exact USDC transfer is simulated, then you approve it in your own wallet. Nothing is signed for you."],
  ["04", "VERIFY", "The finalized transfer is checked on Arc and recorded as an outcome receipt linked to the audited trace."],
];

export default function AgentPage() {
  return (
    <div className="border-x border-ink-3">
      <section className="relative overflow-hidden border-b border-ink-3 px-5 py-16 sm:px-8 sm:py-24 lg:px-12 xl:px-16">
        <div className="instrument-grid instrument-grid-fade pointer-events-none absolute inset-0 opacity-60" />
        <div className="relative grid gap-10 lg:grid-cols-[1fr_0.65fr] lg:items-end">
          <div>
            <div className="micro text-lime">Agent / powered by Aomi</div>
            <h1 className="mt-7 max-w-5xl text-balance font-display text-[clamp(64px,10vw,138px)] leading-[0.82] tracking-[-0.04em]">Settle only what was <span className="italic text-lime">audited.</span></h1>
          </div>
          <div className="border-l border-ink-3 pl-6 lg:mb-2">
            <p className="max-w-xl text-base leading-7 text-bone-dim">Chat with an Aomi agent to pay for a published, audited receipt. It prepares one test USDC transfer on Arc testnet and waits for your wallet approval.</p>
            <div className="mt-5 flex gap-5 font-mono text-[9px] uppercase tracking-[0.14em]"><span className="text-lime">Arc testnet</span><span className="text-bone-faint">Your wallet</span><span className="text-bone-faint">No server keys</span></div>
          </div>
        </div>
      </section>

      <section className="grid border-b border-ink-3 lg:grid-cols-[0.55fr_1fr]">
        <ol className="border-b border-ink-3 lg:border-b-0 lg:border-r">
          {steps.map(([id, action, copy]) => (
            <li key={id} className="border-b border-ink-3 p-6 last:border-0 sm:p-8">
              <div className="font-mono text-[9px] uppercase tracking-[0.15em] text-lime">{id} / {action}</div>
              <p className="mt-4 max-w-sm text-sm leading-6 text-bone-dim">{copy}</p>
            </li>
          ))}
        </ol>
        <div className="h-[720px] min-w-0">
          {Number.isSafeInteger(APPLICATION_ID) && APPLICATION_ID > 0 ? (
            <AomiAgent applicationId={APPLICATION_ID} />
          ) : (
            <div className="grid h-full place-items-center p-8 text-center">
              <div>
                <h2 className="font-display text-4xl italic">Agent not connected</h2>
                <p className="mx-auto mt-3 max-w-md text-sm leading-6 text-bone-dim">Set <code className="font-mono text-bone">NEXT_PUBLIC_AOMI_APPLICATION_ID</code> to the hosted app built from <code className="font-mono text-bone">integrations/aomi</code> to turn the chat on.</p>
                <Link href="https://github.com/tang-vu/reasoning-receipt/tree/main/integrations/aomi" className="mt-6 inline-flex items-center gap-8 border border-bone px-5 py-3 font-mono text-[10px] uppercase tracking-[0.12em] transition-colors hover:border-lime hover:text-lime">How it works <span>↗</span></Link>
              </div>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
