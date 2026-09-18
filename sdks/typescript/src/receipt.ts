/** `reasoning-receipt/1` — portable evidence-receipt envelope.
 * Mirrors `protocol/receipt.py` exactly (spec §3–§6, §9–§12). */

import { canonicalBytes, CANONICALIZATION_ID, parseJsonObject } from "./canon.js";
import type { JsonValue } from "./canon.js";
import {
  E_BAD_HASH,
  E_BAD_KIND,
  E_BAD_NODE_ID,
  E_BAD_REL,
  E_BAD_SCHEMA,
  E_BAD_TIMESTAMP,
  E_BAD_TYPE,
  E_CYCLE,
  E_DANGLING_EDGE,
  E_DUP_EDGE,
  E_DUP_NODE_ID,
  E_EMPTY_NODES,
  E_EMPTY_RECEIPT_ID,
  E_EMPTY_SUBJECT,
  E_LIMIT,
  E_MISSING_FIELD,
  E_SELF_LOOP,
  E_UNKNOWN_FIELD,
  CanonError,
  GraphError,
  ReceiptError,
  SchemaError,
  ShapeError,
} from "./errors.js";
import { hexToBytes, merkleProof, merkleRoot, sha256Hex, verifyMerkleProof } from "./merkle.js";
import { verifySignatures } from "./signatures.js";
import type { SignatureResult } from "./signatures.js";

export const SCHEMA_VERSION = "reasoning-receipt/1";
export const CANONICALIZATION = CANONICALIZATION_ID;

const NODE_ID_RE = /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$/;
const VOCAB_RE = /^[a-z][a-z0-9_]{0,63}$/;
const TIMESTAMP_RE = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})Z$/;

const MAX_NODES = 1024;
const MAX_EDGES = 4096;
const MAX_SUBJECT = 500;
const MAX_RECEIPT_ID = 128;
const ENVELOPE_MAX_BYTES = 8 << 20; // 8 MiB

const ENVELOPE_FIELDS = new Set([
  "schema_version", "receipt_id", "subject", "produced_at", "metadata",
  "nodes", "edges", "node_hashes", "edge_hashes", "merkle_root",
  "signatures", "receipt_hash",
]);
const REQUIRED_FIELDS = [
  "schema_version", "receipt_id", "subject", "produced_at",
  "nodes", "node_hashes", "edge_hashes", "merkle_root",
];
const NODE_FIELDS = new Set(["id", "kind", "payload", "meta"]);
const EDGE_FIELDS = new Set(["from", "to", "rel"]);

const LEAF_DOMAIN_NODE = concat(new TextEncoder().encode("RR1:node"), new Uint8Array([0]));
const LEAF_DOMAIN_EDGE = concat(new TextEncoder().encode("RR1:edge"), new Uint8Array([0]));
const HASH_DOMAIN_RECEIPT = concat(new TextEncoder().encode("RR1:receipt"), new Uint8Array([0]));

function concat(a: Uint8Array, b: Uint8Array): Uint8Array {
  const out = new Uint8Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}

function utcNowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function checkNoControls(value: string, what: string, code: string): void {
  for (const ch of value) {
    const cp = ch.codePointAt(0)!;
    if (cp < 0x20 || cp === 0x7f) {
      throw new ShapeError(`${what} contains a control character`, code);
    }
  }
}

export function validTimestamp(value: unknown): boolean {
  if (typeof value !== "string") return false;
  const m = TIMESTAMP_RE.exec(value);
  if (!m) return false;
  const [, y, mo, d, h, mi, s] = m;
  const year = +y, mon = +mo, day = +d, hour = +h, min = +mi, sec = +s;
  if (mon < 1 || mon > 12 || day < 1 || hour > 23 || min > 59 || sec > 59) return false;
  return day <= new Date(Date.UTC(year, mon, 0)).getUTCDate();
}

