//! Unified verification entry point — dispatch strictly on `schema_version`.
//! Mirrors `protocol/verify.py` + `protocol/legacy.py`.

use crate::legacy_canon::legacy_canonical_bytes;
use crate::merkle;
use crate::receipt::{
    base_report, checks as mk_checks, VerifyReport,
    CANONICALIZATION, SCHEMA_VERSION,
};
use crate::receipt::verify_receipt;
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};

pub const KNOWN_SCHEMAS: &[&str] = &[SCHEMA_VERSION, "rr-trace/3", "rr-trace/2", "rr-trace/1"];
pub const LEGACY_CANON: &str = "legacy-json-6dp";
const TRACE_DAG_SCHEMA: &str = "rr-trace/3";

const CRITIC_DIMS: &[&str] = &[
    "evidence_relevance",
    "falsifiability",
    "scope",
    "coherence",
    "exploration_integrity",
    "methodology",
];

fn legacy_sha256(data: &[u8]) -> String {
    format!("0x{}", merkle::hex_encode(&Sha256::digest(data)))
}

pub fn legacy_trace_hash(document: &Value) -> String {
    legacy_sha256(&legacy_canonical_bytes(document))
}

fn is_blob_schema(schema: &str) -> bool {
    schema == "rr-trace/1" || schema == "rr-trace/2"
}

pub fn verify_trace_blob(document: &Value, expected_hash: Option<&str>) -> VerifyReport {
    let schema = document["schema_version"].as_str().unwrap_or_default();
    let mut errors: Vec<String> = Vec::new();
    let mut pairs: Vec<(String, bool)> = Vec::new();
    for field in ["market_id", "claim", "probability", "produced_at"] {
        let has = document.get(field).is_some();
        pairs.push((format!("has_{field}"), has));
        if !has {
            errors.push(format!("missing_field: {field}"));
        }
    }
    let mut recomputed: Option<String> = None;
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| legacy_trace_hash(document))) {
        Ok(h) => {
            recomputed = Some(h);
            pairs.push(("canonicalizable".into(), true));
        }
        Err(_) => {
            pairs.push(("canonicalizable".into(), false));
            errors.push("noncanonical_value: legacy canonicalization failed".into());
        }
    }
    if let Some(expected) = expected_hash {
        let ok = recomputed
            .as_ref()
            .map(|r| r.eq_ignore_ascii_case(expected))
            .unwrap_or(false);
        pairs.push(("hash_matches_expected".into(), ok));
        if !ok {
            errors.push("hash_mismatch: recomputed hash != expected anchored hash".into());
        }
    }
    let mut m = Map::new();
    for (k, v) in &pairs {
        m.insert(k.clone(), json!(v));
    }
    let mut rep = base_report(schema, LEGACY_CANON, schema, m, errors);
    rep.valid = pairs.iter().all(|(_, v)| *v);
    rep.receipt_hash = recomputed;
    rep
}

fn extract_trace3_nodes(document: &Value) -> Map<String, Value> {
    let mut out = Map::new();
    if let Some(claim) = document.get("claim").and_then(Value::as_object) {
        if let Some(id) = claim.get("id").and_then(Value::as_str) {
            out.insert(id.to_string(), Value::Object(claim.clone()));
        }
    }
    if let Some(stances) = document.get("stances").and_then(Value::as_array) {
        for stance in stances {
            let Some(s) = stance.as_object() else { continue };
            let Some(id) = s.get("id").and_then(Value::as_str) else { continue };
            let mut sdict = s.clone();
            let evidence = sdict
                .remove("evidence")
                .and_then(|e| e.as_array().cloned())
                .unwrap_or_default();
            out.insert(id.to_string(), Value::Object(sdict));
            for ev in evidence {
                if let Some(eo) = ev.as_object() {
                    if let Some(eid) = eo.get("id").and_then(Value::as_str) {
                        out.insert(eid.to_string(), ev.clone());
                    }
                }
            }
        }
    }
    for key in ["counter_arguments", "sensitivity", "falsifiable_claims"] {
        if let Some(items) = document.get(key).and_then(Value::as_array) {
            for item in items {
                if let Some(io) = item.as_object() {
                    if let Some(id) = io.get("id").and_then(Value::as_str) {
                        out.insert(id.to_string(), item.clone());
                    }
                }
            }
        }
    }
    if let Some(audit) = document.get("critic_audit").and_then(Value::as_object) {
        for dim in CRITIC_DIMS {
            if let Some(v) = audit.get(*dim) {
                if v.is_object() {
                    out.insert(format!("cd_{dim}"), v.clone());
                }
            }
        }
    }
    out
}

