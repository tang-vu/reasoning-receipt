/**
 * Five stance "strips" ported from design-landing/index.html `.debate`.
 * Each column is its own column-rule-separated micro-essay: role title in
 * italic display serif, a stance pill, the model's actual claim in italic,
 * evidence list, big italic probability at the bottom. Critic strip has
 * a 6-dim audit meter + a hand-stamped verdict.
 *
 * Static / illustrative — these aren't pulled from a live receipt; they
 * show the *shape* of every receipt so judges grok the schema at a glance.
 */

interface Strip {
  role: "bull" | "bear" | "edge" | "super" | "critic";
  title: string;
  sub: string;
  stance?: string;
  claim: string;
  evidence?: Array<{ tick: string; line: string; src?: string }>;
  prob?: { n: string; label: string };
  criticDims?: Array<{ label: string; filled: number; warn?: number }>;
  verdict?: string;
}

const strips: Strip[] = [
  {
    role: "bull",
    title: "Bull",
    sub: "Argues YES · Gemini Flash · isolated context",
    stance: "YES · 0.62",
    claim:
      "FOMC futures already price in a 56% cut probability; chair Powell's last presser tilts dovish.",
    evidence: [
      { tick: "✓", line: "CME FedWatch · 56% implied for May cut", src: "cmegroup.com" },
      { tick: "✓", line: "FOMC March minutes · two dot-plot dovish shifts", src: "federalreserve.gov" },
      { tick: "✓", line: "Core PCE trailing 12m at 2.7%, inside trend", src: "bea.gov" },
    ],
    prob: { n: "0.62", label: "yes" },
  },
  {
    role: "bear",
    title: "Bear",
    sub: "Argues NO · Gemini Flash · isolated context",
    stance: "NO · 0.34",
    claim:
      "Sticky services inflation + tight labor → Fed holds. Cut implied prob is overpriced by retail flow.",
    evidence: [
      { tick: "✗", line: "Services CPI re-accelerating month-over-month", src: "bls.gov" },
      { tick: "✗", line: "JOLTS holding above 8M openings", src: "bls.gov" },
      { tick: "✗", line: "Williams (NY Fed): 'no rush' speech, April 11", src: "nyfed.org" },
    ],
    prob: { n: "0.34", label: "no" },
  },
  {
    role: "edge",
    title: "Edge",
    sub: "Surfaces tail risks · Gemini Flash",
    stance: "Tail · 0.48",
    claim:
      "Geopolitical oil shock or banking-sector wobble could force an off-script intermeeting cut.",
    evidence: [
      { tick: "△", line: "Iran-Israel escalation · WTI repricing risk", src: "reuters" },
      { tick: "△", line: "Regional bank CRE write-downs Q2", src: "fdic.gov" },
      { tick: "△", line: "Past intermeeting precedent: 2008, 2020", src: "historical" },
    ],
    prob: { n: "0.48", label: "tail" },
  },
  {
    role: "super",
    title: "Supervisor",
    sub: "Weighted-Bayesian merge · Gemini Pro · low temp",
    claim:
      "Weighting Bull 0.42, Bear 0.38, Edge 0.20. Falsifiable claim: cut requires next CPI ≤ 2.5%.",
    prob: { n: "0.58", label: "merged" },
    evidence: [
      { tick: "·", line: "weights ∈ [0.1, 0.7], sum = 1.0" },
      { tick: "·", line: "disagreement_pp = 28pp (bull − bear)" },
      { tick: "·", line: "calibration prior: macro Brier 0.184 (last 30d)" },
    ],
  },
  {
    role: "critic",
    title: "Critic",
    sub: "ARA 6-dim audit · Gemini Flash",
    claim: "Evidence relevance and falsifiability both above 0.7. Methodology spotless.",
    criticDims: [
      { label: "evidence_relevance", filled: 8 },
      { label: "falsifiability", filled: 9 },
      { label: "scope", filled: 7 },
      { label: "coherence", filled: 8 },
      { label: "exploration_integrity", filled: 7 },
      { label: "methodology", filled: 9 },
    ],
    verdict: "Approved · emit",
  },
];

