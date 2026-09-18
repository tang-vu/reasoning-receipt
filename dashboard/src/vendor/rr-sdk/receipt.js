/** `reasoning-receipt/1` — portable evidence-receipt envelope.
 * Mirrors `protocol/receipt.py` exactly (spec §3–§6, §9–§12). */
import { canonicalBytes, CANONICALIZATION_ID, parseJsonObject } from "./canon.js";
import { E_BAD_HASH, E_BAD_KIND, E_BAD_NODE_ID, E_BAD_REL, E_BAD_SCHEMA, E_BAD_TIMESTAMP, E_BAD_TYPE, E_CYCLE, E_DANGLING_EDGE, E_DUP_EDGE, E_DUP_NODE_ID, E_EMPTY_NODES, E_EMPTY_RECEIPT_ID, E_EMPTY_SUBJECT, E_LIMIT, E_MISSING_FIELD, E_SELF_LOOP, E_UNKNOWN_FIELD, CanonError, GraphError, ReceiptError, SchemaError, ShapeError, } from "./errors.js";
import { merkleProof, merkleRoot, sha256Hex, verifyMerkleProof } from "./merkle.js";
import { verifySignatures } from "./signatures.js";
import { bytesToHex, hexToBytes, bytesEqual } from "./hex.js";
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
function concat(a, b) {
    const out = new Uint8Array(a.length + b.length);
    out.set(a, 0);
    out.set(b, a.length);
    return out;
}
function utcNowIso() {
    return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}