export function bytes32Hex(value: unknown, what = "hash"): Uint8Array {
  if (typeof value !== "string") {
    throw new ShapeError(`${what} is not a string`, E_BAD_HASH);
  }
  const raw = value.startsWith("0x") ? value.slice(2) : value;
  if (!/^[0-9a-fA-F]+$/.test(raw)) {
    throw new ShapeError(`${what} is not hex`, E_BAD_HASH);
  }
  const decoded = Uint8Array.from(Buffer.from(raw, "hex"));
  if (decoded.length !== 32) {
    throw new ShapeError(`${what} is ${decoded.length} bytes, expected 32`, E_BAD_HASH);
  }
  return decoded;
}

// ------------------------------------------------------------------ leaves

export interface NodeDict {
  id: string;
  kind: string;
  payload: JsonValue;
  meta?: Record<string, JsonValue>;
}

export interface EdgeDict {
  from: string;
  to: string;
  rel: string;
}

export function nodeLeaf(nodeDict: NodeDict): Uint8Array {
  return sha256Bytes(concat(LEAF_DOMAIN_NODE, canonicalBytes(nodeDict as unknown as JsonValue)));
}

export function edgeLeaf(edgeDict: EdgeDict): Uint8Array {
  return sha256Bytes(concat(LEAF_DOMAIN_EDGE, canonicalBytes(edgeDict as unknown as JsonValue)));
}

function sha256Bytes(b: Uint8Array): Uint8Array {
  return hexToBytes(sha256Hex(b));
}

export function merkleRootOf(leaves: Uint8Array[]): Uint8Array {
  const sorted = [...leaves].sort(cmpBytes);
  return hexToBytes(merkleRoot(sorted));
}

function cmpBytes(a: Uint8Array, b: Uint8Array): number {
  const m = Math.min(a.length, b.length);
  for (let i = 0; i < m; i++) {
    if (a[i] !== b[i]) return a[i] - b[i];
  }
  return a.length - b.length;
}

export function receiptHashOf(committedEnvelope: Record<string, JsonValue>): string {
  return sha256Hex(concat(HASH_DOMAIN_RECEIPT, canonicalBytes(committedEnvelope as JsonValue)));
}

// ------------------------------------------------------------------- model

export class ReceiptNode {
  constructor(
    public id: string,
    public kind: string,
    public payload: JsonValue,
    public meta?: Record<string, JsonValue>,
  ) {}

  validate(): void {
    if (!NODE_ID_RE.test(this.id)) {
      throw new GraphError(`invalid node id ${this.id}`, E_BAD_NODE_ID);
    }
    if (!VOCAB_RE.test(this.kind)) {
      throw new GraphError(`invalid node kind ${this.kind}`, E_BAD_KIND);
    }
    if (this.meta !== undefined && (this.meta === null || typeof this.meta !== "object" || Array.isArray(this.meta))) {
      throw new ShapeError("node meta must be an object", E_BAD_TYPE);
    }
    canonicalBytes(this.toDict() as unknown as JsonValue);
  }

  toDict(): NodeDict {
    const out: NodeDict = { id: this.id, kind: this.kind, payload: this.payload };
    if (this.meta !== undefined) out.meta = this.meta;
    return out;
  }
}

export class ReceiptEdge {
  constructor(
    public src: string,
    public dst: string,
    public rel: string,
  ) {}

  validate(): void {
    if (!NODE_ID_RE.test(this.src)) {
      throw new GraphError(`invalid edge source ${this.src}`, E_BAD_NODE_ID);
    }
    if (!NODE_ID_RE.test(this.dst)) {
      throw new GraphError(`invalid edge target ${this.dst}`, E_BAD_NODE_ID);
    }
    if (!VOCAB_RE.test(this.rel)) {
      throw new GraphError(`invalid edge rel ${this.rel}`, E_BAD_REL);
    }
    if (this.src === this.dst) {
      throw new GraphError(`self-loop on ${this.src}`, E_SELF_LOOP);
    }
  }

  toDict(): EdgeDict {
    return { from: this.src, to: this.dst, rel: this.rel };
  }
}

export interface ProofDocument {
  schema_version: string;
  item_type: "node" | "edge";
  item: NodeDict | EdgeDict;
  leaf: string;
  merkle_root: string;
  proof: string[];
}

export class PortableReceipt {
  subject: string;
  nodes: ReceiptNode[];
  edges: ReceiptEdge[];
  metadata: Record<string, JsonValue>;
  receipt_id: string;
  produced_at: string;
  schema_version: string;
  signatures: Record<string, JsonValue>[];

