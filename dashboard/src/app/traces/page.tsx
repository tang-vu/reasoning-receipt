import { api } from "@/lib/api";
import { TracesTable } from "@/components/traces-table";

export const dynamic = "force-dynamic";
export const revalidate = 0;

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
      <TracesTable rows={rows} />
    </div>
  );
}
