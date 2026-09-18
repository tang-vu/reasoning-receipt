/** Conformance corpus runner — executes `conformance/vectors/*.json`.
 * Mirrors `protocol/conformance.py`; the same vector files drive every
 * SDK's conformance suite. */

import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { canonicalString } from "./canon.js";
import type { JsonValue } from "./canon.js";
import { ReceiptError } from "./errors.js";
import {
  PortableReceipt,
  ReceiptEdge,
  ReceiptNode,
  verifyProofDocument,
  KeyError,
} from "./receipt.js";
import { sign, verifySignatures } from "./signatures.js";
import { verifyAny } from "./verify.js";

const TAG = "$rr";
const TAGS: Record<string, unknown> = {
  nan: NaN,
  "+inf": Infinity,
  "-inf": -Infinity,
  "-0": -0,
};

function untag(value: unknown): unknown {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const o = value as Record<string, unknown>;
    if (Object.keys(o).length === 1 && TAG in o) {
      const tag = o[TAG] as string;
      if (tag in TAGS) return TAGS[tag];
      throw new Error(`unknown tag ${tag}`);
    }
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(o)) out[k] = untag(v);
    return out;
  }
  if (Array.isArray(value)) return value.map(untag);
  return value;
}

interface BuildSpec {
  subject: string;
  metadata?: Record<string, JsonValue>;
  nodes?: { id: string; kind: string; payload?: JsonValue; meta?: Record<string, JsonValue> }[];
  edges?: { from: string; to: string; rel: string }[];
  receipt_id?: string;
  produced_at?: string;
}

function build(spec: BuildSpec): PortableReceipt {
  const nodes = (spec.nodes ?? []).map(
    (n) => new ReceiptNode(n.id, n.kind, untag(n.payload) as JsonValue, n.meta),
  );
  const edges = (spec.edges ?? []).map((e) => new ReceiptEdge(e.from, e.to, e.rel));
  return new PortableReceipt({
    subject: spec.subject,
    metadata: spec.metadata ?? {},
    nodes,
    edges,
    receipt_id: spec.receipt_id ?? "rr-conformance",
    produced_at: spec.produced_at ?? "2026-01-01T00:00:00Z",
  });
}

type Result = [boolean, string];

function runCanon(vector: Record<string, unknown>): Result {
  const expect = vector.expect as Record<string, unknown>;
  try {
    const produced = canonicalString(untag(vector.input) as JsonValue);
    if ("error" in expect) return [false, `expected error ${expect.error}, encoded fine`];
    return [produced === expect.canonical, "canonical bytes differ"];
  } catch (exc) {
    if (exc instanceof ReceiptError && "error" in expect) {
      return [expect.error === exc.code, `error ${exc.code} vs ${expect.error}`];
    }
    return [false, `unexpected error ${exc instanceof ReceiptError ? exc.code : String(exc)}`];
  }
}

function runReceipt(vector: Record<string, unknown>): Result {
  const expect = vector.expect as Record<string, unknown>;
  let receipt: PortableReceipt;
  let envelope: Record<string, JsonValue>;
  try {
    receipt = build(vector.input as BuildSpec);
    envelope = receipt.committedEnvelope();
  } catch (exc) {
    if (exc instanceof ReceiptError && "error" in expect) {
      return [expect.error === exc.code, `error ${exc.code} vs ${expect.error}`];
    }
    return [false, `unexpected error ${exc instanceof ReceiptError ? `${exc.code}: ${exc.message}` : String(exc)}`];
  }
  if ("error" in expect) return [false, `expected error ${expect.error}, built fine`];
  const mismatches: string[] = [];
  if (JSON.stringify(sortObj(envelope.node_hashes)) !== JSON.stringify(sortObj(expect.node_hashes))) {
    mismatches.push("node_hashes");
  }
  if (JSON.stringify(envelope.edge_hashes) !== JSON.stringify(expect.edge_hashes)) {
    mismatches.push("edge_hashes");
  }
  if (envelope.merkle_root !== expect.merkle_root) mismatches.push("merkle_root");
  if ("receipt_hash" in expect && receipt.receiptHash() !== expect.receipt_hash) {
    mismatches.push("receipt_hash");
  }
  if ("canonical_envelope" in expect) {
    const produced = canonicalString(envelope);
    if (produced !== expect.canonical_envelope) mismatches.push("canonical_envelope");
  }
  return [mismatches.length === 0, `fields differ: ${mismatches.join(", ")}`];
}

