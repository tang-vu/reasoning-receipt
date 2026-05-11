import { api, type TraceRow } from "@/lib/api";

interface EventStat {
  market_id: string;
  question: string;
  count: number;
  avg_probability: number;
  last_at: string;
}

function summarise(rows: TraceRow[]): EventStat[] {
  const byMarket = new Map<string, EventStat>();
  for (const r of rows) {
    const existing = byMarket.get(r.market_id);
    if (existing) {
      existing.count += 1;
      existing.avg_probability =
        (existing.avg_probability * (existing.count - 1) + r.probability) / existing.count;
      if (new Date(r.created_at) > new Date(existing.last_at)) {
        existing.last_at = r.created_at;
      }
    } else {
      byMarket.set(r.market_id, {
        market_id: r.market_id,
        question: r.market_question || r.market_id,
        count: 1,
        avg_probability: r.probability,
        last_at: r.created_at,
      });
    }
  }
  return [...byMarket.values()].sort((a, b) => b.count - a.count);
}

export default async function EventsPage() {
  const rows = await api.receipts(500).catch(() => []);
  const events = summarise(rows);
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Events by volume</h1>
        <p className="mt-1 text-sm text-muted">
          Markets the oracle has priced most often, across the latest 500 receipts.
        </p>
      </header>

      {events.length === 0 ? (
        <div className="rounded-xl border border-border bg-panel p-6 text-sm text-muted">
          No data yet.
        </div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-border bg-panel">
          <table className="w-full text-left text-sm">
            <thead className="bg-panel2 text-xs uppercase tracking-wider text-muted">
              <tr>
                <th className="px-4 py-3">Market</th>
                <th className="px-4 py-3">Queries</th>
                <th className="px-4 py-3">Avg prob</th>
                <th className="px-4 py-3">Last priced</th>
              </tr>
            </thead>
            <tbody>
              {events.map((e) => (
                <tr key={e.market_id} className="border-t border-border hover:bg-panel2/60">
                  <td className="px-4 py-3" title={e.market_id}>
                    {e.question}
                  </td>
                  <td className="px-4 py-3 font-mono">{e.count}</td>
                  <td className="px-4 py-3 font-mono text-muted">
                    {(e.avg_probability * 100).toFixed(1)}%
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-muted">
                    {new Date(e.last_at).toISOString().replace("T", " ").slice(0, 19)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
