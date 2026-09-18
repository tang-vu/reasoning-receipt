/** Unified verification entry point — dispatch strictly on `schema_version`.
 * Mirrors `protocol/verify.py` + `protocol/legacy.py`. */

import type { JsonValue } from "./canon.js";
import { ReceiptError } from "./errors.js";
import { legacyCanonicalBytes } from "./legacy_canon.js";
import { merkleRoot, sha256Hex } from "./merkle.js";
import {
  CANONICALIZATION,
  SCHEMA_VERSION,
  verifyReceipt,
} from "./receipt.js";
import type { VerifyReport } from "./receipt.js";
import { hexToBytes } from "./hex.js";

export const KNOWN_SCHEMAS = [SCHEMA_VERSION, "rr-trace/3", "rr-trace/2", "rr-trace/1"];
const TRACE_BLOB_SCHEMAS = new Set(["rr-trace/1", "rr-trace/2"]);
const TRACE_DAG_SCHEMA = "rr-trace/3";
const LEGACY_CANON = "legacy-json-6dp";

const CRITIC_DIMS = [
  "evidence_relevance",
  "falsifiability",
  "scope",
  "coherence",
  "exploration_integrity",
  "methodology",
];

function report(p: Partial<VerifyReport> & Pick<VerifyReport, "valid" | "schema_version" | "canonicalization" | "variant" | "checks" | "errors">): VerifyReport {
  return {
    signatures: [],
    receipt_hash: null,
    merkle_root: null,
    node_count: 0,
    edge_count: 0,
    ...p,
  };
}

function bytes32(hexStr: unknown): Uint8Array {
  const raw = typeof hexStr === "string" && hexStr.startsWith("0x") ? hexStr.slice(2) : (hexStr as string);
  return hexToBytes(raw);
}

export function legacyTraceHash(document: Record<string, JsonValue>): string {
  return sha256Hex(legacyCanonicalBytes(document));
}

export function verifyTraceBlob(
  document: Record<string, JsonValue>,
  expectedHash?: string,
): VerifyReport {
  const schema = String(document.schema_version);
  const errors: string[] = [];
  const checks: Record<string, boolean> = {};
  for (const fieldName of ["market_id", "claim", "probability", "produced_at"]) {
    checks[`has_${fieldName}`] = fieldName in document;
    if (!checks[`has_${fieldName}`]) errors.push(`missing_field: ${fieldName}`);
  }
  let recomputed: string | null = null;
  try {
    recomputed = legacyTraceHash(document);
    checks.canonicalizable = true;
  } catch (exc) {
    checks.canonicalizable = false;
    errors.push(exc instanceof ReceiptError ? `${exc.code}: ${exc.message}` : String(exc));
  }
  if (expectedHash !== undefined) {
    checks.hash_matches_expected =
      recomputed !== null && recomputed.toLowerCase() === expectedHash.toLowerCase();
    if (!checks.hash_matches_expected) {
      errors.push("hash_mismatch: recomputed hash != expected anchored hash");
    }
  }
  return report({
    valid: Object.values(checks).every(Boolean),
    schema_version: schema,
    canonicalization: LEGACY_CANON,
    variant: schema,
    checks,
    errors,
    receipt_hash: recomputed,
  });
}

function extractTrace3Nodes(document: Record<string, JsonValue>): Record<string, Record<string, JsonValue>> {
  const out: Record<string, Record<string, JsonValue>> = {};
  const claim = document.claim;
  if (claim !== null && typeof claim === "object" && !Array.isArray(claim) && "id" in claim) {
    out[(claim as Record<string, JsonValue>).id as string] = { ...(claim as Record<string, JsonValue>) };
  }
  const stances = document.stances;
  if (Array.isArray(stances)) {
    for (const stance of stances) {
      if (stance === null || typeof stance !== "object" || Array.isArray(stance) || !("id" in stance)) continue;
      const sdict = { ...(stance as Record<string, JsonValue>) };
      const evidenceList = (sdict.evidence as JsonValue[]) ?? [];
      delete sdict.evidence;
      out[sdict.id as string] = sdict;
      for (const ev of evidenceList) {
        if (ev !== null && typeof ev === "object" && !Array.isArray(ev) && "id" in ev) {
          out[(ev as Record<string, JsonValue>).id as string] = { ...(ev as Record<string, JsonValue>) };
        }
      }
    }
  }
  for (const key of ["counter_arguments", "sensitivity", "falsifiable_claims"]) {
    const items = document[key];
    if (Array.isArray(items)) {
      for (const item of items) {
        if (item !== null && typeof item === "object" && !Array.isArray(item) && "id" in item) {
          out[(item as Record<string, JsonValue>).id as string] = { ...(item as Record<string, JsonValue>) };
        }
      }
    }
  }
  const audit = document.critic_audit;
  if (audit !== null && typeof audit === "object" && !Array.isArray(audit)) {
    const a = audit as Record<string, JsonValue>;
    for (const dim of CRITIC_DIMS) {
      const v = a[dim];
      if (v !== null && typeof v === "object" && !Array.isArray(v)) {
        out[`cd_${dim}`] = { ...(v as Record<string, JsonValue>) };
      }
    }
  }
  return out;
}