  constructor(opts: {
    subject: string;
    nodes: ReceiptNode[];
    edges?: ReceiptEdge[];
    metadata?: Record<string, JsonValue>;
    receipt_id?: string;
    produced_at?: string;
    schema_version?: string;
    signatures?: Record<string, JsonValue>[];
  }) {
    this.subject = opts.subject;
    this.nodes = opts.nodes;
    this.edges = opts.edges ?? [];
    this.metadata = opts.metadata ?? {};
    this.receipt_id = opts.receipt_id ?? crypto.randomUUID();
    this.produced_at = opts.produced_at ?? utcNowIso();
    this.schema_version = opts.schema_version ?? SCHEMA_VERSION;
    this.signatures = opts.signatures ?? [];
  }

  private orderedNodes(): ReceiptNode[] {
    if (typeof this.subject !== "string" || !this.subject.trim()) {
      throw new ShapeError("receipt subject must not be empty", E_EMPTY_SUBJECT);
    }
    if (this.subject.length > MAX_SUBJECT) {
      throw new ShapeError("subject too long", E_LIMIT);
    }
    checkNoControls(this.subject, "subject", E_EMPTY_SUBJECT);
    if (!this.nodes.length) {
      throw new ShapeError("receipt must contain at least one node", E_EMPTY_NODES);
    }
    if (this.nodes.length > MAX_NODES) {
      throw new ShapeError("too many nodes", E_LIMIT);
    }
    const ids = new Set<string>();
    for (const node of this.nodes) {
      node.validate();
      if (ids.has(node.id)) {
        throw new GraphError(`duplicate node id ${node.id}`, E_DUP_NODE_ID);
      }
      ids.add(node.id);
    }
    return [...this.nodes].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
  }

  private orderedEdges(): ReceiptEdge[] {
    if (this.edges.length > MAX_EDGES) {
      throw new ShapeError("too many edges", E_LIMIT);
    }
    const nodeIds = new Set(this.nodes.map((n) => n.id));
    const triples = new Set<string>();
    for (const edge of this.edges) {
      edge.validate();
      const triple = `${edge.src} ${edge.dst} ${edge.rel}`;
      if (triples.has(triple)) {
        throw new GraphError(`duplicate edge ${triple}`, E_DUP_EDGE);
      }
      triples.add(triple);
      for (const endpoint of [edge.src, edge.dst]) {
        if (!nodeIds.has(endpoint)) {
          throw new GraphError(`edge references unknown node ${endpoint}`, E_DANGLING_EDGE);
        }
      }
    }
    const ordered = [...this.edges].sort((a, b) => {
      const ka = `${a.src} ${a.dst} ${a.rel}`;
      const kb = `${b.src} ${b.dst} ${b.rel}`;
      return ka < kb ? -1 : ka > kb ? 1 : 0;
    });
    assertAcyclic(ordered);
    return ordered;
  }

  nodeDicts(): NodeDict[] {
    return this.orderedNodes().map((n) => n.toDict());
  }

  edgeDicts(): EdgeDict[] {
    return this.orderedEdges().map((e) => e.toDict());
  }

  leaves(): Uint8Array[] {
    const set = this.nodeDicts().map(nodeLeaf);
    set.push(...this.edgeDicts().map(edgeLeaf));
    return set.sort(cmpBytes);
  }

