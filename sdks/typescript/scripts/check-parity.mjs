// Cross-language parity check (TypeScript side). Mirrors
// scripts/parity/check.py — verifies every emitted receipt and asserts
// the canonical document bytes are identical across languages.

import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { canonicalBytes, verifyAny } from "../dist/index.js";

const PARITY_DIR = fileURLToPath(new URL("../../../conformance/parity", import.meta.url));

const files = readdirSync(PARITY_DIR).filter((f) => f.endsWith(".receipt.json")).sort();
if (!files.length) {
  console.error("no parity receipts emitted yet");
  process.exit(2);
}

const canonical = new Map();
let ok = true;
for (const name of files) {
  const doc = JSON.parse(readFileSync(join(PARITY_DIR, name), "utf-8"));
  const report = verifyAny(doc);
  const sigStates = (report.signatures ?? []).map((s) => s.valid);
  let line = `${name}: valid=${report.valid} sigs=[${sigStates}] root=${report.merkle_root}`;
  if (!report.valid || !sigStates.every(Boolean)) {
    ok = false;
    line += `  ERRORS=${JSON.stringify(report.errors)}`;
  }
  console.log(line);
  canonical.set(name, Buffer.from(canonicalBytes(doc)).toString("hex"));
}

const unique = new Set(canonical.values());
if (unique.size > 1) {
  ok = false;
  console.error(`canonical bytes differ across languages: ${unique.size} variants`);
} else {
  console.log(`canonical bytes identical across ${files.length} emitters`);
}
process.exit(ok ? 0 : 1);
