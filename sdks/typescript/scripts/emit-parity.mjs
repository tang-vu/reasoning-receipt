// Emit the cross-language parity receipt (spec: conformance/parity/).
// Byte-identical canonical envelope to the Python and Rust emitters —
// fixed IDs, timestamps and signing key make signatures reproducible.

import { writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import { ReceiptBuilder, sign } from "../dist/index.js";

const PRIVATE_KEY = "0x" + "0123456789abcdef".repeat(4);
const SIGNED_AT = "2026-05-20T00:00:00Z";

const receipt = new ReceiptBuilder("parity:cross-language", {
  harness: "rr-parity/1",
  unicode: "héllo wörld — 数据 ✓",
})
  .add("intent", "intent", { action: "deploy", target: "testnet" }, { source: "emit" })
  .add("policy", "policy", { limit: 100, rules: ["r1", "r2"] })
  .add("decision", "decision", { approved: true, score: 0.125 })
  .add("outcome", "outcome", { status: "success", emoji: "🧾" })
  .link("decision", "policy", "evaluated_against")
  .link("decision", "intent", "produced")
  .link("outcome", "decision", "produced")
  .finalize({ receipt_id: "rr-parity-0001", produced_at: SIGNED_AT });

const envelope = receipt.committedEnvelope();
receipt.signatures = [
  sign(envelope, PRIVATE_KEY, { scope: "receipt", key_id: "parity-key", signed_at: SIGNED_AT }),
  sign(envelope, PRIVATE_KEY, { scope: "node:decision", key_id: "parity-key", signed_at: SIGNED_AT }),
];

const out = process.argv[2] ?? "../../conformance/parity/ts.receipt.json";
mkdirSync(dirname(out), { recursive: true });
writeFileSync(out, JSON.stringify(receipt.toDict(), null, 2) + "\n");
console.log(out);