  nodeHashes(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const nd of this.nodeDicts()) {
      out[nd.id] = "0x" + Buffer.from(nodeLeaf(nd)).toString("hex");
    }
    return out;
  }

  edgeHashes(): string[] {
    return this.edgeDicts().map((ed) => "0x" + Buffer.from(edgeLeaf(ed)).toString("hex"));
  }

  merkleRootHex(): string {
    return "0x" + Buffer.from(merkleRootOf(this.leaves())).toString("hex");
  }

  committedEnvelope(): Record<string, JsonValue> {
    if (!validTimestamp(this.produced_at)) {
      throw new ShapeError(`invalid produced_at ${this.produced_at}`, E_BAD_TIMESTAMP);
    }
    if (
      typeof this.receipt_id !== "string" ||
      this.receipt_id.length === 0 ||
      this.receipt_id.length > MAX_RECEIPT_ID
    ) {
      throw new ShapeError("invalid receipt_id", E_EMPTY_RECEIPT_ID);
    }
    checkNoControls(this.receipt_id, "receipt_id", E_EMPTY_RECEIPT_ID);
    return {
      schema_version: this.schema_version,
      receipt_id: this.receipt_id,
      subject: this.subject,
      produced_at: this.produced_at,
      metadata: this.metadata,
      nodes: this.nodeDicts() as unknown as JsonValue,
      edges: this.edgeDicts() as unknown as JsonValue,
      node_hashes: this.nodeHashes() as unknown as JsonValue,
      edge_hashes: this.edgeHashes() as unknown as JsonValue,
      merkle_root: this.merkleRootHex(),
    };
  }

  toDict(): Record<string, JsonValue> {
    const envelope = this.committedEnvelope();
    if (this.signatures.length) {
      envelope.signatures = this.signatures as unknown as JsonValue;
    }
    envelope.receipt_hash = this.receiptHash();
    return envelope;
  }

  receiptHash(): string {
    return receiptHashOf(this.committedEnvelope());
  }

  canonicalBytes(): Uint8Array {
    return canonicalBytes(this.committedEnvelope());
  }

  proofFor(nodeId: string): ProofDocument {
    const ordered = this.nodeDicts();
    const ids = ordered.map((n) => n.id);
    const idx = ids.indexOf(nodeId);
    if (idx === -1) throw new KeyError(`node ${nodeId} not in receipt`);
    const leaves = this.leaves();
    const leaf = nodeLeaf(ordered[idx]);
    const index = leaves.findIndex((l) => cmpBytes(l, leaf) === 0);
    return {
      schema_version: this.schema_version,
      item_type: "node",
      item: ordered[idx],
      leaf: "0x" + Buffer.from(leaf).toString("hex"),
      merkle_root: "0x" + Buffer.from(merkleRootOf(leaves)).toString("hex"),
      proof: merkleProof(leaves, index),
    };
  }

  proofForEdge(index: number): ProofDocument {
    const edgeDicts = this.edgeDicts();
    if (index < 0 || index >= edgeDicts.length) {
      throw new IndexError(`edge index ${index} out of range`);
    }
    const leaves = this.leaves();
    const leaf = edgeLeaf(edgeDicts[index]);
    const leafIndex = leaves.findIndex((l) => cmpBytes(l, leaf) === 0);
    return {
      schema_version: this.schema_version,
      item_type: "edge",
      item: edgeDicts[index],
      leaf: "0x" + Buffer.from(leaf).toString("hex"),
      merkle_root: "0x" + Buffer.from(merkleRootOf(leaves)).toString("hex"),
      proof: merkleProof(leaves, leafIndex),
    };
  }
}

export class KeyError extends Error {}
export class IndexError extends Error {}

function assertAcyclic(edges: ReceiptEdge[]): void {
  const adjacency = new Map<string, string[]>();
  for (const edge of edges) {
    const list = adjacency.get(edge.src) ?? [];
    list.push(edge.dst);
    adjacency.set(edge.src, list);
  }
  const WHITE = 0, GRAY = 1, BLACK = 2;
  const color = new Map<string, number>();
  for (const start of adjacency.keys()) {
    if ((color.get(start) ?? WHITE) !== WHITE) continue;
    const stack: { node: string; it: Iterator<string> }[] = [
      { node: start, it: (adjacency.get(start) ?? [])[Symbol.iterator]() },
    ];
    color.set(start, GRAY);
    while (stack.length) {
      const top = stack[stack.length - 1];
      let advanced = false;
      for (let n = top.it.next(); !n.done; n = top.it.next()) {
        const nxt = n.value;
        const state = color.get(nxt) ?? WHITE;
        if (state === GRAY) {
          throw new GraphError(`cycle detected via edge ${top.node} -> ${nxt}`, E_CYCLE);
        }
        if (state === WHITE) {
          color.set(nxt, GRAY);
          stack.push({ node: nxt, it: (adjacency.get(nxt) ?? [])[Symbol.iterator]() });
          advanced = true;
          break;
        }
      }
      if (!advanced) {
        color.set(top.node, BLACK);
        stack.pop();
      }
    }
  }
}

