import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { runVector } from "../src/conformance.js";

// The shared language-independent corpus at the repo root.
const VECTOR_DIR = join(__dirname, "..", "..", "..", "conformance", "vectors");
const files = readdirSync(VECTOR_DIR).filter((f) => f.endsWith(".json")).sort();

describe("reasoning-receipt/1 conformance corpus", () => {
  for (const file of files) {
    const vector = JSON.parse(readFileSync(join(VECTOR_DIR, file), "utf-8"));
    it(vector.name ?? file.replace(/\.json$/, ""), () => {
      const result = runVector(vector, vector.name ?? file);
      expect(result.ok, result.detail).toBe(true);
    });
  }
});
