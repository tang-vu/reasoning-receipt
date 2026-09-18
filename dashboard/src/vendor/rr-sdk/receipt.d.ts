/** `reasoning-receipt/1` — portable evidence-receipt envelope.
 * Mirrors `protocol/receipt.py` exactly (spec §3–§6, §9–§12). */
import type { JsonValue } from "./canon.js";
export declare const SCHEMA_VERSION = "reasoning-receipt/1";
export declare const CANONICALIZATION = "rr-json-1";
export declare function validTimestamp(value: unknown): boolean;
export declare function bytes32Hex(value: unknown, what?: string): Uint8Array;
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
export declare function nodeLeaf(nodeDict: NodeDict): Uint8Array;
export declare function edgeLeaf(edgeDict: EdgeDict): Uint8Array;
export declare function merkleRootOf(leaves: Uint8Array[]): Uint8Array;
export declare function receiptHashOf(committedEnvelope: Record<string, JsonValue>): string;
export declare class ReceiptNode {
    id: string;
    kind: string;
    payload: JsonValue;
    meta?: Record<string, JsonValue> | undefined;
    constructor(id: string, kind: string, payload: JsonValue, meta?: Record<string, JsonValue> | undefined);
    validate(): void;
    toDict(): NodeDict;
}
export declare class ReceiptEdge {
    src: string;
    dst: string;
    rel: string;
    constructor(src: string, dst: string, rel: string);
    validate(): void;
    toDict(): EdgeDict;
}
export interface ProofDocument {
    schema_version: string;
    item_type: "node" | "edge";
    item: NodeDict | EdgeDict;
    leaf: string;
    merkle_root: string;
    proof: string[];
}
export declare class PortableReceipt {
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
    });
    private orderedNodes;
    private orderedEdges;
    nodeDicts(): NodeDict[];
    edgeDicts(): EdgeDict[];
    leaves(): Uint8Array[];
    nodeHashes(): Record<string, string>;
    edgeHashes(): string[];
    merkleRootHex(): string;
    committedEnvelope(): Record<string, JsonValue>;
    toDict(): Record<string, JsonValue>;
    receiptHash(): string;
    canonicalBytes(): Uint8Array;
    proofFor(nodeId: string): ProofDocument;
    proofForEdge(index: number): ProofDocument;
}
export declare class KeyError extends Error {
}
export declare class IndexError extends Error {
}
export declare class ReceiptBuilder {
    private subject;
    private metadata;
    private nodes;
    private edges;
    constructor(subject: string, metadata?: Record<string, JsonValue>);
    add(nodeId: string, kind: string, payload: JsonValue, meta?: Record<string, JsonValue>): this;
    link(src: string, dst: string, rel: string): this;
    finalize(opts?: {
        receipt_id?: string;
        produced_at?: string;
    }): PortableReceipt;
}
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
export declare function restoreReceipt(document: unknown): PortableReceipt;
export declare function verifyReceipt(document: unknown): VerifyReport;
export declare function verifyProofDocument(proofDoc: unknown): boolean;
export declare const verifyReceiptProof: typeof verifyProofDocument;
/** Accept a parsed object, JSON text, or bytes; return the document. */
export declare function loadReceipt(source: string | Uint8Array | Record<string, JsonValue>): Record<string, JsonValue>;
/** Read a receipt document from a file path (Node only — lazy node:fs). */
export declare function loadReceiptFile(path: string): Promise<Record<string, JsonValue>>;
