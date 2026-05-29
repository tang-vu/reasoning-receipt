"use client";

/**
 * 2D SVG fallback for the reasoning DAG.
 *
 * Used on mobile + when `prefers-reduced-motion: reduce` is set + when WebGL
 * is unavailable. Same graph data, projected onto X/Y plane (z ignored), no
 * animation. Click-to-select still works via the shared zustand store.
 */

import { type DagGraph, nodeColor } from "@/lib/trace-to-graph";
import { useDagStore } from "@/lib/dag-store";

const VIEWBOX = 720;
const PAD = 40;

function project(x: number, y: number): { x: number; y: number } {
  // map [-2, 2] → [PAD, VIEWBOX-PAD]
  const norm = (v: number) => ((v + 2) / 4) * (VIEWBOX - 2 * PAD) + PAD;
  return { x: norm(x), y: VIEWBOX - norm(y) };
}

export function DagFallback({ graph }: { graph: DagGraph }) {
  const select = useDagStore((s) => s.select);
  const selectedNodeId = useDagStore((s) => s.selectedNodeId);

  const byId = new Map(graph.nodes.map((n) => [n.id, n]));

  return (
    <svg
      viewBox={`0 0 ${VIEWBOX} ${VIEWBOX}`}
      className="h-full w-full rounded-xl border border-border bg-[radial-gradient(ellipse_at_center,#0b1424_0%,#050912_70%)]"
      role="img"
      aria-label="2D reasoning DAG"
    >
      {/* Edges */}
      {graph.edges.map((e, i) => {
        const a = byId.get(e.from);
        const b = byId.get(e.to);
        if (!a || !b) return null;
        const pa = project(a.position.x, a.position.y);
        const pb = project(b.position.x, b.position.y);
        return (
          <line
            key={`${e.from}->${e.to}-${i}`}
            x1={pa.x}
            y1={pa.y}
            x2={pb.x}
            y2={pb.y}
            stroke={nodeColor(b)}
            strokeOpacity={Math.max(0.18, Math.min(1, e.weight))}
            strokeWidth={1 + e.weight * 1.5}
          />
        );
      })}
      {/* Nodes */}
      {graph.nodes.map((n) => {
        const p = project(n.position.x, n.position.y);
        const color = nodeColor(n);
        const r =
          n.kind === "claim"
            ? 14
            : n.kind === "supervisor" || n.kind === "critic_audit"
              ? 12
              : n.kind === "stance"
                ? 10
                : 7;
        const selected = selectedNodeId === n.id;
        return (
          <g
            key={n.id}
            onClick={() => select(selected ? null : n.id)}
            style={{ cursor: "pointer" }}
          >
            <circle
              cx={p.x}
              cy={p.y}
              r={r + (selected ? 4 : 0)}
              fill={color}
              fillOpacity={selected ? 1 : 0.85}
              stroke={selected ? "#fff" : "transparent"}
              strokeWidth={1.5}
            />
            <text
              x={p.x}
              y={p.y - r - 6}
              textAnchor="middle"
              fontSize={10}
              fontFamily="ui-monospace, monospace"
              fill="#e5e7eb"
              opacity={selected ? 1 : 0.75}
              style={{ pointerEvents: "none" }}
            >
              {n.label}
            </text>
          </g>
        );
      })}
    </svg>
  );
}
