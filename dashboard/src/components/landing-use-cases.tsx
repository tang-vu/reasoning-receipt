import Link from "next/link";

const cases = [
  {
    index: "01",
    title: "Agent actions",
    copy: "Prove what an autonomous agent intended, which tools it called, which policy allowed it, and what happened.",
    nodes: "intent · tool · policy · outcome",
  },
  {
    index: "02",
    title: "Approvals",
    copy: "Attach tamper-evident evidence to refunds, underwriting, procurement, access grants, and human sign-off.",
    nodes: "request · evidence · rule · approver",
  },
  {
    index: "03",
    title: "AI compliance",
    copy: "Export a portable audit artifact without coupling your application to one model, chain, or storage vendor.",
    nodes: "input · policy · evaluation · decision",
  },
  {
    index: "04",
    title: "Forecasts",
    copy: "Keep the original prediction-market ensemble as one reference adapter, with calibration and inclusion proofs.",
    nodes: "claim · evidence · counterpoint · verdict",
  },
];

export function LandingUseCases() {
  return (
    <div>
      <div className="mb-10 grid gap-5 lg:grid-cols-[1fr_1fr] lg:items-end">
        <div>
          <div className="micro mb-4 text-lime">one protocol · many decisions</div>
          <h2 className="font-display text-5xl leading-none sm:text-7xl">
            Receipts for <span className="italic text-lime">any</span> AI workflow.
          </h2>
        </div>
        <p className="max-w-xl text-base leading-relaxed text-bone-dim lg:justify-self-end">
          The core envelope only knows subjects, typed evidence nodes, canonical hashes,
          and a Merkle root. Your domain semantics stay in your application.
        </p>
      </div>

      <div className="grid border-l border-t border-ink-3 md:grid-cols-2 xl:grid-cols-4">
        {cases.map((item) => (
          <article key={item.index} className="flex min-h-72 flex-col border-b border-r border-ink-3 p-6">
            <div className="font-mono text-[11px] text-bone-faint">{item.index}</div>
            <h3 className="mt-8 font-display text-3xl italic">{item.title}</h3>
            <p className="mt-4 text-sm leading-relaxed text-bone-dim">{item.copy}</p>
            <div className="mt-auto border-t border-dashed border-ink-3 pt-4 font-mono text-[10px] uppercase tracking-[0.08em] text-lime">
              {item.nodes}
            </div>
          </article>
        ))}
      </div>

      <Link href="/build" className="mt-8 inline-flex border border-bone px-5 py-3 font-mono text-xs tracking-[0.05em] transition-colors hover:border-lime hover:text-lime">
        Build with the portable API →
      </Link>
    </div>
  );
}
