import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Build",
  description: "Create and verify portable ReasoningReceipts for any AI decision or action.",
};

const request = `POST /v1/receipts
Content-Type: application/json

{
  "subject": "support:refund-approval",
  "metadata": { "workflow": "customer-support" },
  "nodes": [
    { "id": "intent", "kind": "request", "payload": { "refund_usd": 49 } },
    { "id": "policy", "kind": "policy", "payload": { "limit_usd": 100 } },
    { "id": "decision", "kind": "outcome", "payload": { "approved": true } }
  ]
}`;

const endpoints = [
  ["POST /v1/receipts", "Canonicalise nodes and create a portable receipt."],
  ["POST /v1/verify", "Recompute every hash and verify the Merkle commitment offline."],
  ["POST /v1/proofs", "Create a compact inclusion proof for one evidence node."],
];

export default function BuildPage() {
  return (
    <div className="mx-auto max-w-6xl py-8 sm:py-14">
      <div className="micro mb-5 text-lime">reasoning-receipt/1 · domain neutral</div>
      <h1 className="max-w-4xl font-display text-6xl leading-[0.95] sm:text-8xl">
        Ship proof with every <span className="italic text-lime">decision.</span>
      </h1>
      <p className="mt-8 max-w-3xl text-lg leading-relaxed text-bone-dim">
        Use ReasoningReceipt as a small protocol layer between your AI system and the
        world it affects. No blockchain, model provider, or storage backend is required;
        anchoring and payment are optional adapters.
      </p>

      <section className="mt-16 grid gap-8 lg:grid-cols-[0.85fr_1.15fr]">
        <div className="border border-ink-3">
          {endpoints.map(([name, copy], index) => (
            <div key={name} className="border-b border-ink-3 p-5 last:border-b-0">
              <div className="font-mono text-xs text-lime">{name}</div>
              <p className="mt-2 text-sm text-bone-dim">{copy}</p>
              <div className="mt-4 font-mono text-[10px] text-bone-faint">0{index + 1}</div>
            </div>
          ))}
        </div>
        <pre className="overflow-x-auto border border-ink-3 bg-ink-2 p-5 font-mono text-[12px] leading-6 text-bone-dim sm:p-7">
          <code>{request}</code>
        </pre>
      </section>

      <section className="mt-16 border-t border-ink-3 pt-10">
        <h2 className="font-display text-4xl italic">The stable primitive</h2>
        <div className="mt-7 grid gap-6 md:grid-cols-3">
          {[
            ["Portable", "Plain canonical JSON. Verify it anywhere with SHA-256."],
            ["Selective", "Prove one node without revealing or downloading the full trace."],
            ["Composable", "Add Irys, Arc, x402, your database, or none of them."],
          ].map(([title, copy]) => (
            <div key={title} className="border-l border-lime pl-5">
              <h3 className="font-mono text-sm text-bone">{title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-bone-dim">{copy}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
