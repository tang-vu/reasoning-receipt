"use client";

/**
 * Top-level DAG panel for a single rr-trace/3 receipt.
 *
 * Responsibilities:
 *   - Fetch the full trace via the existing /verify endpoint (same path used
 *     by V3DetailPanels).
 *   - Build the graph via traceToGraph.
 *   - Decide between the Three.js Canvas and the 2D SVG fallback based on
 *     viewport width + reduced-motion preference.
 *   - Render replay controls + the click-to-select detail panel.
 */

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import {
  type DagGraph,
  type ReasoningTraceV3Like,
  traceToGraph,
} from "@/lib/trace-to-graph";
import { useDagStore } from "@/lib/dag-store";

import { DagDetailPanel } from "./dag-detail-panel";
import { DagFallback } from "./dag-fallback";

// Lazy + SSR-disabled because Three.js touches window. Static export ('output:
// export') would otherwise fail on server prerender.
const DagView = dynamic(() => import("./dag-view").then((m) => m.DagView), {
  ssr: false,
  loading: () => (
    <div className="flex h-full w-full items-center justify-center text-xs text-muted">
      Loading 3D scene…
    </div>
  ),
});

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const m = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(m.matches);
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    m.addEventListener("change", onChange);
    return () => m.removeEventListener("change", onChange);
  }, []);
  return reduced;
}

function useIsMobile(): boolean {
  const [mobile, setMobile] = useState(false);
  useEffect(() => {
    if (typeof window === "undefined") return;
    const check = () => setMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);
  return mobile;
}

export function DagPanel({ receiptId }: { receiptId: number }) {
  const [trace, setTrace] = useState<ReasoningTraceV3Like | null>(null);
  const [error, setError] = useState<string | null>(null);
  const reducedMotion = usePrefersReducedMotion();
  const mobile = useIsMobile();
  const [forceFallback, setForceFallback] = useState(false);
  const togglePlay = useDagStore((s) => s.togglePlay);
  const isPlaying = useDagStore((s) => s.isPlaying);
  const setStep = useDagStore((s) => s.setStep);
  const totalSteps = useDagStore((s) => s.totalSteps);
  const reset = useDagStore((s) => s.reset);

  useEffect(() => {
    let cancelled = false;
    reset();
    api
      .verify(receiptId)
      .then((res) => {
        if (cancelled) return;
        if (res.fetched_trace) {
          setTrace(res.fetched_trace as unknown as ReasoningTraceV3Like);
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
  }, [receiptId, reset]);

  const graph: DagGraph | null = useMemo(
    () => (trace ? traceToGraph(trace) : null),
    [trace],
  );

  if (error) {
    return (
      <div className="rounded-xl border border-border bg-panel p-5 text-sm text-muted">
        Could not load trace for DAG view ({error}).
      </div>
    );
  }
  if (!graph) {
    return (
      <div className="rounded-xl border border-border bg-panel p-5 text-sm text-muted">
        Loading reasoning DAG…
      </div>
    );
  }

  const use2D = forceFallback || mobile || reducedMotion;

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <h2 className="text-lg font-semibold">3D reasoning DAG</h2>
        <div className="flex items-center gap-3 text-xs text-muted">
          <span className="font-mono">{graph.nodes.length} nodes · {graph.edges.length} edges</span>
          <button
            onClick={() => setForceFallback((v) => !v)}
            className="rounded-md border border-border px-2 py-0.5 hover:text-ink"
            title="Toggle 3D / 2D"
          >
            {use2D ? "Try 3D" : "Use 2D"}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-[1fr_280px]">
        <div className="relative h-[480px] overflow-hidden rounded-xl border border-border">
          {use2D ? <DagFallback graph={graph} /> : <DagView graph={graph} />}
        </div>
        <DagDetailPanel graph={graph} />
      </div>

      {!use2D && (
        <div className="flex items-center gap-3 text-xs text-muted">
          <button
            onClick={() => {
              if (!isPlaying) setStep(0);
              togglePlay();
            }}
            className="rounded-md border border-border px-3 py-1 hover:text-ink"
          >
            {isPlaying ? "Pause" : "Replay debate"}
          </button>
          <button
            onClick={() => setStep(totalSteps || graph.nodes.length)}
            className="text-muted hover:text-ink"
          >
            Show all
          </button>
          <span className="font-mono">
            step {Math.min(Math.ceil(useDagStore.getState().step), totalSteps || graph.nodes.length)}/
            {totalSteps || graph.nodes.length}
          </span>
        </div>
      )}
    </section>
  );
}
