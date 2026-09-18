//! Emit the cross-language parity receipt (spec: conformance/parity/).
//! Byte-identical canonical envelope to the Python and TypeScript
//! emitters — fixed IDs, timestamps and signing key make signatures
//! reproducible.

use reasoning_receipt::receipt::ReceiptBuilder;
use reasoning_receipt::signatures::sign;
use serde_json::{json, Map, Value};
use std::fs;
use std::path::PathBuf;

const PRIVATE_KEY: &str = "0x0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef";
const SIGNED_AT: &str = "2026-05-20T00:00:00Z";

fn map(entries: Vec<(&str, Value)>) -> Map<String, Value> {
    entries.into_iter().map(|(k, v)| (k.to_string(), v)).collect()
}

fn main() {
    let mut builder = ReceiptBuilder::new(
        "parity:cross-language",
        map(vec![
            ("harness", json!("rr-parity/1")),
            ("unicode", json!("héllo wörld — 数据 ✓")),
        ]),
    );
    builder
        .add(
            "intent",
            "intent",
            json!({"action": "deploy", "target": "testnet"}),
            Some(map(vec![("source", json!("emit"))])),
        )
        .add("policy", "policy", json!({"limit": 100, "rules": ["r1", "r2"]}), None)
        .add("decision", "decision", json!({"approved": true, "score": 0.125}), None)
        .add("outcome", "outcome", json!({"status": "success", "emoji": "🧾"}), None)
        .link("decision", "policy", "evaluated_against")
        .link("decision", "intent", "produced")
        .link("outcome", "decision", "produced");

    let mut receipt = builder
        .finalize(Some("rr-parity-0001".to_string()), Some(SIGNED_AT.to_string()))
        .expect("finalize");
    let envelope = receipt.committed_envelope().expect("envelope");
    receipt.signatures = vec![
        sign(&envelope, PRIVATE_KEY, "receipt", Some("parity-key"), Some(SIGNED_AT), None)
            .expect("sign receipt"),
        sign(&envelope, PRIVATE_KEY, "node:decision", Some("parity-key"), Some(SIGNED_AT), None)
            .expect("sign node"),
    ];

    let out = PathBuf::from(
        std::env::args().nth(1).unwrap_or_else(|| "../../conformance/parity/rs.receipt.json".into()),
    );
    if let Some(parent) = out.parent() {
        fs::create_dir_all(parent).ok();
    }
    let doc = receipt.to_dict().expect("to_dict");
    fs::write(&out, serde_json::to_string_pretty(&doc).unwrap() + "\n").expect("write");
    println!("{}", out.display());
}