function checkNoControls(value, what, code) {
    for (const ch of value) {
        const cp = ch.codePointAt(0);
        if (cp < 0x20 || cp === 0x7f) {
            throw new ShapeError(`${what} contains a control character`, code);
        }
    }
}
export function validTimestamp(value) {
    if (typeof value !== "string")
        return false;
    const m = TIMESTAMP_RE.exec(value);
    if (!m)
        return false;
    const [, y, mo, d, h, mi, s] = m;
    const year = +y, mon = +mo, day = +d, hour = +h, min = +mi, sec = +s;
    if (mon < 1 || mon > 12 || day < 1 || hour > 23 || min > 59 || sec > 59)
        return false;
    return day <= new Date(Date.UTC(year, mon, 0)).getUTCDate();
}
export function bytes32Hex(value, what = "hash") {
    if (typeof value !== "string") {
        throw new ShapeError(`${what} is not a string`, E_BAD_HASH);
    }
    const raw = value.startsWith("0x") ? value.slice(2) : value;
    if (!/^[0-9a-fA-F]+$/.test(raw)) {
        throw new ShapeError(`${what} is not hex`, E_BAD_HASH);
    }
    const decoded = hexToBytes(raw);
    if (decoded.length !== 32) {
        throw new ShapeError(`${what} is ${decoded.length} bytes, expected 32`, E_BAD_HASH);
    }
    return decoded;
}
export function nodeLeaf(nodeDict) {
    return sha256Bytes(concat(LEAF_DOMAIN_NODE, canonicalBytes(nodeDict)));
}
export function edgeLeaf(edgeDict) {
    return sha256Bytes(concat(LEAF_DOMAIN_EDGE, canonicalBytes(edgeDict)));
}
function sha256Bytes(b) {
    return hexToBytes(sha256Hex(b));
}
export function merkleRootOf(leaves) {
    const sorted = [...leaves].sort(cmpBytes);
    return hexToBytes(merkleRoot(sorted));
}
function cmpBytes(a, b) {
    const m = Math.min(a.length, b.length);
    for (let i = 0; i < m; i++) {
        if (a[i] !== b[i])
            return a[i] - b[i];
    }
    return a.length - b.length;
}
export function receiptHashOf(committedEnvelope) {
    return sha256Hex(concat(HASH_DOMAIN_RECEIPT, canonicalBytes(committedEnvelope)));
}
// ------------------------------------------------------------------- model
export class ReceiptNode {
    id;
    kind;
    payload;
    meta;
    constructor(id, kind, payload, meta) {
        this.id = id;
        this.kind = kind;
        this.payload = payload;
        this.meta = meta;
    }
    validate() {
        if (!NODE_ID_RE.test(this.id)) {
            throw new GraphError(`invalid node id ${this.id}`, E_BAD_NODE_ID);
        }
        if (!VOCAB_RE.test(this.kind)) {
            throw new GraphError(`invalid node kind ${this.kind}`, E_BAD_KIND);
        }
        if (this.meta !== undefined && (this.meta === null || typeof this.meta !== "object" || Array.isArray(this.meta))) {
            throw new ShapeError("node meta must be an object", E_BAD_TYPE);
        }
        canonicalBytes(this.toDict());
    }
    toDict() {
        const out = { id: this.id, kind: this.kind, payload: this.payload };
        if (this.meta !== undefined)
            out.meta = this.meta;
        return out;
    }
}
export class ReceiptEdge {
    src;
    dst;
    rel;
    constructor(src, dst, rel) {
        this.src = src;
        this.dst = dst;
        this.rel = rel;
    }
    validate() {
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
    toDict() {
        return { from: this.src, to: this.dst, rel: this.rel };
    }
}
export class PortableReceipt {
    subject;
    nodes;
    edges;
    metadata;
    receipt_id;
    produced_at;
    schema_version;
    signatures;
    constructor(opts) {
        this.subject = opts.subject;
        this.nodes = opts.nodes;
        this.edges = opts.edges ?? [];
        this.metadata = opts.metadata ?? {};
        this.receipt_id = opts.receipt_id ?? crypto.randomUUID();
        this.produced_at = opts.produced_at ?? utcNowIso();
        this.schema_version = opts.schema_version ?? SCHEMA_VERSION;
        this.signatures = opts.signatures ?? [];
    }
    orderedNodes() {
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
        const ids = new Set();
        for (const node of this.nodes) {
            node.validate();
            if (ids.has(node.id)) {
                throw new GraphError(`duplicate node id ${node.id}`, E_DUP_NODE_ID);
            }
            ids.add(node.id);
        }
        return [...this.nodes].sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    }
    orderedEdges() {
        if (this.edges.length > MAX_EDGES) {
            throw new ShapeError("too many edges", E_LIMIT);
        }
        const nodeIds = new Set(this.nodes.map((n) => n.id));
        const triples = new Set();
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
    nodeDicts() {
        return this.orderedNodes().map((n) => n.toDict());
    }
    edgeDicts() {
        return this.orderedEdges().map((e) => e.toDict());
    }
    leaves() {
        const set = this.nodeDicts().map(nodeLeaf);
        set.push(...this.edgeDicts().map(edgeLeaf));
        return set.sort(cmpBytes);
    }
    nodeHashes() {
        const out = {};
        for (const nd of this.nodeDicts()) {
            out[nd.id] = "0x" + bytesToHex(nodeLeaf(nd));
        }
        return out;
    }
    edgeHashes() {
        return this.edgeDicts().map((ed) => "0x" + bytesToHex(edgeLeaf(ed)));
    }
    merkleRootHex() {
        return "0x" + bytesToHex(merkleRootOf(this.leaves()));
    }
    committedEnvelope() {
        if (!validTimestamp(this.produced_at)) {
            throw new ShapeError(`invalid produced_at ${this.produced_at}`, E_BAD_TIMESTAMP);
        }
        if (typeof this.receipt_id !== "string" ||
            this.receipt_id.length === 0 ||
            this.receipt_id.length > MAX_RECEIPT_ID) {
            throw new ShapeError("invalid receipt_id", E_EMPTY_RECEIPT_ID);
        }
        checkNoControls(this.receipt_id, "receipt_id", E_EMPTY_RECEIPT_ID);
        return {
            schema_version: this.schema_version,
            receipt_id: this.receipt_id,
            subject: this.subject,
            produced_at: this.produced_at,
            metadata: this.metadata,
            nodes: this.nodeDicts(),
            edges: this.edgeDicts(),
            node_hashes: this.nodeHashes(),
            edge_hashes: this.edgeHashes(),
            merkle_root: this.merkleRootHex(),
        };
    }
    toDict() {
        const envelope = this.committedEnvelope();
        if (this.signatures.length) {
            envelope.signatures = this.signatures;
        }
        envelope.receipt_hash = this.receiptHash();
        return envelope;
    }
    receiptHash() {
        return receiptHashOf(this.committedEnvelope());
    }
    canonicalBytes() {
        return canonicalBytes(this.committedEnvelope());
    }
    proofFor(nodeId) {
        const ordered = this.nodeDicts();
        const ids = ordered.map((n) => n.id);
        const idx = ids.indexOf(nodeId);
        if (idx === -1)
            throw new KeyError(`node ${nodeId} not in receipt`);
        const leaves = this.leaves();
        const leaf = nodeLeaf(ordered[idx]);
        const index = leaves.findIndex((l) => cmpBytes(l, leaf) === 0);
        return {
            schema_version: this.schema_version,
            item_type: "node",
            item: ordered[idx],
            leaf: "0x" + bytesToHex(leaf),
            merkle_root: "0x" + bytesToHex(merkleRootOf(leaves)),
            proof: merkleProof(leaves, index),
        };
    }
    proofForEdge(index) {
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
            leaf: "0x" + bytesToHex(leaf),
            merkle_root: "0x" + bytesToHex(merkleRootOf(leaves)),
            proof: merkleProof(leaves, leafIndex),
        };
    }
}
export class KeyError extends Error {
}
export class IndexError extends Error {
}
function assertAcyclic(edges) {
    const adjacency = new Map();
    for (const edge of edges) {
        const list = adjacency.get(edge.src) ?? [];
        list.push(edge.dst);
        adjacency.set(edge.src, list);
    }
    const WHITE = 0, GRAY = 1, BLACK = 2;
    const color = new Map();
    for (const start of adjacency.keys()) {
        if ((color.get(start) ?? WHITE) !== WHITE)
            continue;
        const stack = [
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
    subject;
    metadata;
    nodes = [];
    edges = [];
    constructor(subject, metadata = {}) {
        this.subject = subject;
        this.metadata = metadata;
    }
    add(nodeId, kind, payload, meta) {
        this.nodes.push(new ReceiptNode(nodeId, kind, payload, meta));
        return this;
    }
    link(src, dst, rel) {
        this.edges.push(new ReceiptEdge(src, dst, rel));
        return this;
    }
    finalize(opts = {}) {
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
function report(partial) {
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
function require(cond, message, code) {
    if (!cond)
        throw new ShapeError(message, code);
}
export function restoreReceipt(document) {
    if (document === null || typeof document !== "object" || Array.isArray(document)) {
        throw new ShapeError("receipt document is not an object", E_BAD_TYPE);
    }
    const doc = document;
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
    require(typeof receipt_id === "string" && receipt_id.length > 0 && receipt_id.length <= MAX_RECEIPT_ID, "invalid receipt_id", E_EMPTY_RECEIPT_ID);
    checkNoControls(receipt_id, "receipt_id", E_EMPTY_RECEIPT_ID);
    const produced_at = doc.produced_at;
    if (!validTimestamp(produced_at)) {
        throw new ShapeError(`invalid produced_at ${String(produced_at)}`, E_BAD_TIMESTAMP);
    }
    const metadata = doc.metadata ?? {};
    require(metadata !== null && typeof metadata === "object" && !Array.isArray(metadata), "metadata must be an object", E_BAD_TYPE);
    const rawNodes = doc.nodes;
    require(Array.isArray(rawNodes), "nodes must be an array", E_BAD_TYPE);
    const nodes = [];
    for (const raw of rawNodes) {
        require(raw !== null && typeof raw === "object" && !Array.isArray(raw), "node is not an object", E_BAD_TYPE);
        const n = raw;
        const extra = Object.keys(n).filter((k) => !NODE_FIELDS.has(k));
        if (extra.length) {
            throw new ShapeError(`unknown node fields ${extra.sort()}`, E_UNKNOWN_FIELD);
        }
        for (const needed of ["id", "kind", "payload"]) {
            if (!(needed in n)) {
                throw new ShapeError(`node missing ${needed}`, E_MISSING_FIELD);
            }
        }
        nodes.push(new ReceiptNode(n.id, n.kind, n.payload, n.meta));
    }
    const rawEdges = doc.edges ?? [];
    require(Array.isArray(rawEdges), "edges must be an array", E_BAD_TYPE);
    const edges = [];
    for (const raw of rawEdges) {
        require(raw !== null && typeof raw === "object" && !Array.isArray(raw), "edge is not an object", E_BAD_TYPE);
        const e = raw;
        const keys = Object.keys(e);
        if (keys.length !== EDGE_FIELDS.size || !keys.every((k) => EDGE_FIELDS.has(k))) {
            throw new ShapeError(`edge must have exactly ${[...EDGE_FIELDS].sort()}`, E_UNKNOWN_FIELD);
        }
        edges.push(new ReceiptEdge(e.from, e.to, e.rel));
    }
    require(doc.node_hashes !== null && typeof doc.node_hashes === "object" && !Array.isArray(doc.node_hashes), "node_hashes must be an object", E_BAD_TYPE);
    require(Array.isArray(doc.edge_hashes), "edge_hashes must be an array", E_BAD_TYPE);
    for (const value of [
        ...Object.values(doc.node_hashes),
        ...doc.edge_hashes,
    ]) {
        bytes32Hex(value, "leaf hash");
    }
    bytes32Hex(doc.merkle_root, "merkle_root");
    const signatures = doc.signatures ?? [];
    require(Array.isArray(signatures), "signatures must be an array", E_BAD_TYPE);
    const encoded = canonicalBytes(doc); // throws CanonError
    if (encoded.length > ENVELOPE_MAX_BYTES) {
        throw new ShapeError("envelope exceeds 8 MiB", E_LIMIT);
    }
    return new PortableReceipt({
        receipt_id: receipt_id,
        subject: doc.subject,
        produced_at: produced_at,
        metadata: metadata,
        nodes,
        edges,
        signatures: signatures,
    });
}
// ------------------------------------------------------------------ verify
export function verifyReceipt(document) {
    const checks = {};
    const errors = [];
    let receipt;
    try {
        receipt = restoreReceipt(document);
        checks.shape = true;
    }
    catch (exc) {
        checks.shape = false;
        if (exc instanceof ReceiptError) {
            errors.push(`${exc.code}: ${exc.message}`);
        }
        else {
            errors.push(`receipt_error: ${String(exc)}`);
        }
        return report({
            valid: false,
            schema_version: document !== null && typeof document === "object" && !Array.isArray(document)
                ? String(document.schema_version ?? "unknown")
                : "unknown",
            canonicalization: CANONICALIZATION,
            variant: "final",
            checks,
            errors,
        });
    }
    let expected;
    try {
        expected = receipt.committedEnvelope();
        checks.graph = true;
    }
    catch (exc) {
        checks.graph = false;
        if (exc instanceof ReceiptError) {
            errors.push(`${exc.code}: ${exc.message}`);
        }
        else {
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
    const doc = document;
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
    let sigResults = [];
    try {
        sigResults = verifySignatures(expected, (doc.signatures ?? []));
        checks.signatures = sigResults.every((r) => r.valid === true);
    }
    catch (exc) {
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
        signatures: sigResults,
        receipt_hash: receipt.receiptHash(),
        merkle_root: doc.merkle_root,
        node_count: receipt.nodes.length,
        edge_count: receipt.edges.length,
    });
}
function sortedObj(o) {
    if (o !== null && typeof o === "object" && !Array.isArray(o)) {
        const out = {};
        for (const k of Object.keys(o).sort())
            out[k] = sortedObj(o[k]);
        return out;
    }
    return o;
}
// ------------------------------------------------------------------ proofs
export function verifyProofDocument(proofDoc) {
    try {
        const doc = proofDoc;
        const item = doc.item;
        const itemType = doc.item_type;
        const expectedLeaf = bytes32Hex(doc.leaf, "leaf");
        let actualLeaf;
        if (itemType === "node") {
            new ReceiptNode(item.id, item.kind, item.payload, item.meta).validate();
            actualLeaf = nodeLeaf(item);
        }
        else if (itemType === "edge") {
            new ReceiptEdge(item.from, item.to, item.rel).validate();
            actualLeaf = edgeLeaf(item);
        }
        else {
            return false;
        }
        if (!bytesEqual(actualLeaf, expectedLeaf))
            return false;
        const siblings = doc.proof.map((p) => bytes32Hex(p, "proof element"));
        return verifyMerkleProof(doc.merkle_root, actualLeaf, siblings.map((s) => "0x" + bytesToHex(s)));
    }
    catch (exc) {
        if (exc instanceof ReceiptError || exc instanceof TypeError)
            return false;
        throw exc;
    }
}
export const verifyReceiptProof = verifyProofDocument;
/** Accept a parsed object, JSON text, or bytes; return the document. */
export function loadReceipt(source) {
    if (typeof source === "object" && !(source instanceof Uint8Array))
        return source;
    return parseJsonObject(source);
}
/** Read a receipt document from a file path (Node only — lazy node:fs). */
export async function loadReceiptFile(path) {
    throw new Error("loadReceiptFile is Node-only; pass the document to loadReceipt instead");
    return parseJsonObject(await readFile(path));
}
