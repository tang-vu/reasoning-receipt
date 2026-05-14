"use client";

import { useEffect, useRef, useState } from "react";

import type { TraceRow } from "@/lib/api";
import { api, eventsStreamUrl } from "@/lib/api";

type Status = "idle" | "connecting" | "live" | "fallback";

// Blockscout (Arc explorer) requires a 0x-prefixed hash; reject otherwise.
const ARC_TX_URL = (h: string) => `https://testnet.arcscan.app/tx/${h.startsWith("0x") ? h : `0x${h}`}`;

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
 * Live SSE-backed receipts feed. On mount it pulls the latest 100 receipts
 * from the live API (overriding the build-time seed so the static export
 * doesn't show hour-old rows), then subscribes to /events/stream and
 * prepends new receipts as they arrive. Falls back to the SSR seed if the
 * client fetch fails.
 */
export function LiveReceiptsFeed({ initial }: { initial: TraceRow[] }) {
  const [rows, setRows] = useState<TraceRow[]>(initial);
  const [status, setStatus] = useState<Status>("idle");
  const seenIds = useRef<Set<number>>(new Set(initial.map((r) => r.id)));

  // On mount, refresh the table from the live API. The initial seed is baked
  // at build time on GH Pages, so without this the table stays frozen at the
  // build snapshot until SSE prepends new receipts — leaving an awkward gap
  // between the latest fresh receipt and the next row.
  useEffect(() => {
    let cancelled = false;
    api
      .receipts(100)
      .then((fresh) => {
        if (cancelled || fresh.length === 0) return;
        setRows(fresh);
        seenIds.current = new Set(fresh.map((r) => r.id));
      })
      .catch(() => {
        // Stay on the SSR seed — SSE will still add live receipts on top.
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
              <th className="px-3 py-2">Schema</th>
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
                <td className="px-3 py-2">
                  <SchemaBadge schema={r.schema_version} disagreement={r.disagreement_pp} />
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
                <td colSpan={8} className="px-3 py-8 text-center text-sm text-muted">
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

function SchemaBadge({
  schema,
  disagreement,
}: {
  schema?: string | null;
  disagreement?: number | null;
}) {
  if (schema === "rr-trace/3") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full bg-accent2/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-wider text-accent2"
        title={
          disagreement != null
            ? `Ensemble Bull/Bear/Edge disagreement: ${disagreement.toFixed(1)}pp`
            : "5-agent ensemble + Merkle DAG"
        }
      >
        v3
        {disagreement != null && disagreement > 0 && (
          <span className="text-muted">·{disagreement.toFixed(0)}pp</span>
        )}
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-muted/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-muted">
      {schema?.replace("rr-trace/", "v") ?? "v2"}
    </span>
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
