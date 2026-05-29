"use client";

/**
 * Side panel that opens when the user clicks a DAG node.
 *
 * Reads selection from the shared zustand store; renders the node's full
 * detail (full reasoning fragment, link if evidence, score badge).
 */

import { type DagGraph, type GraphNode, nodeColor } from "@/lib/trace-to-graph";
import { useDagStore } from "@/lib/dag-store";

const KIND_LABEL: Record<GraphNode["kind"], string> = {
  claim: "Final claim",
  stance: "Stance",
  supervisor: "Supervisor synthesis",
  critic_audit: "Critic audit",
  critic_dim: "Critic dimension",
  evidence: "Evidence",
  counter_argument: "Counter-argument",
  sensitivity: "Sensitivity",
  falsifiable: "Falsifiable claim",
  prior_context: "Prior context",
};

export function DagDetailPanel({ graph }: { graph: DagGraph }) {
  const selectedNodeId = useDagStore((s) => s.selectedNodeId);
  const select = useDagStore((s) => s.select);

  if (!selectedNodeId) {
    return (
      <div className="rounded-xl border border-border bg-panel/60 p-4 text-xs text-muted">
        Click a node to see its content. Drag to rotate, scroll to zoom.
      </div>
    );
  }
  const node = graph.nodes.find((n) => n.id === selectedNodeId);
  if (!node) return null;

  const color = nodeColor(node);

  return (
    <aside className="rounded-xl border border-border bg-panel/80 p-4 backdrop-blur">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-2.5 rounded-full"
            style={{ backgroundColor: color }}
            aria-hidden
          />
          <div className="text-xs uppercase tracking-wider text-muted">
            {KIND_LABEL[node.kind]}
          </div>
        </div>
        <button
          onClick={() => select(null)}
          className="text-xs text-muted hover:text-ink"
          aria-label="Close panel"
        >
          ×
        </button>
      </div>
      <div className="mt-2 text-sm font-medium text-ink">{node.label}</div>
      {node.detail && <p className="mt-2 text-sm text-ink/80">{node.detail}</p>}
      {node.url && (
        <a
          href={node.url}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-block text-xs text-accent hover:underline"
        >
          Open source ↗
        </a>
      )}
      {typeof node.score === "number" && (
        <div className="mt-3 border-t border-border pt-2 font-mono text-xs text-muted">
          score · {node.score.toFixed(2)}
        </div>
      )}
      <div className="mt-3 border-t border-border pt-2 font-mono text-[10px] text-muted/70">
        id · {node.id}
      </div>
    </aside>
  );
}
