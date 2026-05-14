"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

interface Evidence {
  id: string;
  url: string;
  title: string;
  cited_for: string;
}

interface Stance {
  id: string;
  role: string;
  model: string;
  probability_estimate: number;
  confidence: number;
  key_factors: string[];
  evidence: Evidence[];
  weight_in_synthesis: number;
}

interface CriticDimension {
  score: number;
  notes: string;
}

interface CriticAudit {
  version: string;
  verdict: string;
  evidence_relevance: CriticDimension;
  falsifiability: CriticDimension;
  scope: CriticDimension;
  coherence: CriticDimension;
  exploration_integrity: CriticDimension;
  methodology: CriticDimension;
}

interface FalsifiableClaim {
  id: string;
  text: string;
  checkable_by: string;
  failure_implies: string;
}

interface SupervisorSynthesis {
  merge_method: string;
  disagreement_pp: number;
  synthesis_reasoning: string;
  calibration_prior_used: string | null;
}

interface TraceV3 {
  schema_version: string;
  category: string;
  stances: Stance[];
  supervisor_synthesis: SupervisorSynthesis;
  falsifiable_claims: FalsifiableClaim[];
  critic_audit: CriticAudit;
  merkle_root: string;
}

const STANCE_ACCENT: Record<string, string> = {
  bull: "border-accent/40 bg-accent/5",
  bear: "border-danger/40 bg-danger/5",
  edge_case: "border-accent2/40 bg-accent2/5",
};

const STANCE_LABEL: Record<string, string> = {
  bull: "Bull",
  bear: "Bear",
  edge_case: "Edge",
};

/** Fetches /verify/{id} to pull the full trace JSON from Irys, then renders
 * the rr-trace/3 panels (ensemble / critic / falsifiables / supervisor).
 * Falls back to a friendly message if the trace can't be fetched. */
export function V3DetailPanels({ receiptId }: { receiptId: number }) {
  const [trace, setTrace] = useState<TraceV3 | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .verify(receiptId)
      .then((res) => {
        if (cancelled) return;
        if (res.fetched_trace) {
          setTrace(res.fetched_trace as unknown as TraceV3);
        } else {
          setError(res.reason || "trace not fetched");
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, [receiptId]);

  if (error) {
    return (
      <div className="rounded-xl border border-border bg-panel p-5 text-sm text-muted">
        Could not fetch full trace from Irys ({error}). The on-chain commit is still verifiable —
        the schema-only fields above came from the database row.
      </div>
    );
  }
  if (!trace) {
    return (
      <div className="rounded-xl border border-border bg-panel p-5 text-sm text-muted">
        Loading reasoning trace from Irys…
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <EnsemblePanel stances={trace.stances} synthesis={trace.supervisor_synthesis} />
      <CriticAuditPanel audit={trace.critic_audit} />
      <FalsifiableClaimsList claims={trace.falsifiable_claims} />
    </div>
  );
}

function EnsemblePanel({
  stances,
  synthesis,
}: {
  stances: Stance[];
  synthesis: SupervisorSynthesis;
}) {
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">5-agent ensemble</h2>
        <span className="font-mono text-xs text-muted">
          disagreement {synthesis.disagreement_pp.toFixed(1)}pp
        </span>
      </div>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
        {stances.map((s) => (
          <div
            key={s.id}
            className={`rounded-xl border p-4 ${STANCE_ACCENT[s.role] ?? "border-border bg-panel"}`}
          >
            <div className="flex items-baseline justify-between">
              <div className="text-xs uppercase tracking-wider text-muted">{STANCE_LABEL[s.role] ?? s.role}</div>
              <div className="font-mono text-xs text-muted">w {s.weight_in_synthesis.toFixed(2)}</div>
            </div>
            <div className="mt-1 font-mono text-2xl text-ink">
              {(s.probability_estimate * 100).toFixed(1)}%
            </div>
            <div className="mt-1 font-mono text-xs text-muted">conf {(s.confidence * 100).toFixed(0)}%</div>
            <ul className="mt-3 space-y-1 text-xs text-ink">
              {s.key_factors.slice(0, 3).map((k, i) => (
                <li key={i} className="leading-tight">
                  · {k}
                </li>
              ))}
            </ul>
            {s.evidence.length > 0 && (
              <div className="mt-3 space-y-1 border-t border-border pt-2 text-xs">
                {s.evidence.slice(0, 2).map((e) => (
                  <a
                    key={e.id}
                    href={e.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate text-accent hover:underline"
                    title={`${e.title} — ${e.cited_for}`}
                  >
                    {e.title}
                  </a>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
      {synthesis.synthesis_reasoning && (
        <details className="rounded-xl border border-border bg-panel p-4 text-sm">
          <summary className="cursor-pointer text-xs uppercase tracking-wider text-muted">
            Supervisor synthesis
          </summary>
          <p className="mt-2 text-ink">{synthesis.synthesis_reasoning}</p>
          {synthesis.calibration_prior_used && (
            <p className="mt-2 border-t border-border pt-2 font-mono text-xs text-muted">
              prior: {synthesis.calibration_prior_used}
            </p>
          )}
        </details>
      )}
    </section>
  );
}

function CriticAuditPanel({ audit }: { audit: CriticAudit }) {
  const dims: Array<[string, CriticDimension]> = [
    ["evidence_relevance", audit.evidence_relevance],
    ["falsifiability", audit.falsifiability],
    ["scope", audit.scope],
    ["coherence", audit.coherence],
    ["exploration_integrity", audit.exploration_integrity],
    ["methodology", audit.methodology],
  ];
  const verdictColor =
    audit.verdict === "approved"
      ? "text-accent"
      : audit.verdict === "needs_revision"
        ? "text-accent2"
        : "text-danger";
  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">Critic audit · 6 dims</h2>
        <span className={`font-mono text-xs uppercase tracking-wider ${verdictColor}`}>
          {audit.verdict.replace("_", " ")}
        </span>
      </div>
      <div className="rounded-xl border border-border bg-panel p-4">
        <ul className="space-y-2">
          {dims.map(([name, d]) => (
            <li key={name} className="flex items-center gap-3 text-sm">
              <div className="w-44 shrink-0 text-xs uppercase tracking-wider text-muted">
                {name.replace(/_/g, " ")}
              </div>
              <div className="relative h-1.5 flex-1 overflow-hidden rounded-full bg-border">
                <div
                  className={`h-full ${d.score >= 0.6 ? "bg-accent" : d.score >= 0.4 ? "bg-accent2" : "bg-danger"}`}
                  style={{ width: `${Math.max(d.score * 100, 4)}%` }}
                />
              </div>
              <div className="w-12 shrink-0 text-right font-mono text-xs tabular-nums">
                {d.score.toFixed(2)}
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function FalsifiableClaimsList({ claims }: { claims: FalsifiableClaim[] }) {
  if (claims.length === 0) return null;
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">Falsifiable claims</h2>
      <ul className="space-y-2">
        {claims.map((c) => (
          <li
            key={c.id}
            className="rounded-xl border border-border bg-panel p-4 text-sm"
          >
            <div className="text-ink">{c.text}</div>
            <div className="mt-2 flex items-center gap-3 font-mono text-xs text-muted">
              <span>checkable by {c.checkable_by}</span>
              {c.failure_implies && (
                <span className="rounded-full bg-danger/10 px-2 py-0.5 text-danger">
                  if true → {c.failure_implies} wrong
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