pub fn verify_trace3(document: &Value) -> VerifyReport {
    let mut errors: Vec<String> = Vec::new();
    let mut pairs: Vec<(String, bool)> = Vec::new();

    let nodes = extract_trace3_nodes(document);
    pairs.push(("nodes_extracted".into(), !nodes.is_empty()));
    if nodes.is_empty() {
        errors.push("invalid_shape: no rr-trace/3 nodes could be extracted".into());
    }

    let embedded = document
        .get("node_hashes")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    pairs.push(("node_hashes_present".into(), !embedded.is_empty()));
    if embedded.is_empty() {
        errors.push("missing_field: 'node_hashes'".into());
    }

    let mut recomputed = Map::new();
    for (id, nd) in &nodes {
        recomputed.insert(
            id.clone(),
            json!(legacy_sha256(&legacy_canonical_bytes(nd))),
        );
    }
    let hashes_ok = !embedded.is_empty() && Value::Object(recomputed) == Value::Object(embedded.clone());
    pairs.push(("hashes".into(), hashes_ok));
    if !embedded.is_empty() && !hashes_ok {
        errors.push("hash_mismatch: embedded node_hashes != recomputed".into());
    }

    let embedded_root = document.get("merkle_root");
    if !embedded.is_empty() {
        let mut leaves = Vec::new();
        let mut ok = true;
        let mut ids: Vec<&String> = embedded.keys().collect();
        ids.sort();
        for id in ids {
            match embedded[id].as_str().and_then(|h| merkle::hex_decode(h).ok()) {
                Some(b) if b.len() == 32 => {
                    let mut a = [0u8; 32];
                    a.copy_from_slice(&b);
                    leaves.push(a);
                }
                _ => {
                    ok = false;
                    pairs.push(("root".into(), false));
                    errors.push(format!("malformed_hash: {id}"));
                    break;
                }
            }
        }
        if ok {
            let root = merkle::merkle_root(&leaves);
            let hex = format!("0x{}", merkle::hex_encode(&root));
            let root_ok = embedded_root.and_then(Value::as_str) == Some(hex.as_str());
            pairs.push(("root".into(), root_ok));
            if !root_ok {
                errors.push("root_mismatch: embedded merkle_root != recomputed".into());
            }
        }
    } else {
        pairs.push(("root".into(), false));
        errors.push("missing_field: 'merkle_root'".into());
    }

    let blob_hash = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| legacy_trace_hash(document))).ok();

    let mut m = Map::new();
    for (k, v) in &pairs {
        m.insert(k.clone(), json!(v));
    }
    let mut rep = base_report(TRACE_DAG_SCHEMA, LEGACY_CANON, TRACE_DAG_SCHEMA, m, errors);
    rep.valid = pairs.iter().all(|(_, v)| *v);
    rep.receipt_hash = blob_hash;
    rep.merkle_root = embedded_root.and_then(Value::as_str).map(String::from);
    rep.node_count = nodes.len();
    rep
}