export function LandingDebate() {
  return (
    <section className="space-y-8 sm:space-y-12">
      <header className="flex flex-col gap-6 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between sm:gap-10">
        <div className="min-w-0">
          <div
            className="mb-3 inline-flex items-center gap-3 text-[11px] uppercase tracking-[0.16em] sm:mb-4 sm:text-[11.5px] sm:tracking-[0.18em]"
            style={{ fontFamily: "var(--f-mono)", color: "var(--bone-faint)" }}
          >
            <span aria-hidden style={{ width: 24, height: 1, background: "var(--bone-faint)" }} />
            01 · the debate
          </div>
          <h2
            className="max-w-[14ch] text-balance leading-[1] tracking-[-0.015em] sm:leading-[0.96]"
            style={{
              fontFamily: "var(--f-display)",
              fontWeight: 400,
              fontSize: "clamp(32px, 7vw, 84px)",
            }}
          >
            Five agents{" "}
            <span className="italic" style={{ color: "var(--lime)" }}>
              debate
            </span>
            . Two stamp.
          </h2>
        </div>
        <p
          className="max-w-[380px] text-[15px] leading-[1.55] sm:text-[16px]"
          style={{ color: "var(--bone-dim)" }}
        >
          Bull, Bear, Edge run in parallel with isolated context. A supervisor merges
          weighted-Bayesian. A critic audits across six rigor dimensions. ~21% of receipts
          fail the gate and never reach the chain.
        </p>
      </header>

      <div
        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5"
        style={{ borderTop: "1px solid var(--ink-3)", borderBottom: "1px solid var(--ink-3)" }}
      >
        {strips.map((s) => (
          <StripCol key={s.role} strip={s} />
        ))}
      </div>
    </section>
  );
}

const ROLE_COLOR: Record<Strip["role"], string> = {
  bull: "var(--lime)",
  bear: "var(--terra)",
  edge: "var(--amber)",
  super: "var(--bone)",
  critic: "var(--bone)",
};

function StripCol({ strip }: { strip: Strip }) {
  const color = ROLE_COLOR[strip.role];
  const isSpecial = strip.role === "super" || strip.role === "critic";
  return (
    <div
      className="relative flex min-h-[320px] flex-col border-b border-r border-ink-3 p-5 font-mono text-[12.5px] last:border-b-0 last:border-r-0 sm:p-6 lg:min-h-[480px] lg:border-b-0 lg:p-7"
      style={{
        color: "var(--bone-dim)",
        background: isSpecial ? "oklch(0.17 0.006 80)" : "var(--ink)",
      }}
    >
      <div
        className="text-[32px] italic leading-none"
        style={{ fontFamily: "var(--f-display)", color }}
      >
        {strip.title}
      </div>
      <div
        className="mt-1 text-[10.5px] uppercase tracking-[0.14em]"
        style={{ color: "var(--bone-faint)" }}
      >
        {strip.sub}
      </div>

      {strip.stance && (
        <div
          className="mt-4 inline-block w-fit border px-2 py-0.5 text-[10px] uppercase tracking-[0.14em]"
          style={{ borderColor: color, color }}
        >
          {strip.stance}
        </div>
      )}

      <div
        className="my-4 text-[18px] italic leading-snug"
        style={{ fontFamily: "var(--f-display)", color: "var(--bone)" }}
      >
        {strip.claim}
      </div>

      {strip.evidence && (
        <ul className="mb-4 list-none p-0" style={{ borderTop: "1px dashed var(--ink-3)" }}>
          {strip.evidence.map((e, i) => (
            <li
              key={i}
              className="grid grid-cols-[auto_1fr] items-start gap-2.5 py-2.5 text-[11.5px]"
              style={{ borderBottom: "1px dashed var(--ink-3)", color: "var(--bone-dim)" }}
            >
              <span style={{ color }}>{e.tick}</span>
              <span>
                {e.line}
                {e.src && (
                  <span
                    className="col-span-2 mt-0.5 block text-[10px]"
                    style={{ color: "var(--bone-faint)" }}
                  >
                    {e.src}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}

      {strip.criticDims && (
        <div className="mb-4 mt-1 space-y-2">
          {strip.criticDims.map((d) => (
            <div
              key={d.label}
              className="grid grid-cols-[1fr_auto] items-center gap-2.5 text-[11px]"
              style={{ color: "var(--bone-dim)" }}
            >
              <span>{d.label}</span>
              <span className="flex gap-0.5">
                {Array.from({ length: 10 }).map((_, i) => (
                  <span
                    key={i}
                    className="block h-2.5 w-2"
                    style={{
                      background:
                        i < d.filled
                          ? d.warn && i >= d.filled - d.warn
                            ? "var(--terra)"
                            : "var(--lime)"
                          : "var(--ink-3)",
                    }}
                  />
                ))}
              </span>
            </div>
          ))}
        </div>
      )}

      {strip.verdict && (
        <div
          className="mt-2 inline-flex w-fit items-center gap-2 border-[1.5px] px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-[0.14em]"
          style={{
            borderColor: "var(--lime)",
            color: "var(--lime)",
            transform: "rotate(-2deg)",
          }}
        >
          ⌐ {strip.verdict}
        </div>
      )}

      {strip.prob && (
        <div
          className="mt-auto flex items-baseline gap-2.5 pt-3.5"
          style={{ borderTop: "1px solid var(--ink-3)" }}
        >
          <span
            className="italic leading-[0.9]"
            style={{ fontFamily: "var(--f-display)", fontSize: 44, color }}
          >
            {strip.prob.n}
          </span>
          <span
            className="text-[10.5px] uppercase tracking-[0.14em]"
            style={{ color: "var(--bone-faint)" }}
          >
            {strip.prob.label}
          </span>
        </div>
      )}
    </div>
  );
}
