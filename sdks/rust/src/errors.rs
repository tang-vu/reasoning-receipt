//! Protocol error type — mirrors `protocol/errors.py`. The `.code` strings
//! are the stable, machine-readable catalog shared by every implementation;
//! negative conformance vectors assert on them.

use std::fmt;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReceiptError {
    pub code: &'static str,
    pub message: String,
}

impl ReceiptError {
    pub fn new(code: &'static str, message: impl Into<String>) -> Self {
        let message = message.into();
        Self {
            code,
            message: if message.is_empty() { code.to_string() } else { message },
        }
    }

    pub fn canon(message: impl Into<String>) -> Self {
        Self::new(E_NONCANONICAL, message)
    }
    pub fn shape(message: impl Into<String>) -> Self {
        Self::new("invalid_shape", message)
    }
    pub fn graph(message: impl Into<String>) -> Self {
        Self::new("invalid_graph", message)
    }
    pub fn schema(message: impl Into<String>) -> Self {
        Self::new(E_BAD_SCHEMA, message)
    }
    pub fn signature(message: impl Into<String>) -> Self {
        Self::new(E_BAD_SIGNATURE, message)
    }
    pub fn limit(message: impl Into<String>) -> Self {
        Self::new(E_LIMIT, message)
    }
}

impl fmt::Display for ReceiptError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.message)
    }
}

impl std::error::Error for ReceiptError {}

pub type Result<T> = std::result::Result<T, ReceiptError>;

pub const E_MISSING_FIELD: &str = "missing_field";
pub const E_UNKNOWN_FIELD: &str = "unknown_field";
pub const E_BAD_TYPE: &str = "bad_type";
pub const E_BAD_SCHEMA: &str = "unsupported_schema";
pub const E_BAD_NODE_ID: &str = "invalid_node_id";
pub const E_BAD_KIND: &str = "invalid_kind";
pub const E_BAD_REL: &str = "invalid_rel";
pub const E_BAD_TIMESTAMP: &str = "invalid_timestamp";
pub const E_EMPTY_SUBJECT: &str = "empty_subject";
pub const E_EMPTY_RECEIPT_ID: &str = "empty_receipt_id";
pub const E_EMPTY_NODES: &str = "empty_nodes";
pub const E_DUP_NODE_ID: &str = "duplicate_node_id";
pub const E_DUP_EDGE: &str = "duplicate_edge";
pub const E_DANGLING_EDGE: &str = "dangling_edge";
pub const E_SELF_LOOP: &str = "self_loop";
pub const E_CYCLE: &str = "cycle";
pub const E_HASH_MISMATCH: &str = "hash_mismatch";
pub const E_ROOT_MISMATCH: &str = "root_mismatch";
pub const E_BAD_HASH: &str = "malformed_hash";
pub const E_NONCANONICAL: &str = "noncanonical_value";
pub const E_LIMIT: &str = "limit_exceeded";
pub const E_BAD_SIGNATURE: &str = "invalid_signature";
pub const E_BAD_PROOF: &str = "invalid_proof";