// ----------------------------------------------------------------- builder

export class ReceiptBuilder {
  private nodes: ReceiptNode[] = [];
  private edges: ReceiptEdge[] = [];

  constructor(
    private subject: string,
    private metadata: Record<string, JsonValue> = {},
  ) {}

  add(nodeId: string, kind: string, payload: JsonValue, meta?: Record<string, JsonValue>): this {
    this.nodes.push(new ReceiptNode(nodeId, kind, payload, meta));
    return this;
  }

  link(src: string, dst: string, rel: string): this {
    this.edges.push(new ReceiptEdge(src, dst, rel));
    return this;
  }

  finalize(opts: { receipt_id?: string; produced_at?: string } = {}): PortableReceipt {
    const receipt = new PortableReceipt({
      subject: this.subject,
      metadata: this.metadata,
      nodes: this.nodes,
      edges: this.edges,
      receipt_id: opts.receipt_id,
      produced_at: opts.produced_at,
    });
    receipt.toDict(); // force full validation now
    return receipt;
  }
}

// ----------------------------------------------------------------- reports

export interface VerifyReport {
  valid: boolean;
  schema_version: string;
  canonicalization: string;
  variant: string;
  checks: Record<string, boolean>;
  errors: string[];
  signatures: Record<string, JsonValue>[];
  receipt_hash: string | null;
  merkle_root: string | null;
  node_count: number;
  edge_count: number;
}

function report(partial: Partial<VerifyReport> & Pick<VerifyReport, "valid" | "schema_version" | "canonicalization" | "variant" | "checks" | "errors">): VerifyReport {
  return {
    signatures: [],
    receipt_hash: null,
    merkle_root: null,
    node_count: 0,
    edge_count: 0,
    ...partial,
  };
}

// ----------------------------------------------------------------- restore

function require(cond: boolean, message: string, code: string): void {
  if (!cond) throw new ShapeError(message, code);
}

