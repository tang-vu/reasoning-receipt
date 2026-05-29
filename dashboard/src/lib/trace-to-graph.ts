/**
 * Adapter: rr-trace/3 ReasoningTraceV3 JSON → DAG graph for visualization.
 *
 * Pure data transform. No DOM, no Three.js types. Layout is computed in a
 * radial-layered scheme so the same graph renders identically across the 3D
 * Canvas and the 2D SVG fallback.
 *
 * Layer semantics:
 *   0 → claim (root)
 *   1 → stances (bull / bear / edge), critic audit, supervisor synthesis
 *   2 → evidence (under stances), critic dimensions (under audit),
 *       falsifiables / counter-args / sensitivity (orbit the claim)
 *
 * Coordinates are unit-less; the renderer scales them.
 */

export type NodeKind =
  | "claim"
  | "stance"
  | "supervisor"
  | "critic_audit"
  | "critic_dim"
  | "evidence"
  | "counter_argument"
  | "sensitivity"
  | "falsifiable"
  | "prior_context"; // reserved for Phase 2

export interface GraphNode {
  id: string;
  kind: NodeKind;
  label: string; // short, shown next to node
  detail: string; // longer body, shown on click
  /** [-1, 1] roughly; renderer scales to scene size. */
  position: { x: number; y: number; z: number };
  /** Optional confidence-like score; renderer uses for color/intensity. */
  score?: number;
  /** Stance role for color mapping (bull/bear/edge_case). */
  role?: string;
  /** For evidence nodes — outbound link. */
  url?: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  /** Visual weight ∈ [0, 1]. */
  weight: number;
}

export interface DagGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

interface TraceEvidence {
  id: string;
  url: string;
  title: string;
  cited_for: string;
}

interface TraceStance {
  id: string;
  role: string;
  model: string;
  probability_estimate: number;
  confidence: number;
  key_factors: string[];
  evidence: TraceEvidence[];
  weight_in_synthesis: number;
}

interface TraceCriticDim {
  score: number;
  notes: string;
}

interface TraceCriticAudit {
  version: string;
  verdict: string;
  evidence_relevance: TraceCriticDim;
  falsifiability: TraceCriticDim;
  scope: TraceCriticDim;
  coherence: TraceCriticDim;
  exploration_integrity: TraceCriticDim;
  methodology: TraceCriticDim;
}

interface TraceFalsifiable {
  id: string;
  text: string;
  checkable_by: string;
  failure_implies: string;
}

interface TraceCounterArgument {
  id: string;
  claim: string;
  weight: number;
  rebuttal?: string | null;
}

interface TraceSensitivity {
  id: string;
  factor: string;
  delta_pp: number;
  note?: string | null;
}

interface TraceSupervisor {
  merge_method: string;
  disagreement_pp: number;
  synthesis_reasoning: string;
  calibration_prior_used?: string | null;
}

interface TraceClaim {
  id: string;
  text: string;
  probability: number;
  confidence: number;
}

export interface ReasoningTraceV3Like {
  schema_version: string;
  market_question?: string;
  category?: string;
  claim: TraceClaim;
  stances: TraceStance[];
  supervisor_synthesis: TraceSupervisor;
  critic_audit: TraceCriticAudit;
  falsifiable_claims: TraceFalsifiable[];
  counter_arguments: TraceCounterArgument[];
  sensitivity: TraceSensitivity[];
}

const STANCE_ANGLE: Record<string, number> = {
  bull: -Math.PI / 6, // upper-right
  bear: Math.PI + Math.PI / 6, // lower-left
  edge_case: Math.PI / 2, // top
};

function stanceAngle(role: string, fallbackIdx: number): number {
  if (role in STANCE_ANGLE) return STANCE_ANGLE[role];
  return (fallbackIdx * 2 * Math.PI) / 3;
}

function truncate(s: string, n: number): string {
  if (!s) return "";
  return s.length <= n ? s : s.slice(0, n - 1) + "…";
}

