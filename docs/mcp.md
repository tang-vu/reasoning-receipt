# MCP integration

ReasoningReceipt is wrapped as an [MCP](https://modelcontextprotocol.io/) server at `services/mcp/server.js`. Any MCP-aware client — **Claude Desktop**, **Cursor**, **Cline**, **Continue** — can call the oracle as a first-class tool, side-by-side with file-system and shell tools.

## Why expose this as MCP

The wedge of the project is *trace as the product* — a probability plus a hashed, verifiable chain-of-thought. MCP turns that wedge into something a human in their everyday AI tool can use directly:

- **Inside Claude Desktop**, ask "What does ReasoningReceipt think about market 2175685?" → Claude calls `get_price`, you see the probability + the Arc tx hash + the Irys CID, and you can ask follow-up questions with the trace as context.
- **Inside Cursor / Cline**, an agent writing trading code can call `verify_receipt` to byte-check a third-party oracle's claim before quoting it.
- **For other AI agents** building on top of our oracle, MCP gives them a structured tool surface that's tracked across LLM frameworks (Anthropic, OpenAI, Google ADK).

## Tools

| Tool | Args | Returns |
|---|---|---|
| `get_price` | `market_id: string` | Latest cached probability + trace pointer + Arc tx hash for the market id (reads from the receipt log; does NOT settle a new x402 payment) |
| `verify_receipt` | `receipt_id: number` | Fetches the trace JSON from Irys, recomputes SHA-256 of the canonical bytes, compares to the on-chain hash. Returns `verified: true|false` plus the full trace payload |
| `get_stats` | none | Total receipts, USDC settled, distinct markets, distinct consumers, timestamp of the latest receipt |
| `get_calibration` | none | Brier score + 10-bucket reliability curve over resolved markets; high-conf vs low-conf Brier split |

## Setup

### 1. Make sure the oracle's FastAPI server is reachable

The MCP server is a thin client — it calls `RR_API_BASE` (default `http://localhost:8000`). Start the oracle locally:

```bash
uv run uvicorn server.main:app --port 8000
```

Or point at a remote oracle by setting `RR_API_BASE` to a Cloudflare Tunnel / ngrok URL.

### 2. Install MCP server deps (one-time)

```bash
cd services/mcp
npm install
```

### 3. Wire into Claude Desktop

Edit `claude_desktop_config.json` (location: `%APPDATA%\Claude\claude_desktop_config.json` on Windows, `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "reasoning-receipt": {
      "command": "node",
      "args": ["C:/Users/tangm/Documents/GitHub/reasoning-receipt/services/mcp/server.js"],
      "env": {
        "RR_API_BASE": "http://localhost:8000"
      }
    }
  }
}
```

Replace the absolute path with wherever you cloned the repo. Restart Claude Desktop. The four tools will appear in the tool palette and Claude will call them when relevant.

### 4. Wire into Cursor / Cline / Continue

Each editor has its own MCP config file but the `command` / `args` / `env` shape is identical to the Claude Desktop snippet above. Refer to your client's docs for the exact path.

## Example usage in Claude Desktop

```
You: What's ReasoningReceipt's current probability on Polymarket market 2175685?

Claude: [calls get_price]
  market: "Will the price of XRP be above $1.90 on May 13?"
  probability: 0.015
  confidence: 0.95
  receipt_id: 1432
  arc tx: 0xa9231c6b1c3c…

You: Prove that trace wasn't tampered.

Claude: [calls verify_receipt with receipt_id=1432]
  verified: true
  reason:    byte-for-byte match
  stored:    0xd00bd13a0fc006c156de818714273802576dee6e9b64377b339c10175e9e0e4b
  recomputed: 0xd00bd13a0fc006c156de818714273802576dee6e9b64377b339c10175e9e0e4b
  ↑ Yes — the trace fetched from Irys re-hashes to exactly the value bound on Arc.
```

## Why this matters for the submission

* **Agentic Sophistication**: the oracle is now callable from any LLM that speaks MCP. Other agents become consumers, which is the natural endpoint of the "AI agents on Arc" thesis.
* **Innovation**: the byte-match verify is reachable from a chat client. Anyone running Claude Desktop can audit our claims in seconds.
* **Discoverability**: judges who use Claude Desktop themselves can drop the MCP config in and try the oracle without leaving their editor.