export function restoreReceipt(document: unknown): PortableReceipt {
  if (document === null || typeof document !== "object" || Array.isArray(document)) {
    throw new ShapeError("receipt document is not an object", E_BAD_TYPE);
  }
  const doc = document as Record<string, unknown>;

  const unknown = Object.keys(doc).filter((k) => !ENVELOPE_FIELDS.has(k));
  if (unknown.length) {
    throw new ShapeError(`unknown top-level fields ${unknown.sort()}`, E_UNKNOWN_FIELD);
  }
  for (const required of [...REQUIRED_FIELDS].sort()) {
    if (!(required in doc)) {
      throw new ShapeError(`missing field ${required}`, E_MISSING_FIELD);
    }
  }
  if (doc.schema_version !== SCHEMA_VERSION) {
    throw new SchemaError(`unsupported schema_version ${String(doc.schema_version)}`, E_BAD_SCHEMA);
  }

  const receipt_id = doc.receipt_id;
  require(
    typeof receipt_id === "string" && receipt_id.length > 0 && receipt_id.length <= MAX_RECEIPT_ID,
    "invalid receipt_id",
    E_EMPTY_RECEIPT_ID,
  );
  checkNoControls(receipt_id as string, "receipt_id", E_EMPTY_RECEIPT_ID);

  const produced_at = doc.produced_at;
  if (!validTimestamp(produced_at)) {
    throw new ShapeError(`invalid produced_at ${String(produced_at)}`, E_BAD_TIMESTAMP);
  }

  const metadata = doc.metadata ?? {};
  require(
    metadata !== null && typeof metadata === "object" && !Array.isArray(metadata),
    "metadata must be an object",
    E_BAD_TYPE,
  );

  const rawNodes = doc.nodes;
  require(Array.isArray(rawNodes), "nodes must be an array", E_BAD_TYPE);
  const nodes: ReceiptNode[] = [];
  for (const raw of rawNodes as unknown[]) {
    require(raw !== null && typeof raw === "object" && !Array.isArray(raw), "node is not an object", E_BAD_TYPE);
    const n = raw as Record<string, unknown>;
    const extra = Object.keys(n).filter((k) => !NODE_FIELDS.has(k));
    if (extra.length) {
      throw new ShapeError(`unknown node fields ${extra.sort()}`, E_UNKNOWN_FIELD);
    }
    for (const needed of ["id", "kind", "payload"]) {
      if (!(needed in n)) {
        throw new ShapeError(`node missing ${needed}`, E_MISSING_FIELD);
      }
    }
    nodes.push(
      new ReceiptNode(
        n.id as string,
        n.kind as string,
        n.payload as JsonValue,
        n.meta as Record<string, JsonValue> | undefined,
      ),
    );
  }

  const rawEdges = doc.edges ?? [];
  require(Array.isArray(rawEdges), "edges must be an array", E_BAD_TYPE);
  const edges: ReceiptEdge[] = [];
  for (const raw of rawEdges as unknown[]) {
    require(raw !== null && typeof raw === "object" && !Array.isArray(raw), "edge is not an object", E_BAD_TYPE);
    const e = raw as Record<string, unknown>;
    const keys = Object.keys(e);
    if (keys.length !== EDGE_FIELDS.size || !keys.every((k) => EDGE_FIELDS.has(k))) {
      throw new ShapeError(
        `edge must have exactly ${[...EDGE_FIELDS].sort()}`,
        E_UNKNOWN_FIELD,
      );
    }
    edges.push(new ReceiptEdge(e.from as string, e.to as string, e.rel as string));
  }

  require(
    doc.node_hashes !== null && typeof doc.node_hashes === "object" && !Array.isArray(doc.node_hashes),
    "node_hashes must be an object",
    E_BAD_TYPE,
  );
  require(Array.isArray(doc.edge_hashes), "edge_hashes must be an array", E_BAD_TYPE);
  for (const value of [
    ...Object.values(doc.node_hashes as Record<string, unknown>),
    ...(doc.edge_hashes as unknown[]),
  ]) {
    bytes32Hex(value, "leaf hash");
  }
  bytes32Hex(doc.merkle_root, "merkle_root");

  const signatures = doc.signatures ?? [];
  require(Array.isArray(signatures), "signatures must be an array", E_BAD_TYPE);

  const encoded = canonicalBytes(doc as JsonValue); // throws CanonError
  if (encoded.length > ENVELOPE_MAX_BYTES) {
    throw new ShapeError("envelope exceeds 8 MiB", E_LIMIT);
  }

  return new PortableReceipt({
    receipt_id: receipt_id as string,
    subject: doc.subject as string,
    produced_at: produced_at as string,
    metadata: metadata as Record<string, JsonValue>,
    nodes,
    edges,
    signatures: signatures as Record<string, JsonValue>[],
  });
}

// ------------------------------------------------------------------ verify

