/**
 * API client for the ReasoningReceipt FastAPI server.
 *
 * Three modes, picked at build/runtime by env vars:
 *
 *  1. Live mode (production custom domain) — set
 *     `NEXT_PUBLIC_LIVE_API_BASE=https://api.rrtrace.xyz`. Every call hits
 *     the deployed FastAPI via Cloudflare Tunnel. If a call fails (tunnel
 *     down, CORS, network), falls through to snapshot data if available.
 *
 *  2. Snapshot-only mode (build-time prerender) — set
 *     `NEXT_PUBLIC_USE_SNAPSHOT=1` AND leave `NEXT_PUBLIC_LIVE_API_BASE`
 *     unset. Pages render from the committed snapshot.json. No network.
 *
 *  3. Local dev mode — neither env var set. Calls `/api/*` which
 *     `next.config.mjs` rewrites to `NEXT_PUBLIC_DASHBOARD_API_URL`
 *     (defaults to http://localhost:8000).
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

const liveApiBase =
  (typeof process !== "undefined" && process.env.NEXT_PUBLIC_LIVE_API_BASE) || "";
const devBase = "/api";

interface Snapshot {
  version: string;
  exported_at: string;
  stats: StatsResponse;
  receipts: TraceRow[];
  per_market: Array<{
    market_id: string;
    question: string;
    count: number;
    avg_probability: number;
    last_at: string;
  }>;
  volume_chart: Array<{ label: string; count: number }>;
  calibration?: CalibrationResponse;
}

const useSnapshot = process.env.NEXT_PUBLIC_USE_SNAPSHOT === "1";
let _snapshot: Promise<Snapshot> | null = null;

async function loadSnapshot(): Promise<Snapshot> {
  if (_snapshot) return _snapshot;
  // Server-side at build time: read the file directly so output: 'export' works.
  if (typeof window === "undefined") {
    _snapshot = (async () => {
      const fs = await import("node:fs/promises");
      const path = await import("node:path");
      const file = path.join(process.cwd(), "public", "snapshot.json");
      return JSON.parse(await fs.readFile(file, "utf-8")) as Snapshot;
    })();
    return _snapshot;
  }
  // GitHub Pages serves under /<repo>/, so prefix the asset URL.
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
  _snapshot = fetch(`${basePath}/snapshot.json`, { cache: "force-cache" }).then((r) => {
    if (!r.ok) throw new Error(`snapshot.json: ${r.status}`);
    return r.json();
  });
  return _snapshot;
}

async function fromSnapshot<T>(path: string): Promise<T> {
  const snap = await loadSnapshot();
  if (path.startsWith("/receipts?")) {
    const limit = Number(new URLSearchParams(path.split("?")[1]).get("limit") ?? 100);
    return snap.receipts.slice(0, limit) as unknown as T;
  }
  if (path.startsWith("/receipts/")) {
    const id = Number(path.split("/").pop());
    const row = snap.receipts.find((r) => r.id === id);
    if (!row) throw new Error("receipt not found");
    return row as unknown as T;
  }
  if (path === "/stats") return snap.stats as unknown as T;
  if (path === "/calibration") {
    const cal = snap.calibration ?? {
      total_resolved: 0,
      distinct_resolved_markets: 0,
      brier_score: 0,
      brier_high_conf: null,
      brier_low_conf: null,
      buckets: [],
    };
    return cal as unknown as T;
  }
  if (path.startsWith("/verify/")) {
    // Static snapshot can't verify against Irys — return a synthetic response
    // so the UI doesn't crash. Live deployment uses the real /verify endpoint.
    const id = Number(path.split("/")[2]);
    const row = snap.receipts.find((r) => r.id === id);
    return {
      verified: false,
      reason: "static snapshot mode — run locally to verify against Irys",
      stored: row ?? null,
      fetched_trace: null,
      recomputed_hash: null,
      irys_gateway_url: row?.trace_cid
        ? `https://gateway.irys.xyz/${row.trace_cid.replace("ar://", "")}`
        : null,
    } as unknown as T;
  }
  throw new Error(`snapshot mode: unsupported path ${path}`);
}

async function getJSON<T>(path: string): Promise<T> {
  // Mode 1: live API base set — try the deployed backend first, snapshot as fallback.
  if (liveApiBase) {
    try {
      const r = await fetch(`${liveApiBase}${path}`, { cache: "no-store" });
      if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
      return (await r.json()) as T;
    } catch (err) {
      if (useSnapshot) {
        // Backend unreachable but a snapshot exists — degrade gracefully.
        return fromSnapshot<T>(path);
      }
      throw err;
    }
  }
  // Mode 2: snapshot-only.
  if (useSnapshot) return fromSnapshot<T>(path);
  // Mode 3: local dev — Next rewrites /api/* to NEXT_PUBLIC_DASHBOARD_API_URL.
  const r = await fetch(`${devBase}${path}`, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path} failed: ${r.status}`);
  return (await r.json()) as T;
}

/** Base URL for the SSE event stream. Live mode uses events.rrtrace.xyz,
 * snapshot/dev modes use the same `/api` base since they hit the local API.
 * SSE doesn't have a snapshot fallback — when live is down, the UI just
 * shows static last-known data without live updates. */
export function eventsStreamUrl(): string {
  if (liveApiBase) {
    // Try a dedicated events subdomain first (longer keepalive in CF Tunnel
    // config), fall back to the main API base.
    if (typeof process !== "undefined" && process.env.NEXT_PUBLIC_EVENTS_BASE) {
      return `${process.env.NEXT_PUBLIC_EVENTS_BASE}/events/stream`;
    }
    return `${liveApiBase}/events/stream`;
  }
  return `${devBase}/events/stream`;
}

export interface CalibrationBucket {
  label: string;
  bucket_min: number;
  bucket_max: number;
  n: number;
  mean_predicted: number;
  mean_actual: number;
}

export interface CalibrationResponse {
  total_resolved: number;
  distinct_resolved_markets: number;
  brier_score: number;
  brier_high_conf: number | null;
  brier_low_conf: number | null;
  buckets: CalibrationBucket[];
}

export interface VerifyResponse {
  verified: boolean;
  reason: string;
  stored: {
    id: number;
    market_id: string;
    market_question: string | null;
    trace_hash: string;
    trace_cid: string;
    arc_tx_hash: string | null;
    probability: number;
    confidence: number;
    consumer_address: string | null;
    publisher_address: string;
    created_at: string | null;
  };
  fetched_trace: Record<string, unknown> | null;
  recomputed_hash: string | null;
  irys_gateway_url: string | null;
}

export const api = {
  receipts: (limit = 100) => getJSON<TraceRow[]>(`/receipts?limit=${limit}`),
  receipt: (id: number) => getJSON<TraceRow>(`/receipts/${id}`),
  stats: () => getJSON<StatsResponse>("/stats"),
  verify: (id: number) => getJSON<VerifyResponse>(`/verify/${id}`),
  calibration: () => getJSON<CalibrationResponse>("/calibration"),
};

/** SWR fetcher used by client components. */
export const fetcher = <T,>(path: string): Promise<T> => getJSON<T>(path);
