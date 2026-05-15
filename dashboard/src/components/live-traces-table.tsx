"use client";

import { useEffect, useState } from "react";

import { api, type TraceRow } from "@/lib/api";
import { TracesTable } from "@/components/traces-table";

/**
 * Live-refreshing wrapper around TracesTable. Takes the server-rendered
 * receipt list as a seed (so the static GH Pages export still has data at
 * first paint), then re-fetches the latest from the live API on mount.
 * Without this, the /traces page sticks at the snapshot baked in at the
 * last dashboard build — same pitfall the homepage feed used to have.
 */
export function LiveTracesTable({ initial }: { initial: TraceRow[] }) {
  const [rows, setRows] = useState<TraceRow[]>(initial);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRefreshing(true);
    api
      .receipts(200)
      .then((fresh) => {
        if (cancelled || fresh.length === 0) return;
        setRows(fresh);
      })
      .catch(() => {
        // Stay on the SSR seed if the live API is unreachable.
      })
      .finally(() => {
        if (!cancelled) setRefreshing(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between text-xs text-muted">
        <span>
          Showing latest {rows.length} receipts
          {refreshing ? " · refreshing…" : ""}
        </span>
      </div>
      <TracesTable rows={rows} />
    </div>
  );
}
