"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { api, type TraceRow } from "@/lib/api";
import { V3DetailPanels } from "@/components/v3-detail-panels";
import { VerifyButton } from "@/components/verify-button";

/**
 * Smart 404 that doubles as a runtime fallback for /traces/<id> URLs whose
 * static page wasn't pre-rendered at build time.
 *
 * Why this exists: `/traces/[id]/page.tsx` uses generateStaticParams over the
 * committed snapshot.json — at build time that's roughly the latest 2k IDs.
 * The daemon emits new receipts continuously, so any ID emitted after the
 * last `dashboard/**` push lands on GH Pages as a 404 (GH serves /404.html
 * for unknown paths, and Next exports this component to /404.html in
 * `output: 'export'` mode).
 *
 * The fix: detect the `/traces/<digits>` pathname, hit the live API for
 * the receipt, and render the same detail view inline. No URL change, no
 * snapshot regen + redeploy required.
 */
function isTracePath(pathname: string | null): number | null {
  if (!pathname) return null;
  const m = pathname.match(/\/traces\/(\d+)\/?$/);
  if (!m) return null;
  const id = Number(m[1]);
  return Number.isFinite(id) && id > 0 ? id : null;
}

function FieldRow({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-start justify-between gap-4 border-t border-border py-2 first:border-t-0">
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className={`text-sm ${mono ? "font-mono" : ""} max-w-[60%] break-all text-right text-ink`}>
        {value}
      </div>
    </div>
  );
}

function TraceFallbackView({ id }: { id: number }) {
  const [row, setRow] = useState<TraceRow | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .receipt(id)
      .then((r) => {
        if (!cancelled) setRow(r);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : "fetch failed");
      });
    return () => {
      cancelled = true;
    };
  }, [id]);

  if (error) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-semibold">Receipt #{id} — not available</h1>
        <p className="text-muted">
          This receipt isn&apos;t in the static snapshot and the live API call failed
          ({error}). The receipt may exist on Arc — check the explorer directly, or
          retry in a few seconds.
        </p>
        <Link href="/traces/" className="text-accent hover:underline">
          ← Back to recent traces
        </Link>
      </div>
    );
  }

  if (!row) {
    return (
      <div className="space-y-3">
        <Link href="/traces/" className="text-sm text-muted hover:text-ink">
          ← Back to traces
        </Link>
        <p className="text-muted">Loading receipt #{id} from live API…</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link href="/traces/" className="text-sm text-muted hover:text-ink">
        ← Back to traces
      </Link>

      <header>
        <h1 className="text-xl font-semibold tracking-tight">
          {row.market_question || row.market_id}
        </h1>
        <p className="mt-1 text-sm text-muted">
          Receipt #{row.id} — settled on Arc. (Loaded from live API — this ID was emitted
          after the last dashboard build.)
        </p>
      </header>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="rounded-xl border border-border bg-panel p-5">
          <div className="text-xs uppercase tracking-wider text-muted">Probability</div>
          <div className="mt-1 font-mono text-3xl text-accent">
            {(row.probability * 100).toFixed(1)}%
          </div>
        </div>
        <div className="rounded-xl border border-border bg-panel p-5">
          <div className="text-xs uppercase tracking-wider text-muted">Confidence</div>
          <div className="mt-1 font-mono text-3xl text-accent2">
            {(row.confidence * 100).toFixed(1)}%
          </div>
        </div>
      </section>

      {row.schema_version === "rr-trace/3" && <V3DetailPanels receiptId={row.id} />}

      <VerifyButton receiptId={row.id} />

      <section className="rounded-xl border border-border bg-panel p-5">
        <FieldRow label="Market id" value={row.market_id} mono />
        <FieldRow label="Source" value={row.market_source} />
        <FieldRow label="Trace hash" value={row.trace_hash} mono />
        <FieldRow label="Trace CID" value={row.trace_cid} mono />
        <FieldRow label="Arc tx" value={row.arc_tx_hash || "—"} mono />
        <FieldRow label="Consumer" value={row.consumer_address || "—"} mono />
        <FieldRow
          label="Paid"
          value={`${(row.paid_micro_usdc / 1_000_000).toFixed(6)} USDC`}
          mono
        />
        <FieldRow
          label="Created"
          value={new Date(row.created_at).toISOString().replace("T", " ").slice(0, 19) + " UTC"}
          mono
        />
      </section>
    </div>
  );
}

function GenericNotFound() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Page not found</h1>
      <p className="text-muted">
        That URL doesn&apos;t exist. The agent&apos;s home is{" "}
        <Link href="/" className="text-accent hover:underline">
          rrtrace.xyz
        </Link>
        .
      </p>
    </div>
  );
}

export default function NotFound() {
  const pathname = usePathname();
  const traceId = isTracePath(pathname);
  if (traceId !== null) return <TraceFallbackView id={traceId} />;
  return <GenericNotFound />;
}