export function verifyTrace3(document: Record<string, JsonValue>): VerifyReport {
  const errors: string[] = [];
  const checks: Record<string, boolean> = {};
  const nodes = extractTrace3Nodes(document);
  checks.nodes_extracted = Object.keys(nodes).length > 0;
  if (!checks.nodes_extracted) {
    errors.push("invalid_shape: no rr-trace/3 nodes could be extracted");
  }

  let embeddedHashes = document.node_hashes;
  checks.node_hashes_present =
    embeddedHashes !== null && typeof embeddedHashes === "object" && !Array.isArray(embeddedHashes) &&
    Object.keys(embeddedHashes).length > 0;
  if (!checks.node_hashes_present) {
    errors.push("missing_field: 'node_hashes'");
    embeddedHashes = {};
  }
  const embedded = embeddedHashes as Record<string, JsonValue>;

  const recomputed: Record<string, string> = {};
  for (const [nodeId, nodeDict] of Object.entries(nodes)) {
    recomputed[nodeId] = sha256Hex(legacyCanonicalBytes(nodeDict));
  }
  checks.hashes =
    Object.keys(embedded).length > 0 &&
    JSON.stringify(sortObj(recomputed)) === JSON.stringify(sortObj(embedded));
  if (Object.keys(embedded).length > 0 && !checks.hashes) {
    errors.push("hash_mismatch: embedded node_hashes != recomputed");
  }

  const embeddedRoot = document.merkle_root;
  let rootHex: string | null = null;
  if (Object.keys(embedded).length > 0) {
    try {
      const leaves = Object.keys(embedded)
        .sort()
        .map((i) => bytes32(embedded[i]));
      rootHex = merkleRoot(leaves);
      checks.root = rootHex === embeddedRoot;
      if (!checks.root) {
        errors.push("root_mismatch: embedded merkle_root != recomputed");
      }
    } catch (exc) {
      checks.root = false;
      errors.push(`malformed_hash: ${String(exc)}`);
    }
  } else {
    checks.root = false;
    errors.push("missing_field: 'merkle_root'");
  }

  let blobHash: string | null = null;
  try {
    blobHash = legacyTraceHash(document);
  } catch {
    blobHash = null;
  }

  return report({
    valid: Object.values(checks).every(Boolean),
    schema_version: TRACE_DAG_SCHEMA,
    canonicalization: LEGACY_CANON,
    variant: TRACE_DAG_SCHEMA,
    checks,
    errors,
    receipt_hash: blobHash,
    merkle_root: typeof embeddedRoot === "string" ? embeddedRoot : null,
    node_count: Object.keys(nodes).length,
  });
}

const DRAFT_REQUIRED = [
  "schema_version", "receipt_id", "subject", "produced_at",
  "nodes", "node_hashes", "merkle_root",
];

