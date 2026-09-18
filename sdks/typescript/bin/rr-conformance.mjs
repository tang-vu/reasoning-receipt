#!/usr/bin/env node
/** `rr-conformance [vector-dir]` — run the shared corpus, print JSON report. */
import { runCorpus } from "../dist/conformance.js";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const dir = process.argv[2] ?? join(here, "..", "..", "..", "conformance", "vectors");
const report = runCorpus(dir);
for (const v of report.vectors) {
  if (!v.ok) console.error(`  [FAIL] ${v.name}: ${v.detail}`);
}
console.log(JSON.stringify({ implementation: report.implementation, total: report.total, passed: report.passed, ok: report.ok }));
process.exit(report.ok ? 0 : 1);
