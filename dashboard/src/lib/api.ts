/**
 * API client for the ReasoningReceipt FastAPI server.
 *
 * Reads from /api/* which is rewritten in next.config.mjs to the FastAPI
 * URL. In production set NEXT_PUBLIC_DASHBOARD_API_URL to the deployed API.
 */

export interface TraceRow {
  id: number;
  market_id: string;
  market_source: string;
  market_question: string | null;
  probability: number;
  confidence: number;
  trace_hash: string;
  trace_cid: string;
  consumer_address: string | null;
  arc_tx_hash: string | null;
  paid_micro_usdc: number;
  created_at: string;
}

export interface StatsResponse {
  total_receipts: number;
  total_paid_micro_usdc: number;
  distinct_markets: number;
  distinct_consumers: number;
  latest_receipt_at: string | null;
}

const base = "/api";

async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(`${base}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return (await r.json()) as T;
}

export const api = {
  receipts: (limit = 100) => getJSON<TraceRow[]>(`/receipts?limit=${limit}`),
  receipt: (id: number) => getJSON<TraceRow>(`/receipts/${id}`),
  stats: () => getJSON<StatsResponse>("/stats"),
};

/** SWR fetcher used by client components. */
export const fetcher = <T,>(path: string): Promise<T> => getJSON<T>(path);