export function verifyReceiptDraft(document: Record<string, JsonValue>): VerifyReport {
  const errors: string[] = [];
  const checks: Record<string, boolean> = {};
  for (const fieldName of [...DRAFT_REQUIRED].sort()) {
    checks[`has_${fieldName}`] = fieldName in document;
    if (!checks[`has_${fieldName}`]) errors.push(`missing_field: ${fieldName}`);
  }
  if (document.schema_version !== SCHEMA_VERSION) {
    errors.push("unsupported_schema: not reasoning-receipt/1");
    checks.schema = false;
  } else {
    checks.schema = true;
  }

  const rawNodes = Array.isArray(document.nodes) ? document.nodes : [];
  const ids = rawNodes
    .filter((n) => n !== null && typeof n === "object" && !Array.isArray(n))
    .map((n) => (n as Record<string, JsonValue>).id);
  checks.unique_ids =
    ids.length === new Set(ids).size && !ids.some((i) => i === undefined || i === null);
  checks.nonempty = rawNodes.length > 0;

  try {
    const subject = document.subject ?? "";
    if (typeof subject === "string") {
      for (const ch of subject) {
        const cp = ch.codePointAt(0)!;
        if (cp < 0x20 || cp === 0x7f) throw new ReceiptError("subject contains a control character", "empty_subject");
      }
    }
  } catch (exc) {
    checks.subject = false;
    errors.push(exc instanceof ReceiptError ? `${exc.code}: ${exc.message}` : String(exc));
  }

  let rootHex: string | null = null;
  if (checks.unique_ids && rawNodes.length) {
    try {
      const ordered = [...rawNodes]
        .filter((n): n is Record<string, JsonValue> => n !== null && typeof n === "object" && !Array.isArray(n))
        .sort((a, b) => ((a.id as string) < (b.id as string) ? -1 : (a.id as string) > (b.id as string) ? 1 : 0));
      const recomputed: Record<string, string> = {};
      for (const nd of ordered) {
        recomputed[nd.id as string] = sha256Hex(legacyCanonicalBytes(nd));
      }
      const leaves = Object.keys(recomputed)
        .sort()
        .map((i) => bytes32(recomputed[i]));
      rootHex = merkleRoot(leaves);
      const embedded = (document.node_hashes ?? {}) as Record<string, JsonValue>;
      checks.hashes = JSON.stringify(sortObj(recomputed)) === JSON.stringify(sortObj(embedded));
      checks.root = rootHex === document.merkle_root;
      if (!checks.hashes) {
        errors.push("hash_mismatch: node_hashes != recomputed (draft rules)");
      }
      if (!checks.root) {
        errors.push("root_mismatch: merkle_root != recomputed (draft rules)");
      }
    } catch (exc) {
      checks.hashes = false;
      errors.push(`malformed: ${String(exc)}`);
    }
  }

  return report({
    valid: Object.values(checks).every(Boolean) && rawNodes.length > 0,
    schema_version: SCHEMA_VERSION,
    canonicalization: LEGACY_CANON,
    variant: "draft",
    checks,
    errors,
    merkle_root: typeof document.merkle_root === "string" ? document.merkle_root : null,
    node_count: rawNodes.length,
  });
}

function sortObj(o: unknown): unknown {
  if (o !== null && typeof o === "object" && !Array.isArray(o)) {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(o).sort()) out[k] = sortObj((o as Record<string, unknown>)[k]);
    return out;
  }
  return o;
}

export function verifyAny(document: unknown, expectedHash?: string): VerifyReport {
  if (document === null || typeof document !== "object" || Array.isArray(document)) {
    return report({
      valid: false,
      schema_version: "unknown",
      canonicalization: "unknown",
      variant: "unknown",
      checks: { shape: false },
      errors: ["bad_type: document is not an object"],
    });
  }
  const doc = document as Record<string, JsonValue>;
  const schema = doc.schema_version;

  if (schema === SCHEMA_VERSION) {
    const rep = verifyReceipt(doc);
    if (rep.valid) return rep;
    const hasDraftShape = !("edges" in doc) && !("edge_hashes" in doc) && !("signatures" in doc);
    if (hasDraftShape) {
      const draft = verifyReceiptDraft(doc);
      if (draft.valid) return draft;
    }
    return rep;
  }
  if (TRACE_BLOB_SCHEMAS.has(String(schema))) {
    return verifyTraceBlob(doc, expectedHash);
  }
  if (schema === TRACE_DAG_SCHEMA) {
    return verifyTrace3(doc);
  }
  return report({
    valid: false,
    schema_version: schema != null ? String(schema) : "missing",
    canonicalization: "unknown",
    variant: "unknown",
    checks: { shape: false },
    errors: [`unsupported_schema: ${String(schema)} — refusing to verify under guessed rules`],
  });
}

export function supportedSchemas(): Record<string, JsonValue>[] {
  return [
    {
      schema_version: SCHEMA_VERSION,
      status: "current",
      canonicalization: CANONICALIZATION,
      features: ["nodes", "edges", "merkle_proofs", "signatures"],
    },
    {
      schema_version: "rr-trace/3",
      status: "legacy",
      canonicalization: LEGACY_CANON,
      features: ["nodes", "merkle_proofs"],
    },
    {
      schema_version: "rr-trace/2",
      status: "legacy",
      canonicalization: LEGACY_CANON,
      features: ["blob_hash"],
    },
    {
      schema_version: "rr-trace/1",
      status: "legacy",
      canonicalization: LEGACY_CANON,
      features: ["blob_hash"],
    },
  ];
}
