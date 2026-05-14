import Link from "next/link";

import type { TraceRow } from "@/lib/api";

function short(s?: string | null, head = 8, tail = 4): string {
  if (!s) return "—";
  if (s.length <= head + tail + 1) return s;
  return `${s.slice(0, head)}…${s.slice(-tail)}`;
}

function pct(x: number): string {
  return `${(x * 100).toFixed(1)}%`;
}

function SourcePill({ source }: { source: string | null | undefined }) {
  const tone =
    source === "kalshi"
      ? "bg-accent2/15 text-accent2 border-accent2/30"
      : "bg-accent/15 text-accent border-accent/30";
  const label = source || "polymarket";
  return (
    <span
      className={`mr-2 inline-block rounded border px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${tone}`}
    >
      {label}
    </span>
  );
}

export function TracesTable({ rows }: { rows: TraceRow[] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-panel p-6 text-sm text-muted">
        No receipts yet. Run the agent loop or seed the DB with{" "}
        <code className="font-mono">uv run python -m scripts.seed-demo --count 50</code>.
      </div>
    );
  }
  return (
    <div className="overflow-x-auto rounded-xl border border-border bg-panel">
      <table className="w-full text-left text-sm">
        <thead className="bg-panel2 text-xs uppercase tracking-wider text-muted">
          <tr>
            <th className="px-4 py-3">#</th>
            <th className="px-4 py-3">Market</th>
            <th className="px-4 py-3">Prob</th>
            <th className="px-4 py-3">Conf</th>
            <th className="px-4 py-3">Trace</th>
            <th className="px-4 py-3">Arc tx</th>
            <th className="px-4 py-3">When</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-t border-border hover:bg-panel2/60">
              <td className="px-4 py-3 font-mono text-xs text-muted">{r.id}</td>
              <td className="px-4 py-3">
                <SourcePill source={r.market_source} />
                <Link
                  href={`/traces/${r.id}`}
                  className="text-ink hover:text-accent"
                  title={r.market_id}
                >
                  {r.market_question || r.market_id}
                </Link>
              </td>
              <td className="px-4 py-3 font-mono">{pct(r.probability)}</td>
              <td className="px-4 py-3 font-mono text-muted">{pct(r.confidence)}</td>
              <td className="px-4 py-3 font-mono text-xs">{short(r.trace_hash, 10, 6)}</td>
              <td className="px-4 py-3 font-mono text-xs">{short(r.arc_tx_hash, 10, 6)}</td>
              <td className="px-4 py-3 font-mono text-xs text-muted">
                {new Date(r.created_at).toISOString().replace("T", " ").slice(0, 19)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
