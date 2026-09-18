//! reasoning-receipt — official Rust SDK for `reasoning-receipt/1`:
//! portable, byte-verifiable evidence receipts for AI decisions and actions.
//!
//! The protocol core is pure data + bytes: no chain, model provider,
//! storage backend, clock authority, or network is required to build or
//! verify a receipt.

pub mod canon;
pub mod conformance;
pub mod errors;
pub mod legacy_canon;
pub mod merkle;
pub mod receipt;
pub mod signatures;
pub mod verify;

pub use canon::{canonical_bytes, canonical_string, parse_json_object, CANONICALIZATION_ID};
pub use errors::{ReceiptError, Result};
pub use legacy_canon::{legacy_canonical_bytes, LEGACY_CANONICALIZATION_ID};
pub use merkle::{merkle_proof, merkle_root, sha256_hex, verify_proof};
pub use receipt::{
    bytes32_hex, edge_leaf, merkle_root_of, node_leaf, receipt_hash_of, restore_receipt,
    valid_timestamp, verify_proof_document, verify_receipt, PortableReceipt, ReceiptBuilder,
    ReceiptEdge, ReceiptNode, VerifyReport, CANONICALIZATION, SCHEMA_VERSION,
};
pub use signatures::{generate_keypair, sign, verify_signatures, ALG_ED25519};
pub use verify::{
    supported_schemas, verify_any, verify_receipt_draft, verify_trace3, verify_trace_blob,
    KNOWN_SCHEMAS, LEGACY_CANON,
};
