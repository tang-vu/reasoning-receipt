const stages = [
  { id: "01", kind: "CAPTURE", title: "Record the context", copy: "Intent, evidence, policy, tools, approvals, and outcome become typed nodes—not one opaque blob.", hash: "5c1a…e902" },
  { id: "02", kind: "COMMIT", title: "Hash every claim", copy: "Canonical JSON makes each node byte-deterministic. One Merkle root commits the complete decision.", hash: "7f14…aa31" },
  { id: "03", kind: "VERIFY", title: "Challenge anything", copy: "Recompute the whole receipt offline or prove one node without exposing the rest of the trace.", hash: "91c0…3e88" },
];

export function LandingProofFlow() {
  return (
    <section className="border-x border-t border-ink-3 py-16 sm:py-24">
      <div className="grid gap-8 px-5 sm:px-8 lg:grid-cols-[0.75fr_1.25fr] lg:px-12 xl:px-16">
        <div><div className="micro text-lime">The proof pipeline</div><h2 className="mt-5 max-w-xl font-display text-5xl leading-[0.9] sm:text-7xl">From action to <span className="italic text-lime">artifact.</span></h2></div>
        <div className="self-end lg:pl-16"><p className="max-w-2xl text-base leading-7 text-bone-dim">Observability tells you what happened inside one platform. A ReasoningReceipt gives you evidence that survives outside it—portable across models, clouds, chains, auditors, and time.</p></div>
      </div>

      <div className="relative mt-14 grid border-y border-ink-3 md:grid-cols-3">
        {stages.map((stage, index) => (
          <article key={stage.id} className="group relative min-h-[340px] border-b border-ink-3 p-6 transition-colors hover:bg-ink-2/70 md:border-b-0 md:border-r md:p-8 last:md:border-r-0">
            <div className="flex items-center justify-between font-mono text-[9px] uppercase tracking-[0.17em]"><span className="text-lime">{stage.id} / {stage.kind}</span><span className="text-bone-faint">{stage.hash}</span></div>
            <div className="my-9 flex items-center"><span className="grid h-12 w-12 place-items-center rounded-full border border-lime bg-lime-soft font-mono text-[10px] text-lime">0{index + 1}</span><span className="h-px flex-1 bg-gradient-to-r from-lime to-ink-3" /><span className="h-2 w-2 rotate-45 border border-ink-3 group-hover:border-lime" /></div>
            <h3 className="font-display text-3xl italic sm:text-4xl">{stage.title}</h3>
            <p className="mt-4 max-w-sm text-sm leading-6 text-bone-dim">{stage.copy}</p>
            <div className="absolute bottom-6 left-6 right-6 flex justify-between border-t border-dotted border-ink-3 pt-3 font-mono text-[8px] uppercase tracking-[0.14em] text-bone-faint md:bottom-8 md:left-8 md:right-8"><span>deterministic</span><span className="text-lime">pass ✓</span></div>
          </article>
        ))}
      </div>

      <div className="mx-5 mt-8 flex flex-col gap-4 border border-lime/40 bg-lime-soft p-5 sm:mx-8 sm:flex-row sm:items-center sm:justify-between lg:mx-12 xl:mx-16">
        <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-lime">Output / one portable reasoning-receipt/1 envelope</div>
        <div className="font-mono text-[9px] text-bone-dim">root 0x91c03e882a7f14aa31 · 3 proofs available · no chain required</div>
      </div>
    </section>
  );
}