function runDocument(vector: Record<string, unknown>): Result {
  const expect = vector.expect as Record<string, unknown>;
  const document = untag(vector.input) as Record<string, JsonValue>;
  const rep = verifyAny(document);
  if (rep.valid !== expect.valid) {
    return [false, `valid=${rep.valid} expected ${expect.valid} (${rep.errors})`];
  }
  for (const code of (expect.errors as string[]) ?? []) {
    if (!rep.errors.some((e) => e.includes(code))) {
      return [false, `missing expected error code ${code} in ${JSON.stringify(rep.errors)}`];
    }
  }
  return [true, ""];
}

function runProof(vector: Record<string, unknown>): Result {
  const expect = vector.expect as Record<string, unknown>;
  if ("proof_document" in vector) {
    const ok = verifyProofDocument(untag(vector.proof_document));
    return [ok === expect.verify, `verify=${ok} expected ${expect.verify}`];
  }
  const receipt = build(vector.input as BuildSpec);
  let proofDoc: ReturnType<PortableReceipt["proofFor"]>;
  if ("node" in expect) {
    try {
      proofDoc = receipt.proofFor(expect.node as string);
    } catch (exc) {
      if (exc instanceof KeyError && "error" in expect) return [true, ""];
      return [false, "node not found, no error expected"];
    }
  } else {
    proofDoc = receipt.proofForEdge(expect.edge_index as number);
  }
  if (proofDoc.leaf !== expect.leaf) return [false, "leaf differs"];
  if (JSON.stringify(proofDoc.proof) !== JSON.stringify(expect.proof)) {
    return [false, "proof siblings differ"];
  }
  if (proofDoc.merkle_root !== expect.merkle_root) return [false, "root differs"];
  return [verifyProofDocument(proofDoc), "generated proof does not verify"];
}

function runSignature(vector: Record<string, unknown>): Result {
  const expect = vector.expect as Record<string, unknown>;
  const committed = build(vector.input as BuildSpec).committedEnvelope();
  const spec = vector.sign as Record<string, string>;
  const sigObj = sign(committed, spec.private_key, {
    scope: spec.scope ?? "receipt",
    key_id: spec.key_id,
    signed_at: spec.signed_at,
  });
  if ("public_key" in expect && sigObj.public_key !== expect.public_key) {
    return [false, "public_key differs"];
  }
  if ("sig" in expect && sigObj.sig !== expect.sig) {
    return [false, "signature bytes differ"];
  }
  const target =
    "verify_against" in vector
      ? build(vector.verify_against as BuildSpec).committedEnvelope()
      : committed;
  const results = verifySignatures(target, [sigObj]);
  const ok = results[0].valid;
  return [ok === (expect.valid ?? true), `verify=${ok}`];
}

const RUNNERS: Record<string, (v: Record<string, unknown>) => Result> = {
  canon: runCanon,
  receipt: runReceipt,
  document: runDocument,
  proof: runProof,
  signature: runSignature,
};

function sortObj(o: unknown): unknown {
  if (o !== null && typeof o === "object" && !Array.isArray(o)) {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(o).sort()) out[k] = sortObj((o as Record<string, unknown>)[k]);
    return out;
  }
  return o;
}

export interface VectorResult {
  name: string;
  ok: boolean;
  detail: string;
}

export function runVector(vector: Record<string, unknown>, name: string): VectorResult {
  const runner = RUNNERS[vector.kind as string];
  try {
    const [ok, detail] = runner(vector);
    return { name, ok, detail };
  } catch (exc) {
    const expect = (vector.expect ?? {}) as Record<string, unknown>;
    if (exc instanceof ReceiptError) {
      const ok = expect.error === exc.code;
      return {
        name,
        ok,
        detail: `error ${exc.code}` + (ok ? "" : ` (wanted ${expect.error})`),
      };
    }
    return { name, ok: false, detail: `${(exc as Error).constructor.name}: ${(exc as Error).message}` };
  }
}

export interface CorpusReport {
  vectors: VectorResult[];
  total: number;
  passed: number;
  ok: boolean;
  implementation: string;
}

export function runCorpus(vectorDir: string): CorpusReport {
  const files = readdirSync(vectorDir)
    .filter((f) => f.endsWith(".json"))
    .sort();
  const entries = files.map((f) => {
    const vector = JSON.parse(readFileSync(join(vectorDir, f), "utf-8"));
    return runVector(vector, vector.name ?? f.replace(/\.json$/, ""));
  });
  const passed = entries.filter((e) => e.ok).length;
  return {
    vectors: entries,
    total: entries.length,
    passed,
    ok: passed === entries.length && entries.length > 0,
    implementation: "typescript",
  };
}
