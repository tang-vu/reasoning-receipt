"use client";

/**
 * Tab toggle for the rr-trace/3 detail view: classic JSON panels vs the new
 * 3D DAG. Default tab = JSON (existing UX preserved).
 */

import { useState } from "react";

import { V3DetailPanels } from "./v3-detail-panels";
import { DagPanel } from "./dag-panel";

type Tab = "panels" | "dag";

export function TraceViewTabs({ receiptId }: { receiptId: number }) {
  const [tab, setTab] = useState<Tab>("panels");

  return (
    <section className="space-y-3">
      <div
        role="tablist"
        aria-label="Trace view"
        className="flex gap-1 rounded-lg border border-border bg-panel/60 p-1 text-xs"
      >
        <button
          role="tab"
          aria-selected={tab === "panels"}
          onClick={() => setTab("panels")}
          className={`rounded-md px-3 py-1 ${
            tab === "panels" ? "bg-panel text-ink" : "text-muted hover:text-ink"
          }`}
        >
          Panels
        </button>
        <button
          role="tab"
          aria-selected={tab === "dag"}
          onClick={() => setTab("dag")}
          className={`rounded-md px-3 py-1 ${
            tab === "dag" ? "bg-panel text-ink" : "text-muted hover:text-ink"
          }`}
        >
          3D DAG
        </button>
      </div>
      {tab === "panels" ? <V3DetailPanels receiptId={receiptId} /> : <DagPanel receiptId={receiptId} />}
    </section>
  );
}
