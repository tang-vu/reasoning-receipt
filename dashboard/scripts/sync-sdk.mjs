// Vendor the browser-safe modules of @reasoning-receipt/sdk into
// src/vendor/rr-sdk/ so the dashboard builds standalone (Vercel, GH Pages)
// without the sibling sdks/typescript checkout in its build context.
//
// Usage:  node scripts/sync-sdk.mjs           (from dashboard/)
//         npm run sync-sdk
//
// Re-run after `npm run build` in ../../sdks/typescript to pick up changes.

import { copyFileSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const SDK_DIST = join(here, "..", "..", "sdks", "typescript", "dist");
const OUT = join(here, "..", "src", "vendor", "rr-sdk");

// conformance.js is Node-only tooling (node:fs) — never shipped to the client.
const MODULES = [
  "canon",
  "errors",
  "hex",
  "legacy_canon",
  "merkle",
  "receipt",
  "signatures",
  "verify",
  "index",
];

mkdirSync(OUT, { recursive: true });

for (const mod of MODULES) {
  let js = readFileSync(join(SDK_DIST, `${mod}.js`), "utf8");
  if (mod === "receipt") {
    // Bundlers statically resolve `await import("node:fs/promises")` inside
    // loadReceiptFile and fail client builds. Stub it in the vendored copy.
    const needle = 'const { readFile } = await import("node:fs/promises");';
    if (!js.includes(needle)) {
      throw new Error("expected node:fs import in receipt.js — SDK changed?");
    }
    js = js.replace(
      needle,
      'throw new Error("loadReceiptFile is Node-only; pass the document to loadReceipt instead");',
    );
  }
  writeFileSync(join(OUT, `${mod}.js`), js);
  copyFileSync(join(SDK_DIST, `${mod}.d.ts`), join(OUT, `${mod}.d.ts`));
}

console.log(`synced ${MODULES.length} modules -> src/vendor/rr-sdk/`);
