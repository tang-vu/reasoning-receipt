#!/usr/bin/env node
/**
 * ReasoningReceipt MCP server.
 *
 * Exposes the oracle as a stdio MCP server so any MCP-aware client
 * (Claude Desktop, Cursor, Cline, Continue, …) can call the oracle as
 * a tool. Four tools:
 *
 *   get_price        — fetch the latest cached price + trace pointer for a market
 *   verify_receipt   — pull the trace JSON from Irys, re-hash, byte-match
 *   get_stats        — total receipts, distinct markets, USDC settled
 *   get_calibration  — Brier score + reliability buckets over resolved receipts
 *
 * Configure in Claude Desktop's claude_desktop_config.json:
 *
 *   {
 *     "mcpServers": {
 *       "reasoning-receipt": {
 *         "command": "node",
 *         "args": ["<path-to-repo>/services/mcp/server.js"],
 *         "env": {
 *           "RR_API_BASE": "http://localhost:8000"
 *         }
 *       }
 *     }
 *   }
 *
 * Defaults to the local FastAPI server. Set RR_API_BASE to a deployed URL
 * (e.g. an ngrok tunnel) to use a remote oracle.
 */

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const API_BASE = (process.env.RR_API_BASE || "http://localhost:8000").replace(/\/$/, "");

async function callApi(path) {
  const resp = await fetch(`${API_BASE}${path}`);
  if (!resp.ok) {
    throw new Error(`oracle ${path} responded ${resp.status}: ${await resp.text()}`);
  }
  return resp.json();
}

const server = new McpServer(
  { name: "reasoning-receipt", version: "0.1.0" },
  {
    capabilities: { tools: {} },
    instructions:
      "ReasoningReceipt is an x402-paywalled prediction-market oracle whose product is the " +
      "hashed reasoning trace, not just the number. Use get_price for the latest cached " +
      "answer on a Polymarket market, verify_receipt to prove a trace byte-matches the " +
      "on-chain hash, get_stats for headline traction, and get_calibration to see the " +
      "agent's Brier score against resolved markets.",
  },
);

server.tool(
  "get_price",
  "Return the latest cached probability for a Polymarket market id, including the on-chain " +
    "receipt id, trace hash, Irys CID, and the Arc Testnet tx hash. Does NOT settle a new " +
    "x402 payment — reads from the existing receipt log (the agent re-prices every market " +
    "every 5 minutes anyway).",
  { market_id: z.string().describe("Polymarket market id, e.g. \"2175685\" or \"mock-polymarket-fed-rate-cut-jun-2026\"") },
  async ({ market_id }) => {
    const rows = await callApi(`/receipts?limit=500`);
    const match = rows.find((r) => r.market_id === market_id);
    if (!match) {
      return {
        content: [
          {
            type: "text",
            text: `No cached receipt for market_id=${market_id}. The agent may not have priced it yet. Run the agent loop or call GET /price/${market_id} on the FastAPI server to mint a fresh receipt (settles 0.01 USDC via x402).`,
          },
        ],
      };
    }
    return {
      content: [
        {
          type: "text",
          text: JSON.stringify(
            {
              market_id: match.market_id,
              market_question: match.market_question,
              probability: match.probability,
              confidence: match.confidence,
              trace_hash: match.trace_hash,
              trace_cid: match.trace_cid,
              arc_tx_hash: match.arc_tx_hash,
              receipt_id: match.id,
              priced_at: match.created_at,
            },
            null,
            2,
          ),
        },
      ],
    };
  },
);

server.tool(
  "verify_receipt",
  "Prove that a receipt's stored trace_hash byte-matches the SHA-256 of the canonical JSON " +
    "fetched from Irys. Returns verified=true iff the on-chain hash and the recomputed hash " +
    "agree, plus the full trace payload (sources, counter-arguments, sensitivity) for " +
    "inspection.",
  { receipt_id: z.number().int().positive().describe("Receipt id from /receipts or get_price") },
  async ({ receipt_id }) => {
    const result = await callApi(`/verify/${receipt_id}`);
    return {
      content: [
        {
          type: "text",
          text:
            `verified: ${result.verified}\n` +
            `reason:   ${result.reason}\n` +
            `stored hash:    ${result.stored?.trace_hash}\n` +
            `recomputed:     ${result.recomputed_hash ?? "n/a"}\n` +
            `irys gateway:   ${result.irys_gateway_url ?? "n/a"}\n` +
            `\nFetched trace:\n${JSON.stringify(result.fetched_trace, null, 2)}`,
        },
      ],
    };
  },
);

server.tool(
  "get_stats",
  "Return headline traction: total on-chain receipts, USDC settled via x402, distinct " +
    "markets priced, distinct consumer addresses, timestamp of the most recent receipt.",
  {},
  async () => {
    const stats = await callApi(`/stats`);
    return { content: [{ type: "text", text: JSON.stringify(stats, null, 2) }] };
  },
);

server.tool(
  "get_calibration",
  "Return the agent's Brier score on resolved markets plus a 10-bucket reliability curve " +
    "(mean predicted vs mean actual). Lower Brier is better; perfectly calibrated dots " +
    "lie on the y=x identity line. Empty until the first wave of markets resolves.",
  {},
  async () => {
    const cal = await callApi(`/calibration`);
    return { content: [{ type: "text", text: JSON.stringify(cal, null, 2) }] };
  },
);

const transport = new StdioServerTransport();
await server.connect(transport);
// stderr-only so it doesn't pollute the stdio MCP transport.
process.stderr.write(`reasoning-receipt MCP server: api=${API_BASE}\n`);
