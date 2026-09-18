/** Protocol error codes — the stable, machine-readable catalog shared by
 * every implementation (mirrors protocol/errors.py). Negative conformance
 * vectors assert on these codes; rename cautiously. */
export declare class ReceiptError extends Error {
    readonly code: string;
    constructor(message?: string, code?: string);
}
/** Input is outside the canonical-JSON domain (spec §7.1). */
export declare class CanonError extends ReceiptError {
    constructor(message?: string, code?: string);
}
/** Envelope/node/edge structure violates the schema. */
export declare class ShapeError extends ReceiptError {
    constructor(message?: string, code?: string);
}
/** Node-id / edge / DAG violations. */
export declare class GraphError extends ReceiptError {
    constructor(message?: string, code?: string);
}
/** Unsupported or missing schema_version. */
export declare class SchemaError extends ReceiptError {
    constructor(message?: string, code?: string);
}
/** Malformed signature object (a *failed* signature is not an error). */
export declare class SignatureError extends ReceiptError {
    constructor(message?: string, code?: string);
}
export declare const E_MISSING_FIELD = "missing_field";
export declare const E_UNKNOWN_FIELD = "unknown_field";
export declare const E_BAD_TYPE = "bad_type";
export declare const E_BAD_SCHEMA = "unsupported_schema";
export declare const E_BAD_NODE_ID = "invalid_node_id";
export declare const E_BAD_KIND = "invalid_kind";
export declare const E_BAD_REL = "invalid_rel";
export declare const E_BAD_TIMESTAMP = "invalid_timestamp";
export declare const E_EMPTY_SUBJECT = "empty_subject";
export declare const E_EMPTY_RECEIPT_ID = "empty_receipt_id";
export declare const E_EMPTY_NODES = "empty_nodes";
export declare const E_DUP_NODE_ID = "duplicate_node_id";
export declare const E_DUP_EDGE = "duplicate_edge";
export declare const E_DANGLING_EDGE = "dangling_edge";
export declare const E_SELF_LOOP = "self_loop";
export declare const E_CYCLE = "cycle";
export declare const E_HASH_MISMATCH = "hash_mismatch";
export declare const E_ROOT_MISMATCH = "root_mismatch";
export declare const E_BAD_HASH = "malformed_hash";
export declare const E_NONCANONICAL = "noncanonical_value";
export declare const E_LIMIT = "limit_exceeded";
export declare const E_BAD_SIGNATURE = "invalid_signature";
export declare const E_BAD_PROOF = "invalid_proof";
