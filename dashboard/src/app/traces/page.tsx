import type { Metadata } from "next";

import { api } from "@/lib/api";
import { LiveTracesTable } from "@/components/live-traces-table";

export const metadata: Metadata = {
  title: "Receipts — every paid query, on-chain",
  description:
    "Browse every reasoning receipt emitted on Arc. Each row links to a byte-verifiable trace pinned on Irys and a ReceiptV2 event with Merkle root.",
  alternates: { canonical: "/traces/" },
};

export default async function TracesPage() {
  const rows = await api.receipts(200).catch(() => []);
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Trace explorer</h1>
        <p className="mt-1 text-sm text-muted">
          Latest 200 receipts. Click a row to see the cited sources, counter-arguments, and Arc
          settlement details.
        </p>
      </header>
      <LiveTracesTable initial={rows} />
    </div>
  );
}
