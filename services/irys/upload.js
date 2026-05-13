// upload.js — Irys uploader sidecar.
//
// Reads a JSON blob from stdin, uploads to Irys devnet using the ETH signer,
// prints the resulting transaction id on a single stdout line as JSON:
//   {"id":"<txid>","cid":"ar://<txid>","size":<bytes>}
//
// Errors go to stderr; exit code 1 on failure.

import { Uploader } from "@irys/upload";
import { Ethereum } from "@irys/upload-ethereum";
import { readFileSync } from "node:fs";

async function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { data += chunk; });
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function envOrDie(name) {
  const v = process.env[name];
  if (!v) {
    console.error(`missing env: ${name}`);
    process.exit(2);
  }
  return v;
}

async function main() {
  const privateKey = envOrDie("IRYS_PRIVATE_KEY");
  const network = process.env.IRYS_NETWORK || "devnet";

  let payload;
  const argFile = process.argv[2];
  const raw = argFile ? readFileSync(argFile, "utf8") : await readStdin();
  try {
    payload = JSON.parse(raw);
  } catch (e) {
    console.error("invalid JSON on stdin:", e.message);
    process.exit(3);
  }

  const builder = Uploader(Ethereum).withWallet(privateKey);
  const uploader = network === "mainnet" ? builder : builder.withRpc("https://rpc.sepolia.org").devnet();
  const irys = await uploader;

  const body = JSON.stringify(payload);
  const tags = [{ name: "Content-Type", value: "application/json" }, { name: "App-Name", value: "reasoning-receipt" }];
  const receipt = await irys.upload(body, { tags });

  process.stdout.write(JSON.stringify({ id: receipt.id, cid: `ar://${receipt.id}`, size: body.length }) + "\n");
}

main().catch((err) => {
  console.error("irys upload failed:", err?.message || String(err));
  process.exit(1);
});