/** Build the graph. Pure function — same input always yields same output. */
export function traceToGraph(trace: ReasoningTraceV3Like): DagGraph {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];

  // Layer 0 — claim at origin.
  nodes.push({
    id: trace.claim.id,
    kind: "claim",
    label: `Claim · ${(trace.claim.probability * 100).toFixed(1)}%`,
    detail: trace.claim.text,
    position: { x: 0, y: 0, z: 0 },
    score: trace.claim.confidence,
  });

  // Layer 1 — stances orbit on a ring radius ~1.2, vertical y=+0.8.
  const stanceRadius = 1.2;
  const stanceY = 0.8;
  trace.stances.forEach((stance, idx) => {
    const angle = stanceAngle(stance.role, idx);
    nodes.push({
      id: stance.id,
      kind: "stance",
      role: stance.role,
      label: `${stance.role.toUpperCase()} · ${(stance.probability_estimate * 100).toFixed(0)}%`,
      detail: stance.key_factors.join(" · "),
      position: {
        x: Math.cos(angle) * stanceRadius,
        y: stanceY,
        z: Math.sin(angle) * stanceRadius,
      },
      score: stance.confidence,
    });
    edges.push({
      from: stance.id,
      to: trace.claim.id,
      weight: stance.weight_in_synthesis,
    });

    // Layer 2 — evidence orbits its parent stance.
    const evRadius = 0.45;
    stance.evidence.forEach((ev, evIdx) => {
      const evAngle = angle + (evIdx - (stance.evidence.length - 1) / 2) * 0.4;
      nodes.push({
        id: ev.id,
        kind: "evidence",
        label: truncate(ev.title, 32),
        detail: `${ev.title} — ${ev.cited_for}`,
        position: {
          x: Math.cos(evAngle) * (stanceRadius + evRadius),
          y: stanceY + 0.4,
          z: Math.sin(evAngle) * (stanceRadius + evRadius),
        },
        url: ev.url,
      });
      edges.push({ from: ev.id, to: stance.id, weight: 0.5 });
    });
  });

  // Layer 1 — supervisor synthesis directly above the claim.
  const supervisorId = "supervisor";
  nodes.push({
    id: supervisorId,
    kind: "supervisor",
    label: `Synthesis · ${trace.supervisor_synthesis.disagreement_pp.toFixed(1)}pp Δ`,
    detail: trace.supervisor_synthesis.synthesis_reasoning,
    position: { x: 0, y: 1.6, z: 0 },
  });
  edges.push({ from: supervisorId, to: trace.claim.id, weight: 1 });

  // Layer 1 — critic audit below the claim.
  const auditId = "critic_audit";
  nodes.push({
    id: auditId,
    kind: "critic_audit",
    label: `Audit · ${trace.critic_audit.verdict.replace("_", " ")}`,
    detail: `Critic v2 (${trace.critic_audit.version})`,
    position: { x: 0, y: -0.8, z: 0 },
  });
  edges.push({ from: auditId, to: trace.claim.id, weight: 0.7 });

  // Layer 2 — 6 critic dimensions on a lower ring under the audit.
  const dims: Array<[string, TraceCriticDim]> = [
    ["evidence_relevance", trace.critic_audit.evidence_relevance],
    ["falsifiability", trace.critic_audit.falsifiability],
    ["scope", trace.critic_audit.scope],
    ["coherence", trace.critic_audit.coherence],
    ["exploration_integrity", trace.critic_audit.exploration_integrity],
    ["methodology", trace.critic_audit.methodology],
  ];
  const dimRadius = 1.0;
  dims.forEach(([name, dim], i) => {
    const angle = (i * 2 * Math.PI) / dims.length + Math.PI;
    nodes.push({
      id: `cd_${name}`,
      kind: "critic_dim",
      label: `${name.replace(/_/g, " ")} · ${dim.score.toFixed(2)}`,
      detail: dim.notes,
      position: {
        x: Math.cos(angle) * dimRadius,
        y: -1.4,
        z: Math.sin(angle) * dimRadius,
      },
      score: dim.score,
    });
    edges.push({ from: `cd_${name}`, to: auditId, weight: dim.score });
  });

  // Layer 2 — falsifiables on the right.
  trace.falsifiable_claims.forEach((fc, i) => {
    nodes.push({
      id: fc.id,
      kind: "falsifiable",
      label: truncate(fc.text, 28),
      detail: `${fc.text} (checkable by ${fc.checkable_by}; if fails → ${fc.failure_implies})`,
      position: {
        x: 1.8,
        y: 0.4 - i * 0.4,
        z: -1.2,
      },
    });
    edges.push({ from: fc.id, to: trace.claim.id, weight: 0.4 });
  });

  // Layer 2 — counter-arguments on the left.
  trace.counter_arguments.forEach((ca, i) => {
    nodes.push({
      id: ca.id,
      kind: "counter_argument",
      label: truncate(ca.claim, 28),
      detail: ca.rebuttal ? `${ca.claim} → ${ca.rebuttal}` : ca.claim,
      position: {
        x: -1.8,
        y: 0.4 - i * 0.4,
        z: -1.2,
      },
      score: ca.weight,
    });
    edges.push({ from: ca.id, to: trace.claim.id, weight: ca.weight });
  });

  // Layer 2 — sensitivity factors at the front.
  trace.sensitivity.forEach((sn, i) => {
    nodes.push({
      id: sn.id,
      kind: "sensitivity",
      label: `${truncate(sn.factor, 20)} · ${sn.delta_pp >= 0 ? "+" : ""}${sn.delta_pp.toFixed(1)}pp`,
      detail: sn.note ? `${sn.factor}: ${sn.note}` : sn.factor,
      position: {
        x: -0.6 + i * 0.6,
        y: 0,
        z: 1.6,
      },
    });
    edges.push({ from: sn.id, to: trace.claim.id, weight: 0.3 });
  });

  return { nodes, edges };
}

export const NODE_COLORS: Record<NodeKind, string> = {
  claim: "#22d3ee",
  stance: "#fbbf24",
  supervisor: "#a78bfa",
  critic_audit: "#f472b6",
  critic_dim: "#f9a8d4",
  evidence: "#34d399",
  counter_argument: "#fb7185",
  sensitivity: "#60a5fa",
  falsifiable: "#fcd34d",
  prior_context: "#94a3b8",
};

export const STANCE_COLORS: Record<string, string> = {
  bull: "#10b981",
  bear: "#ef4444",
  edge_case: "#f59e0b",
};

export function nodeColor(node: GraphNode): string {
  if (node.kind === "stance" && node.role && node.role in STANCE_COLORS) {
    return STANCE_COLORS[node.role];
  }
  return NODE_COLORS[node.kind];
}
