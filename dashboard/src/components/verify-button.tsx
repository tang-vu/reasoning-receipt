"use client";

import { useState } from "react";

import type { VerifyResponse } from "@/lib/api";
import { api } from "@/lib/api";

type State =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ok"; data: VerifyResponse }
  | { kind: "fail"; data: VerifyResponse }
  | { kind: "error"; message: string };

export function VerifyButton({ receiptId }: { receiptId: number }) {
  const [state, setState] = useState<State>({ kind: "idle" });

  async function run() {
    setState({ kind: "loading" });
    try {
      const data = await api.verify(receiptId);
      setState({ kind: data.verified ? "ok" : "fail", data });
    } catch (e) {
      setState({ kind: "error", message: e instanceof Error ? e.message : String(e) });
    }
  }

  return (
    <div className="rounded-xl border border-border bg-panel p-5">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <div className="text-xs uppercase tracking-wider text-muted">Verify trace</div>
          <p className="mt-1 text-sm text-muted">
            Pull the trace JSON from Irys, re-canonicalise, re-hash, compare to the value bound
            on Arc. Anyone can re-run this client-side.
          </p>
        </div>
        <button
          onClick={run}
          disabled={state.kind === "loading"}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-bg hover:opacity-90 disabled:opacity-50"
        >
          {state.kind === "loading" ? "Verifying…" : "Verify"}
        </button>
      </div>

      {state.kind === "ok" && (
        <div className="mt-2 rounded-lg border border-accent/40 bg-accent/5 p-3 text-sm">
          <div className="font-semibold text-accent">VERIFIED ✓</div>
          <div className="mt-1 text-muted">{state.data.reason}</div>
          {state.data.recomputed_hash && (
            <div className="mt-2 font-mono text-xs text-ink">
              recomputed: {state.data.recomputed_hash}
            </div>
          )}
        </div>
      )}

      {state.kind === "fail" && (
        <div className="mt-2 rounded-lg border border-danger/40 bg-danger/5 p-3 text-sm">
          <div className="font-semibold text-danger">UNVERIFIED</div>
          <div className="mt-1 text-muted">{state.data.reason}</div>
          {state.data.recomputed_hash && (
            <div className="mt-2 font-mono text-xs">
              <div>stored: {state.data.stored.trace_hash}</div>
              <div>recomputed: {state.data.recomputed_hash}</div>
            </div>
          )}
        </div>
      )}

      {state.kind === "error" && (
        <div className="mt-2 rounded-lg border border-danger/40 bg-danger/5 p-3 text-sm text-danger">
          Error: {state.message}
        </div>
      )}
    </div>
  );
}
