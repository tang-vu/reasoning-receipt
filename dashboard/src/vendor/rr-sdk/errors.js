/** Protocol error codes — the stable, machine-readable catalog shared by
 * every implementation (mirrors protocol/errors.py). Negative conformance
 * vectors assert on these codes; rename cautiously. */
export class ReceiptError extends Error {
    code;
    constructor(message, code = "receipt_error") {
        super(message ?? code);
        this.name = "ReceiptError";
        this.code = code;
    }
}
/** Input is outside the canonical-JSON domain (spec §7.1). */
export class CanonError extends ReceiptError {
    constructor(message, code = "noncanonical_value") {
        super(message, code);
        this.name = "CanonError";
    }
}
/** Envelope/node/edge structure violates the schema. */
export class ShapeError extends ReceiptError {
    constructor(message, code = "invalid_shape") {
        super(message, code);
        this.name = "ShapeError";
    }
}
/** Node-id / edge / DAG violations. */
export class GraphError extends ReceiptError {
    constructor(message, code = "invalid_graph") {
        super(message, code);
        this.name = "GraphError";
    }
}
/** Unsupported or missing schema_version. */
export class SchemaError extends ReceiptError {
    constructor(message, code = "unsupported_schema") {
        super(message, code);
        this.name = "SchemaError";
    }
}
/** Malformed signature object (a *failed* signature is not an error). */
export class SignatureError extends ReceiptError {
    constructor(message, code = "invalid_signature") {
        super(message, code);
        this.name = "SignatureError";
    }
}
export const E_MISSING_FIELD = "missing_field";
export const E_UNKNOWN_FIELD = "unknown_field";
export const E_BAD_TYPE = "bad_type";
export const E_BAD_SCHEMA = "unsupported_schema";
export const E_BAD_NODE_ID = "invalid_node_id";
export const E_BAD_KIND = "invalid_kind";
export const E_BAD_REL = "invalid_rel";
export const E_BAD_TIMESTAMP = "invalid_timestamp";
export const E_EMPTY_SUBJECT = "empty_subject";
export const E_EMPTY_RECEIPT_ID = "empty_receipt_id";
export const E_EMPTY_NODES = "empty_nodes";
export const E_DUP_NODE_ID = "duplicate_node_id";
export const E_DUP_EDGE = "duplicate_edge";
export const E_DANGLING_EDGE = "dangling_edge";
export const E_SELF_LOOP = "self_loop";
export const E_CYCLE = "cycle";
export const E_HASH_MISMATCH = "hash_mismatch";
export const E_ROOT_MISMATCH = "root_mismatch";
export const E_BAD_HASH = "malformed_hash";
export const E_NONCANONICAL = "noncanonical_value";
export const E_LIMIT = "limit_exceeded";
export const E_BAD_SIGNATURE = "invalid_signature";
export const E_BAD_PROOF = "invalid_proof";
