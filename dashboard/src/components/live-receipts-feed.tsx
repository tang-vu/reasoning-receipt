"use client";

import { useEffect, useRef, useState } from "react";

import type { TraceRow } from "@/lib/api";
import { eventsStreamUrl } from "@/lib/api";

type Status = "idle" | "connecting" | "live" | "fallback";

const ARC_TX_URL = (h: string) => `https://testnet.arcscan.app/tx/${h.replace(/^0x/, "")}`;

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  return `${h}h ago`;
}

/**
 * Live SSE-backed receipts feed. Subscribes to the backend's /events/stream,
 * prepends new receipts as they arrive, and keeps the most recent 100 in
 * memory. Falls back to the initial seed (server-rendered snapshot) if the
 * SSE connection can't be established.
 */
export function LiveReceiptsFeed({ initial }: { initial: TraceRow[] }) {
  const [rows, setRows] = useState<TraceRow[]>(initial);
  const [status, setStatus] = useState<Status>("idle");
  const seenIds = useRef<Set<number>>(new Set(initial.map((r) => r.id)));

  useEffect(() => {
    setStatus("connecting");
    const url = eventsStreamUrl();
    const es = new EventSource(url);

    es.addEventListener("open", () => setStatus("live"));

    es.addEventListener("receipt", (e: MessageEvent) => {
      try {
        const payload = JSON.parse((e as MessageEvent<string>).data) as TraceRow;
        if (seenIds.current.has(payload.id)) return;
        seenIds.current.add(payload.id);
        setRows((prev) => [payload, ...prev].slice(0, 100));
      } catch {
        // Bad payload — drop silently, don't break the stream.
      }
    });

    es.addEventListener("error", () => {
      // EventSource auto-reconnects. We flip to "fallback" so the user knows
      // the snapshot data isn't auto-updating, but keep the existing rows.
      setStatus("fallback");
    });

    return () => {
      es.close();
    };
  }, []);

  return (
    <section className="space-y-3">
      <div className="flex items-baseline justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-xl font-semibold">Live receipts</h2>
          <StatusPill status={status} />
        </div>
        <span className="text-sm text-muted">latest {rows.length}</span>
      </div>

      <div className="overflow-hidden rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-panel text-left text-xs uppercase tracking-wider text-muted">
            <tr>
              <th className="px-3 py-2">#</th>
              <th className="px-3 py-2">Market</th>
              <th className="px-3 py-2 text-right">Prob</th>
              <th className="px-3 py-2 text-right">Conf</th>
              <th className="px-3 py-2">When</th>
              <th className="px-3 py-2">On chain</th>
              <th className="px-3 py-2">Trace</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {rows.slice(0, 30).map((r) => (
              <tr key={r.id} className="bg-bg transition-colors hover:bg-panel/30">
                <td className="px-3 py-2 font-mono text-xs text-muted">{r.id}</td>
                <td className="max-w-[280px] truncate px-3 py-2 text-ink">
                  {r.market_question ?? r.market_id}
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums">
                  {(r.probability * 100).toFixed(1)}%
                </td>
                <td className="px-3 py-2 text-right font-mono tabular-nums text-muted">
                  {(r.confidence * 100).toFixed(0)}%
                </td>
                <td className="px-3 py-2 text-muted">{timeAgo(r.created_at)}</td>
                <td className="px-3 py-2">
                  {r.arc_tx_hash ? (
                    <a
                      href={ARC_TX_URL(r.arc_tx_hash)}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-xs text-accent hover:underline"
                    >
                      {r.arc_tx_hash.slice(0, 10)}…
                    </a>
                  ) : (
                    <span className="text-xs text-muted">—</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <a
                    href={`/traces/${r.id}`}
                    className="text-xs text-accent hover:underline"
                  >
                    open →
                  </a>
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-sm text-muted">
                  No receipts yet. Run the agent loop or hit <code>/price/&lt;market_id&gt;</code>.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StatusPill({ status }: { status: Status }) {
  if (status === "live") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
        <span className="size-1.5 animate-pulse rounded-full bg-accent" />
        LIVE
      </span>
    );
  }
  if (status === "connecting") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-muted/10 px-2 py-0.5 text-xs font-medium text-muted">
        <span className="size-1.5 rounded-full bg-muted" />
        connecting…
      </span>
    );
  }
  if (status === "fallback") {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full bg-danger/10 px-2 py-0.5 text-xs font-medium text-danger">
        <span className="size-1.5 rounded-full bg-danger" />
        snapshot
      </span>
    );
  }
  return null;
}
