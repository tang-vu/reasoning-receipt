import { timingSafeEqual } from "node:crypto";

import { Uploader } from "@irys/upload";
import { Ethereum } from "@irys/upload-ethereum";

export const config = {
  api: { bodyParser: false },
  maxDuration: 60,
};

function sameSecret(supplied, expected) {
  const left = Buffer.from(supplied || "");
  const right = Buffer.from(expected || "");
  return left.length === right.length && left.length > 0 && timingSafeEqual(left, right);
}

async function readRaw(req) {
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  return Buffer.concat(chunks);
}

export default async function handler(req, res) {
  if (req.method !== "POST") {
    res.setHeader("Allow", "POST");
    return res.status(405).json({ error: "method not allowed" });
  }

  const secret = process.env.IRYS_UPLOAD_SECRET || "";
  const supplied = (req.headers.authorization || "").replace(/^Bearer\s+/i, "");
  if (!sameSecret(supplied, secret)) return res.status(401).json({ error: "unauthorized" });
  if (!process.env.IRYS_PRIVATE_KEY) return res.status(503).json({ error: "IRYS_PRIVATE_KEY is not configured" });

  const raw = await readRaw(req);
  if (!raw.length || raw.length > 1_000_000) return res.status(413).json({ error: "invalid payload size" });
  try {
    JSON.parse(raw.toString("utf8"));
  } catch {
    return res.status(400).json({ error: "body must be canonical JSON" });
  }

  const builder = Uploader(Ethereum).withWallet(process.env.IRYS_PRIVATE_KEY);
  const irys = process.env.IRYS_NETWORK === "mainnet"
    ? await builder
    : await builder.withRpc("https://rpc.sepolia.org").devnet();
  const receipt = await irys.upload(raw, {
    tags: [
      { name: "Content-Type", value: "application/json" },
      { name: "App-Name", value: "reasoning-receipt" },
    ],
  });
  return res.status(200).json({ id: receipt.id, cid: `ar://${receipt.id}`, size: raw.length });
}
