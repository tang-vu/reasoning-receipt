import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "The five agents",
  description:
    "Bull, Bear, Edge run in parallel with isolated context. Supervisor merges weighted-Bayesian. Critic audits across six rigor dimensions. The 5-agent ensemble inside ReasoningReceipt.",
  alternates: { canonical: "/agents/" },
};

const agents = [
  {
    role: "Bull",
    color: "bg-accent/10 border-accent/40 text-accent",
    job: "Argue YES — strongest defensible case",
    model: "Gemini 3.1 Pro Preview (Vertex AI, global region)",
    grounding: "Google Search at request time",
    isolation: "Sees only the market prompt — never Bear or Edge's drafts",
    output: "probability_estimate ≥ 0.55, key factors, ≥ 2 cited evidence URLs",
  },
  {
    role: "Bear",
    color: "bg-danger/10 border-danger/40 text-danger",
    job: "Argue NO — strongest defensible case",
    model: "Gemini 3.1 Pro Preview (Vertex AI, global region)",
    grounding: "Google Search at request time",
    isolation: "Same — opposite advocate, independent context",
    output: "probability_estimate ≤ 0.45, key factors, ≥ 2 cited evidence URLs",
  },
  {
    role: "Edge",
    color: "bg-accent2/10 border-accent2/40 text-accent2",
    job: "Surface tail risks both partisans miss",
    model: "Gemini 3.1 Pro Preview (Vertex AI, global region)",
    grounding: "Google Search at request time",
    isolation: "Same — adversarial-to-conventional-wisdom, independent context",
    output: "Tail-risk factors, structural assumptions, ≥ 1 historical analog",
  },
  {
    role: "Supervisor",
    color: "bg-panel border-border text-ink",
    job: "Weighted-Bayesian merge of three stances",
    model: "Gemini 3.1 Pro Preview, low temperature (0.2)",
    grounding: "None — synthesises drafts, no fresh search",
    isolation: "Reads all three drafts. Cannot reach back to a stance for clarification.",
    output:
      "final probability + confidence, stance weights ∈ [0.1, 0.7] summing to 1.0, disagreement_pp, mandatory ≥ 1 falsifiable claim with checkable_by date, calibration_prior_used",
  },
  {
    role: "Critic",
    color: "bg-panel border-border text-ink",
    job: "Audit the merged trace across 6 rigor dimensions",
    model: "Gemini 3 Flash Preview (smaller, faster, cheaper)",
    grounding: "None — reads only the trace under audit",
    isolation: "Single pass. Returns verdict: approved / needs_revision / rejected.",
    output:
      "Per-dim score [0, 1]: evidence_relevance, falsifiability, scope, coherence, exploration_integrity, methodology. Rule overrides model self-report.",
  },
];

export default function AgentsPage() {
  return (
    <div className="space-y-8">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight">The five agents</h1>
        <p className="max-w-3xl text-muted">
          Each market goes through a structured debate. Three sub-researchers run in parallel with
          isolated context — they don&apos;t see each other&apos;s drafts. A Supervisor merges with
          a weighted-Bayesian rule + mandates a falsifiable claim. A Critic audits the result
          across six rigor dimensions; if any dim falls below 0.4 the Supervisor re-runs once with
          the critic&apos;s feedback inlined. Receipts that fail audit on the second pass never reach
          the chain.
        </p>
      </header>

      {/* Flow chart */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Pipeline</h2>
        <div className="overflow-x-auto rounded-xl border border-border bg-panel p-5 font-mono text-xs leading-relaxed text-muted">
          <pre>
{`     scanner — Polymarket Gamma poll
          │
          ▼
   ┌──────┼──────┐
   ▼      ▼      ▼
 [Bull]  [Bear]  [Edge]       ← parallel, isolated context, ~3s per stance
   │      │      │
   └──────┼──────┘
          ▼
     [Supervisor]              ← weighted-Bayesian merge, mandates falsifiable claim,
          │                      consumes calibration_prior from past Brier
          ▼
       [Critic]                ← 6-dim audit; verdict ∈ {approved, needs_revision, rejected}
          │
     ┌────┴────┐
     │ needs_  │ approved │ rejected
     │revision │          │
     ▼         ▼          ▼
   Supervisor  emit on    SKIP — no on-chain commit,
   re-runs    Arc V2 +    no calibration noise
   once       Irys upload`}
          </pre>
        </div>
      </section>

      {/* Agent cards */}
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Agent cards</h2>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          {agents.map((a) => (
            <div key={a.role} className={`rounded-xl border p-4 ${a.color.split(" ").slice(0, 2).join(" ")}`}>
              <div className={`text-xs uppercase tracking-wider ${a.color.split(" ")[2]}`}>{a.role}</div>
              <div className="mt-1 font-semibold text-ink">{a.job}</div>
              <dl className="mt-3 space-y-1 text-xs">
                <Row k="Model" v={a.model} />
                <Row k="Grounding" v={a.grounding} />
                <Row k="Context isolation" v={a.isolation} />
                <Row k="Output" v={a.output} />
              </dl>
            </div>
          ))}
        </div>
      </section>

      {/* Fallback chain */}
      <section className="space-y-3 rounded-xl border border-border bg-panel p-5">
        <h2 className="text-lg font-semibold">Multi-model fallback</h2>
        <p className="text-sm text-muted">
          Every Gemini call routes through a fallback chain. When the primary 429s — usually Pro
          Preview hitting the free-tier quota mid-tick — the wrapper retries the next model in the
          chain transparently. The fallback has fired hundreds of times in production today, keeping
          the loop emitting receipts without any operator intervention.
        </p>
        <pre className="overflow-x-auto rounded-lg bg-bg p-3 font-mono text-xs text-muted">
{`Stance + Supervisor: gemini-3.1-pro-preview → gemini-3-flash-preview → gemini-2.5-flash
Critic:              gemini-3-flash-preview → gemini-2.5-flash → gemini-2.5-flash-lite`}
        </pre>
      </section>

      {/* Watch live */}
      <section className="rounded-xl border border-accent/40 bg-accent/5 p-5">
        <h2 className="text-lg font-semibold">Watch them debate in real time</h2>
        <p className="mt-2 text-sm text-muted">
          The <Link href="/" className="text-accent hover:underline">home page</Link> has a live
          SSE feed. The <span className="font-mono text-xs">v3</span> pill on a row tells you the
          receipt came out of a 5-agent debate; hover to see the Bull/Bear/Edge disagreement in
          percentage points. Click any v3 row → see the full ensemble panel, the critic radar, and
          the falsifiable claims the supervisor committed to.
        </p>
      </section>
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <dt className="w-32 shrink-0 text-muted">{k}</dt>
      <dd className="text-ink">{v}</dd>
    </div>
  );
}
