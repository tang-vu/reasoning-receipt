import Link from "next/link";
import { notFound } from "next/navigation";

import { api, type TraceRow } from "@/lib/api";
import { V3DetailPanels } from "@/components/v3-detail-panels";
import { VerifyButton } from "@/components/verify-button";

const useSnapshot = process.env.NEXT_PUBLIC_USE_SNAPSHOT === "1";

// Static export needs to know which ids to pre-render. In snapshot mode we
// enumerate everything in the snapshot; in server mode we let Next handle it
// per-request.
export async function generateStaticParams(): Promise<Array<{ id: string }>> {
  if (!useSnapshot) return [];
  try {
    const rows = await api.receipts(2000);
    return rows.map((r) => ({ id: String(r.id) }));
  } catch {
    return [];
  }
}

interface PageProps {
  params: Promise<{ id: string }>;
}

function fieldRow(label: string, value: string, mono = false) {
  return (
    <div className="flex items-start justify-between gap-4 border-t border-border py-2 first:border-t-0">
      <div className="text-xs uppercase tracking-wider text-muted">{label}</div>
      <div className={`text-sm ${mono ? "font-mono" : ""} max-w-[60%] break-all text-right text-ink`}>
        {value}
      </div>
    </div>
  );
}

export default async function TraceDetail({ params }: PageProps) {
  const { id } = await params;
  let row: TraceRow;
  try {
    row = await api.receipt(Number(id));
  } catch {
    return notFound();
  }
  return (
    <div className="space-y-6">
      <Link href="/traces" className="text-sm text-muted hover:text-ink">
        ← Back to traces
      </Link>

      <header>
        <h1 className="text-xl font-semibold tracking-tight">
          {row.market_question || row.market_id}
        </h1>
        <p className="mt-1 text-sm text-muted">Receipt #{row.id} — settled on Arc.</p>
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
        {fieldRow("Market id", row.market_id, true)}
        {fieldRow("Source", row.market_source)}
        {fieldRow("Trace hash", row.trace_hash, true)}
        {fieldRow("Trace CID", row.trace_cid, true)}
        {fieldRow("Arc tx", row.arc_tx_hash || "—", true)}
        {fieldRow("Consumer", row.consumer_address || "—", true)}
        {fieldRow(
          "Paid",
          `${(row.paid_micro_usdc / 1_000_000).toFixed(6)} USDC`,
          true,
        )}
        {fieldRow(
          "Created",
          new Date(row.created_at).toISOString().replace("T", " ").slice(0, 19) + " UTC",
          true,
        )}
      </section>

      <p className="text-xs text-muted">
        The full reasoning trace lives at the CID above (Irys / IPFS-compatible). The hash on Arc
        binds this row to the exact JSON that the analyst produced.
      </p>
    </div>
  );
}