pub fn verify_receipt_draft(document: &Value) -> VerifyReport {
    let mut errors: Vec<String> = Vec::new();
    let mut pairs: Vec<(String, bool)> = Vec::new();
    for field in [
        "merkle_root", "node_hashes", "nodes", "produced_at",
        "receipt_id", "schema_version", "subject",
    ] {
        let has = document.get(field).is_some();
        pairs.push((format!("has_{field}"), has));
        if !has {
            errors.push(format!("missing_field: {field}"));
        }
    }
    let schema_ok = document["schema_version"].as_str() == Some(SCHEMA_VERSION);
    pairs.push(("schema".into(), schema_ok));
    if !schema_ok {
        errors.push("unsupported_schema: not reasoning-receipt/1".into());
    }

    let raw_nodes = document.get("nodes").and_then(Value::as_array).cloned().unwrap_or_default();
    let ids: Vec<Option<&str>> = raw_nodes
        .iter()
        .map(|n| n.as_object().and_then(|o| o.get("id")).and_then(Value::as_str))
        .collect();
    let unique = ids.iter().all(Option::is_some)
        && {
            let mut seen = std::collections::HashSet::new();
            ids.iter().all(|i| seen.insert(i.unwrap()))
        };
    pairs.push(("unique_ids".into(), unique));
    pairs.push(("nonempty".into(), !raw_nodes.is_empty()));

    let subject = document.get("subject").and_then(Value::as_str).unwrap_or("");
    if subject.chars().any(|c| (c as u32) < 0x20 || c as u32 == 0x7f) {
        pairs.push(("subject".into(), false));
        errors.push("empty_subject: subject contains a control character".into());
    }

    if unique && !raw_nodes.is_empty() {
        let mut ordered: Vec<&Value> = raw_nodes.iter().collect();
        ordered.sort_by(|a, b| {
            a["id"].as_str().unwrap_or("").cmp(b["id"].as_str().unwrap_or(""))
        });
        let mut recomputed = Map::new();
        for nd in ordered {
            if let Some(id) = nd["id"].as_str() {
                recomputed.insert(
                    id.to_string(),
                    json!(legacy_sha256(&legacy_canonical_bytes(nd))),
                );
            }
        }
        let mut ids_sorted: Vec<&String> = recomputed.keys().collect();
        ids_sorted.sort();
        let leaves: Vec<[u8; 32]> = ids_sorted
            .iter()
            .filter_map(|id| {
                merkle::hex_decode(recomputed[*id].as_str().unwrap_or(""))
                    .ok()
                    .and_then(|b| <[u8; 32]>::try_from(b.as_slice()).ok())
            })
            .collect();
        let root_hex = format!("0x{}", merkle::hex_encode(&merkle::merkle_root(&leaves)));
        let embedded = document.get("node_hashes").cloned().unwrap_or(json!({}));
        let hashes_ok = Value::Object(recomputed) == embedded;
        pairs.push(("hashes".into(), hashes_ok));
        let root_ok = document["merkle_root"].as_str() == Some(root_hex.as_str());
        pairs.push(("root".into(), root_ok));
        if !hashes_ok {
            errors.push("hash_mismatch: node_hashes != recomputed (draft rules)".into());
        }
        if !root_ok {
            errors.push("root_mismatch: merkle_root != recomputed (draft rules)".into());
        }
    }

    let mut m = Map::new();
    for (k, v) in &pairs {
        m.insert(k.clone(), json!(v));
    }
    let mut rep = base_report(SCHEMA_VERSION, LEGACY_CANON, "draft", m, errors);
    rep.valid = pairs.iter().all(|(_, v)| *v) && !raw_nodes.is_empty();
    rep.merkle_root = document["merkle_root"].as_str().map(String::from);
    rep.node_count = raw_nodes.len();
    rep
}

pub fn verify_any(document: &Value, expected_hash: Option<&str>) -> VerifyReport {
    if !document.is_object() {
        return base_report(
            "unknown",
            "unknown",
            "unknown",
            mk_checks(&[("shape", false)]),
            vec!["bad_type: document is not an object".into()],
        );
    }
    let schema = document.get("schema_version");

    if schema.and_then(Value::as_str) == Some(SCHEMA_VERSION) {
        let rep = verify_receipt(document);
        if rep.valid {
            return rep;
        }
        let has_draft_shape = document.get("edges").is_none()
            && document.get("edge_hashes").is_none()
            && document.get("signatures").is_none();
        if has_draft_shape {
            let draft = verify_receipt_draft(document);
            if draft.valid {
                return draft;
            }
        }
        return rep;
    }
    if let Some(s) = schema.and_then(Value::as_str) {
        if is_blob_schema(s) {
            return verify_trace_blob(document, expected_hash);
        }
        if s == TRACE_DAG_SCHEMA {
            return verify_trace3(document);
        }
    }
    let name = schema.and_then(Value::as_str).map(String::from).unwrap_or_else(|| "missing".into());
    base_report(
        &name,
        "unknown",
        "unknown",
        mk_checks(&[("shape", false)]),
        vec![format!("unsupported_schema: {name} — refusing to verify under guessed rules")],
    )
}

pub fn supported_schemas() -> Value {
    json!([
        {"schema_version": SCHEMA_VERSION, "status": "current",
         "canonicalization": CANONICALIZATION,
         "features": ["nodes", "edges", "merkle_proofs", "signatures"]},
        {"schema_version": "rr-trace/3", "status": "legacy",
         "canonicalization": LEGACY_CANON, "features": ["nodes", "merkle_proofs"]},
        {"schema_version": "rr-trace/2", "status": "legacy",
         "canonicalization": LEGACY_CANON, "features": ["blob_hash"]},
        {"schema_version": "rr-trace/1", "status": "legacy",
         "canonicalization": LEGACY_CANON, "features": ["blob_hash"]},
    ])
}