export function verifyReceipt(document: unknown): VerifyReport {
  const checks: Record<string, boolean> = {};
  const errors: string[] = [];
  let receipt: PortableReceipt;
  try {
    receipt = restoreReceipt(document);
    checks.shape = true;
  } catch (exc) {
    checks.shape = false;
    if (exc instanceof ReceiptError) {
      errors.push(`${exc.code}: ${exc.message}`);
    } else {
      errors.push(`receipt_error: ${String(exc)}`);
    }
    return report({
      valid: false,
      schema_version:
        document !== null && typeof document === "object" && !Array.isArray(document)
          ? String((document as Record<string, unknown>).schema_version ?? "unknown")
          : "unknown",
      canonicalization: CANONICALIZATION,
      variant: "final",
      checks,
      errors,
    });
  }

  let expected: Record<string, JsonValue>;
  try {
    expected = receipt.committedEnvelope();
    checks.graph = true;
  } catch (exc) {
    checks.graph = false;
    if (exc instanceof ReceiptError) {
      errors.push(`${exc.code}: ${exc.message}`);
    } else {
      errors.push(`receipt_error: ${String(exc)}`);
    }
    return report({
      valid: false,
      schema_version: SCHEMA_VERSION,
      canonicalization: CANONICALIZATION,
      variant: "final",
      checks,
      errors,
    });
  }

  const doc = document as Record<string, JsonValue>;
  checks.hashes =
    JSON.stringify(sortedObj(expected.node_hashes)) === JSON.stringify(sortedObj(doc.node_hashes)) &&
    JSON.stringify(expected.edge_hashes) === JSON.stringify(doc.edge_hashes);
  if (!checks.hashes) {
    errors.push("hash_mismatch: node_hashes or edge_hashes do not match recomputed leaves");
  }
  checks.root = expected.merkle_root === doc.merkle_root;
  if (!checks.root) {
    errors.push("root_mismatch: merkle_root does not match recomputed leaf set");
  }

  if ("receipt_hash" in doc) {
    const recomputed = receipt.receiptHash();
    checks.receipt_hash = recomputed === doc.receipt_hash;
    if (!checks.receipt_hash) {
      errors.push("hash_mismatch: receipt_hash annotation does not match");
    }
  }

  let sigResults: SignatureResult[] = [];
  try {
    sigResults = verifySignatures(expected, (doc.signatures ?? []) as Record<string, JsonValue>[]);
    checks.signatures = sigResults.every((r) => r.valid === true);
  } catch (exc) {
    checks.signatures = false;
    errors.push(exc instanceof ReceiptError ? `${exc.code}: ${exc.message}` : String(exc));
  }

  const valid = Object.values(checks).every(Boolean);
  return report({
    valid,
    schema_version: SCHEMA_VERSION,
    canonicalization: CANONICALIZATION,
    variant: "final",
    checks,
    errors,
    signatures: sigResults as unknown as Record<string, JsonValue>[],
    receipt_hash: receipt.receiptHash(),
    merkle_root: doc.merkle_root as string,
    node_count: receipt.nodes.length,
    edge_count: receipt.edges.length,
  });
}

function sortedObj(o: unknown): unknown {
  if (o !== null && typeof o === "object" && !Array.isArray(o)) {
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(o).sort()) out[k] = sortedObj((o as Record<string, unknown>)[k]);
    return out;
  }
  return o;
}

// ------------------------------------------------------------------ proofs

export function verifyProofDocument(proofDoc: unknown): boolean {
  try {
    const doc = proofDoc as Record<string, unknown>;
    const item = doc.item as Record<string, unknown>;
    const itemType = doc.item_type;
    const expectedLeaf = bytes32Hex(doc.leaf, "leaf");
    let actualLeaf: Uint8Array;
    if (itemType === "node") {
      new ReceiptNode(
        item.id as string,
        item.kind as string,
        item.payload as JsonValue,
        item.meta as Record<string, JsonValue> | undefined,
      ).validate();
      actualLeaf = nodeLeaf(item as unknown as NodeDict);
    } else if (itemType === "edge") {
      new ReceiptEdge(item.from as string, item.to as string, item.rel as string).validate();
      actualLeaf = edgeLeaf(item as unknown as EdgeDict);
    } else {
      return false;
    }
    if (Buffer.compare(Buffer.from(actualLeaf), Buffer.from(expectedLeaf)) !== 0) return false;
    const siblings = (doc.proof as unknown[]).map((p) => bytes32Hex(p, "proof element"));
    return verifyMerkleProof(
      doc.merkle_root as string,
      actualLeaf,
      siblings.map((s) => "0x" + Buffer.from(s).toString("hex")),
    );
  } catch (exc) {
    if (exc instanceof ReceiptError || exc instanceof TypeError) return false;
    throw exc;
  }
}

export const verifyReceiptProof = verifyProofDocument;

/** Accept a parsed object, JSON text, or bytes; return the document. */
export function loadReceipt(
  source: string | Uint8Array | Record<string, JsonValue>,
): Record<string, JsonValue> {
  if (typeof source === "object" && !(source instanceof Uint8Array)) return source;
  return parseJsonObject(source);
}

/** Read a receipt document from a file path (Node only — lazy node:fs). */
export async function loadReceiptFile(path: string): Promise<Record<string, JsonValue>> {
  const { readFile } = await import("node:fs/promises");
  return parseJsonObject(await readFile(path));
}
